from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from . import schemas
from .audit import audit
from .bank import MockBankAdapter
from . import risk as risk_engine
from .config import settings
from .db import get_db
from .models import (SecurityDeposit, Discrepancy, VerificationRequest, VerificationEvidence, Document,
                     ReleaseRequest, Clearance, Instrument, RiskAssessment, User, utcnow)
from .security import current_user, get_deposit, require_roles, require_owner
from .presenters import record, deposit_detail, release_detail, task_for
from .workflows import RISK_CLEARANCE_CELL, current_instrument, detect, flag, readiness, reopen_verification, configuration, DEFAULT_WORKFLOW, release_blockers, release_reviewers

router = APIRouter(prefix="/api", tags=["Verification and release"])


def editable_review(deposit):
    if deposit.status in ("draft", "released", "release_authorised"):
        raise HTTPException(409, "This case is not open for verification")


@router.post("/deposits/{deposit_id}/assign")
def assign(deposit_id: str, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "verification")
    deposit = get_deposit(db, user, deposit_id, lock=True)
    editable_review(deposit)
    if deposit.assigned_officer_id and deposit.assigned_officer_id != user.id:
        raise HTTPException(409, "This case is already assigned to another officer")
    deposit.assigned_officer_id, deposit.status = user.id, "under_review"
    for item in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id)).all():
        item.assigned_officer_id = user.id
    audit(db, user, "officer_assigned", deposit.id, deposit.institution_id, after={"officer_id": user.id})
    db.commit()
    return deposit_detail(db, deposit, user)


def assigned_review(db, user, deposit_id):
    require_roles(user, "verification")
    deposit = get_deposit(db, user, deposit_id, lock=True)
    editable_review(deposit)
    if deposit.assigned_officer_id != user.id:
        raise HTTPException(403, "Assign this case to yourself before recording a finding")
    return deposit


@router.post("/deposits/{deposit_id}/assignment")
def reassign(deposit_id: str, body: schemas.AssignmentInput, user=Depends(current_user), db=Depends(get_db)):
    """Administrators move a case between officers; an assigned officer may hand their own case back."""
    require_roles(user, "admin", "verification")
    deposit = get_deposit(db, user, deposit_id, lock=True)
    editable_review(deposit)
    if user.role == "verification" and (body.officer_id or deposit.assigned_officer_id != user.id):
        raise HTTPException(403, "Officers may only hand back a case assigned to them")
    if body.officer_id:
        officer = db.get(User, body.officer_id)
        if not officer or officer.role != "verification" or not officer.active:
            raise HTTPException(422, "Choose an active verification officer")
    previous = deposit.assigned_officer_id
    if previous == body.officer_id:
        raise HTTPException(409, "The case is already assigned that way")
    deposit.assigned_officer_id = body.officer_id
    if not body.officer_id and deposit.status == "under_review":
        deposit.status = "submitted"
    elif body.officer_id and deposit.status == "submitted":
        deposit.status = "under_review"
    for item in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.status != "resolved")).all():
        item.assigned_officer_id = body.officer_id
    audit(db, user, "officer_reassigned", deposit.id, deposit.institution_id, {"officer_id": previous}, {"officer_id": body.officer_id, "reason": body.reason})
    db.commit()
    return deposit_detail(db, deposit, user)


@router.post("/deposits/{deposit_id}/observations")
def observation(deposit_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    deposit = assigned_review(db, user, deposit_id)
    audit(db, user, "scrutiny_observation", deposit.id, deposit.institution_id, after={"notes": body.notes})
    db.commit()
    return {"message": "Observation recorded"}


@router.post("/deposits/{deposit_id}/clarification")
def clarification(deposit_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    deposit = assigned_review(db, user, deposit_id)
    item = Discrepancy(deposit_id=deposit.id, instrument_id=current_instrument(db, deposit.id).id,
                       code="officer:" + __import__("secrets").token_hex(8), severity="warning", description=body.notes,
                       evidence_source="officer_review", next_step="Respond with an explanation and supporting documents.", assigned_officer_id=user.id)
    db.add(item)
    deposit.status = "clarification_required"
    reopen_verification(db, deposit, "Clarification requested")
    audit(db, user, "clarification_requested", deposit.id, deposit.institution_id, after={"notes": body.notes})
    risk_engine.assess(db, deposit)
    db.commit()
    return record(item)


@router.post("/discrepancies/{case_id}/respond")
def respond(case_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    item = db.get(Discrepancy, case_id)
    if not item:
        raise HTTPException(404, "Discrepancy not found")
    deposit = get_deposit(db, user, item.deposit_id, lock=True)
    require_owner(user, deposit)
    if item.status in ("resolved", "resolution_proposed"):
        raise HTTPException(409, "This discrepancy is already resolved or awaiting confirmation of its resolution")
    item.response, item.status = body.notes, "responded"
    audit(db, user, "clarification_responded", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "notes": body.notes})
    db.commit()
    return task_for(record(item), user)


@router.post("/discrepancies/{case_id}/resolve")
def resolve(case_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    item = db.get(Discrepancy, case_id)
    if not item:
        raise HTTPException(404, "Discrepancy not found")
    deposit = get_deposit(db, user, item.deposit_id, lock=True)
    if risk_engine.is_escalated(deposit) and risk_engine.suspicion_key(db, item):
        return vigilance_resolution(db, user, deposit, item, body)
    deposit = assigned_review(db, user, item.deposit_id)
    if item.status in ("resolved", "resolution_proposed"):
        raise HTTPException(409, "This discrepancy is already resolved or awaiting confirmation of its resolution")
    item.resolution, item.resolved_by = body.notes, user.id
    if item.severity == "high":
        # High-severity findings need a second verification officer, so one person cannot close them alone.
        if len(body.notes) < 20:
            raise HTTPException(422, "Explain the evidence behind a high-severity resolution in at least 20 characters")
        item.status = "resolution_proposed"
        audit(db, user, "discrepancy_resolution_proposed", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "code": item.code, "notes": body.notes})
    else:
        item.status, item.resolution_kind = "resolved", "officer"
        audit(db, user, "discrepancy_resolved", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "notes": body.notes})
    risk_engine.assess(db, deposit)
    db.commit()
    return record(item)


@router.post("/discrepancies/{case_id}/review")
def review_resolution(case_id: str, body: schemas.ResolutionReview, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "verification")
    item = db.get(Discrepancy, case_id)
    if not item:
        raise HTTPException(404, "Discrepancy not found")
    deposit = get_deposit(db, user, item.deposit_id, lock=True)
    editable_review(deposit)
    db.refresh(item)
    if item.status != "resolution_proposed":
        raise HTTPException(409, "Only proposed resolutions can be confirmed or rejected")
    if risk_engine.is_escalated(deposit) and risk_engine.suspicion_key(db, item):
        raise HTTPException(403, "This case is escalated to Vigilance; only Vigilance can clear its suspicious findings")
    if user.id in (item.resolved_by, deposit.assigned_officer_id):
        raise HTTPException(403, "A second verification officer, not the case officer, must review this resolution")
    if body.decision == "confirm":
        item.status, item.confirmed_by, item.resolution_kind = "resolved", user.id, "officer_confirmed"
        audit(db, user, "discrepancy_resolution_confirmed", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "code": item.code, "notes": body.notes})
    else:
        before = {"resolution": item.resolution, "resolved_by": item.resolved_by}
        item.status, item.resolution, item.resolved_by = "open", "", None
        audit(db, user, "discrepancy_resolution_rejected", deposit.id, deposit.institution_id, before, {"discrepancy_id": item.id, "code": item.code, "notes": body.notes})
    risk_engine.assess(db, deposit)
    db.commit()
    return record(item)


def vigilance_resolution(db, user, deposit, item, body):
    """On an escalated case, suspicious findings are cleared by Vigilance, independently of the case officer."""
    if user.role != "clearance" or user.clearance_cell != RISK_CLEARANCE_CELL:
        raise HTTPException(403, "This case is escalated to Vigilance; only Vigilance can clear its suspicious findings")
    editable_review(deposit)
    if item.status == "resolved":
        raise HTTPException(409, "This discrepancy is already resolved")
    if len(body.notes) < 20:
        raise HTTPException(422, "Explain the evidence behind the resolution in at least 20 characters")
    item.status, item.resolution, item.resolved_by, item.resolution_kind = "resolved", body.notes, user.id, "vigilance"
    audit(db, user, "discrepancy_resolved_by_vigilance", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "code": item.code, "notes": body.notes})
    risk_engine.assess(db, deposit)
    db.commit()
    return record(item)


@router.post("/deposits/{deposit_id}/vigilance-clearance")
def vigilance_clearance(deposit_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    """Vigilance closes an escalation once every suspicious finding on the case has been resolved."""
    require_roles(user, "clearance")
    if user.clearance_cell != RISK_CLEARANCE_CELL:
        raise HTTPException(403, "Only the Vigilance cell can clear an escalation")
    deposit = get_deposit(db, user, deposit_id, lock=True)
    editable_review(deposit)
    if not risk_engine.is_escalated(deposit):
        raise HTTPException(409, "This case is not escalated")
    still_open = [t for t in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.status != "resolved")).all()
                  if risk_engine.suspicion_key(db, t)]
    if still_open:
        raise HTTPException(409, f"Resolve the {len(still_open)} open suspicious finding(s) before clearing the escalation")
    deposit.vigilance_cleared_at, deposit.vigilance_cleared_by = utcnow(), user.id
    audit(db, user, "escalation_cleared_by_vigilance", deposit.id, deposit.institution_id, after={"notes": body.notes})
    db.commit()
    return deposit_detail(db, deposit, user)


@router.post("/deposits/{deposit_id}/verification-complete")
def verification_complete(deposit_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    """The officer's formal sign-off. Refused until the bank has confirmed, the receipt is checked,
    every review task is resolved and no suspicion above the limit remains uncleared by Vigilance."""
    deposit = assigned_review(db, user, deposit_id)
    risk_engine.assess(db, deposit)
    missing = [c["label"] + ": " + c["detail"] for c in readiness(db, deposit) if not c["met"]]
    if missing:
        raise HTTPException(409, {"message": "Verification cannot be completed yet", "blockers": missing})
    deposit.verified_at, deposit.verified_by = utcnow(), user.id
    if deposit.status in ("submitted", "under_review", "clarification_required"):
        deposit.status = "verified"
    audit(db, user, "verification_completed", deposit.id, deposit.institution_id, after={"notes": body.notes})
    db.commit()
    return deposit_detail(db, deposit, user)


@router.get("/deposits/{deposit_id}/risk")
def risk(deposit_id: str, user=Depends(current_user), db=Depends(get_db)):
    # Officials only: the explanation names the checks an altered document would need to evade.
    require_roles(user, "verification", "clearance", "authority", "admin", "auditor")
    deposit = get_deposit(db, user, deposit_id)
    current = risk_engine.latest(db, deposit.id)
    if not current:
        current = risk_engine.assess(db, deposit)
        db.commit()
    history = db.scalars(select(RiskAssessment).where(RiskAssessment.deposit_id == deposit.id).order_by(RiskAssessment.created_at)).all()
    return {**record(current), "history": [{key: getattr(h, key) for key in ("score", "level", "created_at", "engine_version", "weights_version")} for h in history],
            "notice": "A risk score orders review work. It is not a finding of fraud and does not authorise or refuse release."}


@router.post("/deposits/{deposit_id}/verification/mock")
def mock_verify(deposit_id: str, user=Depends(current_user), db=Depends(get_db)):
    if settings.environment == "production":
        raise HTTPException(403, "Simulated bank verification is disabled in production")
    deposit = assigned_review(db, user, deposit_id)
    inst = current_instrument(db, deposit.id)
    result = MockBankAdapter(db).verify(inst)
    request = VerificationRequest(deposit_id=deposit.id, instrument_id=inst.id, channel="SIMULATED / MOCK BANK DATA", requested_by=user.id, status=result["finding"])
    db.add(request)
    db.flush()
    evidence = VerificationEvidence(request_id=request.id, source=result["source"], reference="MOCK-" + inst.number,
                                    finding=result["finding"], observations=result["observations"], confirmed_fields=result["fields"],
                                    simulated=True, verified_on=date.today(), recorded_by=user.id)
    db.add(evidence)
    inst.verification_status = "mock_confirmed" if result["finding"] == "confirmed" else "mock_" + result["finding"]
    if result["finding"] != "confirmed":
        flag(db, deposit, "mock_bank:" + inst.id, result["observations"], "high", source="SIMULATED / MOCK BANK DATA", instrument_id=inst.id)
    detect(db, deposit)
    audit(db, user, "mock_verification_recorded", deposit.id, deposit.institution_id, after=result)
    db.commit()
    return result


@router.post("/deposits/{deposit_id}/verification/manual", status_code=201)
def manual_request(deposit_id: str, body: schemas.VerificationInput, user=Depends(current_user), db=Depends(get_db)):
    deposit = assigned_review(db, user, deposit_id)
    request = VerificationRequest(deposit_id=deposit.id, instrument_id=current_instrument(db, deposit.id).id,
                                  channel=body.channel, requested_by=user.id)
    db.add(request)
    audit(db, user, "verification_requested", deposit.id, deposit.institution_id, after={"channel": body.channel})
    db.commit()
    return record(request)


@router.post("/verifications/{request_id}/evidence")
def manual_evidence(request_id: str, body: schemas.EvidenceInput, user=Depends(current_user), db=Depends(get_db)):
    request = db.get(VerificationRequest, request_id)
    if not request:
        raise HTTPException(404, "Verification request not found")
    deposit = assigned_review(db, user, request.deposit_id)
    if request.channel.startswith("SIMULATED") or db.scalar(select(VerificationEvidence.id).where(VerificationEvidence.request_id == request.id)):
        raise HTTPException(409, "Create a new manual request to record additional evidence")
    doc = db.get(Document, body.document_id)
    if not doc or doc.deposit_id != deposit.id or doc.category != "bank_confirmation":
        raise HTTPException(422, "Attach an officer-uploaded bank confirmation from this case")
    inst = current_instrument(db, deposit.id)
    if request.instrument_id != inst.id:
        raise HTTPException(409, "Verification request refers to a replaced instrument")
    confirmed = body.confirmed_fields.model_dump(mode="json", exclude_none=True) if body.confirmed_fields else {}
    evidence = VerificationEvidence(request_id=request.id, **body.model_dump(exclude={"confirmed_fields"}), confirmed_fields=confirmed,
                                    recorded_by=user.id, simulated=False)
    db.add(evidence)
    request.status = body.finding
    inst.verification_status = "officially_confirmed" if body.finding == "confirmed" else body.finding
    if body.finding != "confirmed":
        flag(db, deposit, "manual_bank:" + request.id, body.observations, "high", source=body.source, instrument_id=inst.id)
    detect(db, deposit)
    audit(db, user, "bank_evidence_received", deposit.id, deposit.institution_id, after={"finding": body.finding, "reference": body.reference, "document_id": doc.id})
    db.commit()
    return record(evidence)


@router.post("/deposits/{deposit_id}/release", status_code=201)
def request_release(deposit_id: str, body: schemas.ReleaseInput, user=Depends(current_user), db=Depends(get_db)):
    deposit = get_deposit(db, user, deposit_id, lock=True)
    require_owner(user, deposit)
    if deposit.status in ("draft", "released", "release_authorised"):
        raise HTTPException(409, "Submit the deposit before requesting release")
    if db.scalar(select(ReleaseRequest.id).where(ReleaseRequest.deposit_id == deposit.id)):
        raise HTTPException(409, "A release request already exists for this deposit")
    if not deposit.verified_at:
        raise HTTPException(409, "An officer must complete verification before release can be requested")
    workflow = dict(configuration(db, "workflow", DEFAULT_WORKFLOW))
    if settings.environment == "production":
        workflow["allow_mock_for_demo"] = False
    release = ReleaseRequest(deposit_id=deposit.id, requested_by=user.id, kind=body.kind, reason=body.reason, workflow_snapshot=workflow)
    db.add(release)
    db.flush()
    for cell in workflow["cells"]:
        db.add(Clearance(release_id=release.id, cell=cell))
    db.flush()
    if (current := risk_engine.latest(db, deposit.id)) and current.level == "critical":
        risk_engine.require_risk_clearance(db, deposit)
    deposit.status = "release_requested"
    audit(db, user, "release_requested", deposit.id, deposit.institution_id, after={"kind": body.kind, "reason": body.reason, "workflow": workflow})
    db.commit()
    return release_detail(db, deposit, release, user)


@router.get("/releases")
def releases(user=Depends(current_user), db=Depends(get_db)):
    query = select(ReleaseRequest).join(SecurityDeposit, ReleaseRequest.deposit_id == SecurityDeposit.id).order_by(ReleaseRequest.created_at.desc())
    if user.role == "institution":
        query = query.where(SecurityDeposit.institution_id == user.institution_id)
    return [release_detail(db, db.get(SecurityDeposit, r.deposit_id), r, user) for r in db.scalars(query).all()]


@router.post("/clearances/{clearance_id}/decision")
def clearance_decision(clearance_id: str, body: schemas.Decision, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "clearance")
    item = db.get(Clearance, clearance_id)
    if not item:
        raise HTTPException(404, "Clearance not found")
    release = db.get(ReleaseRequest, item.release_id)
    deposit = get_deposit(db, user, release.deposit_id, lock=True)
    if item.cell != user.clearance_cell:
        raise HTTPException(403, "You may decide only your assigned clearance cell")
    if release.status in ("authorised", "completed", "rejected"):
        raise HTTPException(409, "This release is no longer open for clearance")
    before = record(item)
    item.status, item.notes, item.officer_id = body.decision, body.notes, user.id
    audit(db, user, "clearance_decided", deposit.id, deposit.institution_id, before, record(item))
    db.commit()
    return record(item)


@router.post("/releases/{release_id}/decision")
def release_decision(release_id: str, body: schemas.Decision, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "authority")
    release = db.get(ReleaseRequest, release_id)
    if not release:
        raise HTTPException(404, "Release not found")
    deposit = get_deposit(db, user, release.deposit_id, lock=True)
    db.refresh(release)
    if release.status in ("authorised", "completed", "rejected"):
        raise HTTPException(409, "This release already has a final decision")
    if user.id in release_reviewers(db, deposit, release):
        raise HTTPException(403, 'A different approving authority must decide this release. You previously submitted or reviewed this case.')
    # Decide on a current score: institution history or time may have moved it since the last event.
    current = risk_engine.assess(db, deposit)
    if body.decision == "approved":
        if current.level == "critical" and not body.risk_acknowledged:
            raise HTTPException(409, {"message": "Release authorisation is blocked", "blockers": ["Confirm that you have read the risk explanation for this critical-risk case."]})
        blockers = release_blockers(db, deposit, release)
        if blockers:
            raise HTTPException(409, {"message": "Release authorisation is blocked", "blockers": blockers})
        release.status, deposit.status = "authorised", "release_authorised"
        release.authorised_by = user.id
    else:
        release.status = body.decision
    release.decision_notes = body.notes
    audit(db, user, "release_" + body.decision, deposit.id, deposit.institution_id,
          after={"notes": body.notes, "status": release.status, "risk_score": float(current.score), "risk_level": current.level, "risk_acknowledged": body.risk_acknowledged})
    db.commit()
    return release_detail(db, deposit, release, user)


@router.post("/releases/{release_id}/resubmit")
def resubmit_release(release_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    release = db.get(ReleaseRequest, release_id)
    if not release:
        raise HTTPException(404, "Release not found")
    deposit = get_deposit(db, user, release.deposit_id, lock=True)
    require_owner(user, deposit)
    if release.status != "returned":
        raise HTTPException(409, "Only returned requests can be resubmitted")
    release.status = "under_review"
    audit(db, user, "release_resubmitted", deposit.id, deposit.institution_id, after={"notes": body.notes})
    db.commit()
    return release_detail(db, deposit, release, user)


@router.post("/releases/{release_id}/complete")
def complete_release(release_id: str, body: schemas.Completion, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "authority")
    release = db.get(ReleaseRequest, release_id)
    if not release:
        raise HTTPException(404, "Release not found")
    deposit = get_deposit(db, user, release.deposit_id, lock=True)
    if release.status != "authorised":
        raise HTTPException(409, "Record completion only after final authorisation")
    release.status, release.completion_reference, deposit.status = "completed", body.reference, "released"
    current_instrument(db, deposit.id).status = "discharged"
    audit(db, user, "release_completion_recorded", deposit.id, deposit.institution_id, after={"reference": body.reference, "money_transferred_by_portal": False})
    db.commit()
    return release_detail(db, deposit, release, user)

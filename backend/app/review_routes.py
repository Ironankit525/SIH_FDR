from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from . import schemas
from .audit import audit
from .bank import MockBankAdapter
from .config import settings
from .db import get_db
from .models import (SecurityDeposit, Discrepancy, VerificationRequest, VerificationEvidence, Document,
                     ReleaseRequest, Clearance, Instrument)
from .security import current_user, get_deposit, require_roles, require_owner
from .presenters import record, deposit_detail, release_detail
from .workflows import current_instrument, flag, configuration, DEFAULT_WORKFLOW, release_blockers, release_reviewers

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
    return deposit_detail(db, deposit)


def assigned_review(db, user, deposit_id):
    require_roles(user, "verification")
    deposit = get_deposit(db, user, deposit_id, lock=True)
    editable_review(deposit)
    if deposit.assigned_officer_id != user.id:
        raise HTTPException(403, "Assign this case to yourself before recording a finding")
    return deposit


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
    audit(db, user, "clarification_requested", deposit.id, deposit.institution_id, after={"notes": body.notes})
    db.commit()
    return record(item)


@router.post("/discrepancies/{case_id}/respond")
def respond(case_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    item = db.get(Discrepancy, case_id)
    if not item:
        raise HTTPException(404, "Discrepancy not found")
    deposit = get_deposit(db, user, item.deposit_id, lock=True)
    require_owner(user, deposit)
    if item.status == "resolved":
        raise HTTPException(409, "This discrepancy is already resolved")
    item.response, item.status = body.notes, "responded"
    audit(db, user, "clarification_responded", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "notes": body.notes})
    db.commit()
    return record(item)


@router.post("/discrepancies/{case_id}/resolve")
def resolve(case_id: str, body: schemas.Note, user=Depends(current_user), db=Depends(get_db)):
    item = db.get(Discrepancy, case_id)
    if not item:
        raise HTTPException(404, "Discrepancy not found")
    deposit = assigned_review(db, user, item.deposit_id)
    if item.status == "resolved":
        raise HTTPException(409, "This discrepancy is already resolved")
    item.resolution, item.status = body.notes, "resolved"
    audit(db, user, "discrepancy_resolved", deposit.id, deposit.institution_id, after={"discrepancy_id": item.id, "notes": body.notes})
    db.commit()
    return record(item)


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
    evidence = VerificationEvidence(request_id=request.id, **body.model_dump(), recorded_by=user.id, simulated=False)
    db.add(evidence)
    request.status = body.finding
    inst.verification_status = "officially_confirmed" if body.finding == "confirmed" else body.finding
    if body.finding != "confirmed":
        flag(db, deposit, "manual_bank:" + request.id, body.observations, "high", source=body.source, instrument_id=inst.id)
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
    workflow = dict(configuration(db, "workflow", DEFAULT_WORKFLOW))
    if settings.environment == "production":
        workflow["allow_mock_for_demo"] = False
    release = ReleaseRequest(deposit_id=deposit.id, requested_by=user.id, kind=body.kind, reason=body.reason, workflow_snapshot=workflow)
    db.add(release)
    db.flush()
    for cell in workflow["cells"]:
        db.add(Clearance(release_id=release.id, cell=cell))
    deposit.status = "release_requested"
    audit(db, user, "release_requested", deposit.id, deposit.institution_id, after={"kind": body.kind, "reason": body.reason, "workflow": workflow})
    db.commit()
    return release_detail(db, deposit, release)


@router.get("/releases")
def releases(user=Depends(current_user), db=Depends(get_db)):
    query = select(ReleaseRequest).join(SecurityDeposit, ReleaseRequest.deposit_id == SecurityDeposit.id).order_by(ReleaseRequest.created_at.desc())
    if user.role == "institution":
        query = query.where(SecurityDeposit.institution_id == user.institution_id)
    return [release_detail(db, db.get(SecurityDeposit, r.deposit_id), r) for r in db.scalars(query).all()]


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
    if body.decision == "approved":
        blockers = release_blockers(db, deposit, release)
        if blockers:
            raise HTTPException(409, {"message": "Release authorisation is blocked", "blockers": blockers})
        release.status, deposit.status = "authorised", "release_authorised"
        release.authorised_by = user.id
    else:
        release.status = body.decision
    release.decision_notes = body.notes
    audit(db, user, "release_" + body.decision, deposit.id, deposit.institution_id, after={"notes": body.notes, "status": release.status})
    db.commit()
    return release_detail(db, deposit, release)


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
    return release_detail(db, deposit, release)


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
    return release_detail(db, deposit, release)

"""Bank role endpoints: overview, verification queue, detail and verification actions."""
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from . import schemas
from .audit import audit
from .db import get_db
from .matching import normalise_bank
from .models import (
    SecurityDeposit, Instrument, Document, VerificationRequest,
    VerificationEvidence, Institution, Programme, User, utcnow
)
from .presenters import record
from .security import current_user, require_roles
from .workflows import current_instrument, detect, flag
from . import risk as risk_engine

router = APIRouter(prefix="/api/bank", tags=["Bank verification"])


def get_bank_request(db, user, request_id: str) -> tuple[VerificationRequest, SecurityDeposit, Instrument]:
    require_roles(user, "bank")
    req = db.get(VerificationRequest, request_id)
    if not req:
        raise HTTPException(404, "Verification request not found")
    user_bank_key = normalise_bank(user.bank_name or "")
    req_bank_key = normalise_bank(req.bank_name or "")
    if not user_bank_key or user_bank_key != req_bank_key:
        raise HTTPException(404, "Verification request not found")
    deposit = db.get(SecurityDeposit, req.deposit_id)
    if not deposit:
        raise HTTPException(404, "Associated deposit not found")
    inst = db.get(Instrument, req.instrument_id) or current_instrument(db, deposit.id)
    return req, deposit, inst


@router.get("/overview")
def bank_overview(user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "bank")
    user_bank_key = normalise_bank(user.bank_name or "")
    all_reqs = db.scalars(
        select(VerificationRequest)
        .where(VerificationRequest.bank_name.is_not(None))
        .order_by(VerificationRequest.created_at.desc())
    ).all()
    # Filter for this bank
    reqs = [r for r in all_reqs if normalise_bank(r.bank_name or "") == user_bank_key]

    total = len(reqs)
    pending_sent = sum(1 for r in reqs if r.status in ("sent", "pending"))
    under_verification = sum(1 for r in reqs if r.status == "under_verification")
    verified = sum(1 for r in reqs if r.status == "verified" or r.bank_decision == "verified")
    rejected = sum(1 for r in reqs if r.status == "rejected" or r.bank_decision == "rejected")
    info_requested = sum(1 for r in reqs if r.status == "additional_info_required" or r.bank_decision == "additional_info_required")

    # Recent items summary
    recent = []
    for r in reqs[:6]:
        deposit = db.get(SecurityDeposit, r.deposit_id)
        institution = db.get(Institution, deposit.institution_id) if deposit else None
        inst = db.get(Instrument, r.instrument_id) if r.instrument_id else None
        recent.append({
            "id": r.id,
            "deposit_id": r.deposit_id,
            "reference": deposit.reference if deposit else "Unknown",
            "institution_name": institution.name if institution else "Unknown",
            "instrument_number": inst.number if inst else "Unknown",
            "amount": float(inst.amount) if inst else 0.0,
            "maturity_date": inst.maturity_date.isoformat() if inst and inst.maturity_date else None,
            "status": r.status,
            "bank_decision": r.bank_decision,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "bank_name": user.bank_name,
        "total_requests": total,
        "pending_requests": pending_sent,
        "under_verification": under_verification,
        "verified": verified,
        "rejected": rejected,
        "additional_info_required": info_requested,
        "recent": recent,
    }


@router.get("/verifications")
def list_bank_verifications(
    status: str = "",
    q: str = "",
    user=Depends(current_user),
    db=Depends(get_db)
):
    require_roles(user, "bank")
    user_bank_key = normalise_bank(user.bank_name or "")
    all_reqs = db.scalars(
        select(VerificationRequest)
        .where(VerificationRequest.bank_name.is_not(None))
        .order_by(VerificationRequest.created_at.desc())
    ).all()
    reqs = [r for r in all_reqs if normalise_bank(r.bank_name or "") == user_bank_key]

    items = []
    today = date.today()
    for r in reqs:
        deposit = db.get(SecurityDeposit, r.deposit_id)
        if not deposit:
            continue
        institution = db.get(Institution, deposit.institution_id)
        inst = db.get(Instrument, r.instrument_id) or current_instrument(db, deposit.id)
        officer = db.get(User, r.requested_by) if r.requested_by else None

        item = {
            "id": r.id,
            "deposit_id": deposit.id,
            "reference": deposit.reference,
            "institution_name": institution.name if institution else "Unknown",
            "institution_code": institution.code if institution else "Unknown",
            "instrument_number": inst.number if inst else "Unknown",
            "instrument_type": inst.instrument_type if inst else "FDR",
            "bank": inst.bank if inst else (r.bank_name or "Unknown"),
            "branch": inst.branch if inst else "Unknown",
            "depositor_name": inst.depositor_name if inst else "Unknown",
            "amount": float(inst.amount) if inst else 0.0,
            "issue_date": inst.issue_date.isoformat() if inst and inst.issue_date else None,
            "maturity_date": inst.maturity_date.isoformat() if inst and inst.maturity_date else None,
            "days_to_maturity": (inst.maturity_date - today).days if inst and inst.maturity_date else None,
            "submission_date": deposit.submitted_at.isoformat() if deposit.submitted_at else (deposit.created_at.isoformat() if deposit.created_at else None),
            "status": r.status,
            "bank_decision": r.bank_decision,
            "officer_notes": r.officer_notes,
            "requested_by_name": officer.name if officer else "Assigned Officer",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "bank_verified_at": r.bank_verified_at.isoformat() if r.bank_verified_at else None,
            "bank_remarks": r.bank_remarks,
        }

        # Filtering
        if status and status != "all":
            if status == "pending" and item["status"] not in ("sent", "pending"):
                continue
            elif status != "pending" and item["status"] != status and item.get("bank_decision") != status:
                continue

        if q:
            searchable = f"{item['reference']} {item['institution_name']} {item['instrument_number']} {item['depositor_name']}".lower()
            if q.lower() not in searchable:
                continue

        items.append(item)

    return items


@router.get("/verifications/{request_id}")
def get_bank_verification_detail(request_id: str, user=Depends(current_user), db=Depends(get_db)):
    req, deposit, inst = get_bank_request(db, user, request_id)
    institution = db.get(Institution, deposit.institution_id)
    programme = db.get(Programme, deposit.programme_id)
    officer = db.get(User, req.requested_by) if req.requested_by else None
    decider = db.get(User, req.bank_user_id) if getattr(req, "bank_user_id", None) else None

    # Auto-transition from "sent" to "under_verification" upon first view
    if req.status in ("sent", "pending"):
        req.status = "under_verification"
        audit(db, user, "bank_review_started", deposit.id, deposit.institution_id,
              after={"request_id": req.id, "bank_name": user.bank_name})
        db.commit()

    # Documents available to inspect
    docs = db.scalars(
        select(Document)
        .where(Document.deposit_id == deposit.id)
        .order_by(Document.created_at)
    ).all()

    evidence = db.scalar(
        select(VerificationEvidence)
        .where(VerificationEvidence.request_id == req.id)
    )

    today = date.today()
    return {
        "request": {
            **record(req),
            "requested_by_name": officer.name if officer else "Assigned Officer",
            "bank_user_name": decider.name if decider else None,
        },
        "deposit": {
            "id": deposit.id,
            "reference": deposit.reference,
            "status": deposit.status,
            "submitted_at": deposit.submitted_at.isoformat() if deposit.submitted_at else None,
            "regulatory_end_date": deposit.regulatory_end_date.isoformat() if deposit.regulatory_end_date else None,
        },
        "institution": {
            "id": institution.id if institution else None,
            "name": institution.name if institution else "Unknown",
            "code": institution.code if institution else "Unknown",
            "state": institution.state if institution else "Unknown",
            "contact_email": institution.contact_email if institution else "Unknown",
            "address": institution.address if institution else "",
            "programme": programme.name if programme else "Unknown",
        },
        "instrument": {
            "id": inst.id if inst else None,
            "instrument_type": inst.instrument_type if inst else "FDR",
            "bank": inst.bank if inst else "Unknown",
            "branch": inst.branch if inst else "Unknown",
            "number": inst.number if inst else "Unknown",
            "depositor_name": inst.depositor_name if inst else "Unknown",
            "amount": float(inst.amount) if inst else 0.0,
            "issue_date": inst.issue_date.isoformat() if inst and inst.issue_date else None,
            "maturity_date": inst.maturity_date.isoformat() if inst and inst.maturity_date else None,
            "days_to_maturity": (inst.maturity_date - today).days if inst and inst.maturity_date else None,
            "validity_date": inst.validity_date.isoformat() if inst and inst.validity_date else None,
            "lien_details": inst.lien_details if inst else "",
            "verification_status": inst.verification_status if inst else "pending",
        },
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "category": d.category,
                "size": d.size,
                "content_type": d.content_type,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "scan_status": d.scan_status,
            }
            for d in docs
        ],
        "evidence": record(evidence) if evidence else None,
    }


@router.post("/verifications/{request_id}/decision")
def submit_bank_decision(
    request_id: str,
    body: schemas.BankDecisionInput,
    user=Depends(current_user),
    db=Depends(get_db)
):
    req, deposit, inst = get_bank_request(db, user, request_id)

    # Prevent duplicate conflicting final actions
    if req.status in ("verified", "rejected") and req.bank_decision in ("verified", "rejected"):
        raise HTTPException(409, f"This verification request has already been finalized as {req.bank_decision}.")

    before = record(req)
    req.status = body.decision
    req.bank_decision = body.decision
    req.bank_remarks = body.remarks
    req.bank_user_id = user.id
    req.bank_verified_at = utcnow()

    # Update instrument status and record discrepancy flags where appropriate
    if body.decision == "verified":
        inst.verification_status = "bank_verified"
        finding = "confirmed"
    elif body.decision == "rejected":
        inst.verification_status = "bank_rejected"
        finding = "mismatched"
        flag(
            db, deposit, f"bank_rejection:{req.id}",
            f"The issuing bank rejected verification: {body.remarks}",
            "high", source=f"Bank Portal ({user.bank_name})", instrument_id=inst.id
        )
    else:  # additional_info_required
        inst.verification_status = "bank_info_requested"
        finding = "inconclusive"
        deposit.status = "clarification_required"
        flag(
            db, deposit, f"bank_clarification:{req.id}",
            f"The bank requested additional information before verification: {body.remarks}",
            "warning", source=f"Bank Portal ({user.bank_name})", instrument_id=inst.id
        )

    # Record or update VerificationEvidence
    confirmed = body.confirmed_fields.model_dump(mode="json", exclude_none=True) if body.confirmed_fields else {}
    evidence = db.scalar(select(VerificationEvidence).where(VerificationEvidence.request_id == req.id))
    if not evidence:
        evidence = VerificationEvidence(
            request_id=req.id,
            source=f"Bank Portal ({user.bank_name})",
            reference=f"BANK-{req.id[:8].upper()}",
            finding=finding,
            observations=body.remarks,
            confirmed_fields=confirmed,
            simulated=False,
            verified_on=date.today(),
            recorded_by=user.id
        )
        db.add(evidence)
    else:
        evidence.finding = finding
        evidence.observations = body.remarks
        evidence.confirmed_fields = confirmed
        evidence.verified_on = date.today()
        evidence.recorded_by = user.id

    # Append-only audit trail
    audit(
        db, user, f"bank_verification_{body.decision}", deposit.id, deposit.institution_id,
        before=before,
        after={
            "request_id": req.id,
            "decision": body.decision,
            "remarks": body.remarks,
            "bank_user": user.name,
            "bank_name": user.bank_name,
            "instrument_number": inst.number
        }
    )

    detect(db, deposit)
    risk_engine.assess(db, deposit)
    db.commit()

    return {
        "message": f"Verification decision '{body.decision}' recorded successfully.",
        "request": record(req),
        "evidence": record(evidence)
    }

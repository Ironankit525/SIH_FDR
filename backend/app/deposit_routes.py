import hashlib
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Literal

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from . import schemas
from .audit import audit
from .config import settings
from .db import get_db
from .models import (Institution, Programme, SecurityDeposit, Instrument, Document, Extraction, FieldCorrection,
                     Replacement, ReleaseRequest, User, utcnow)
from .security import current_user, require_roles, require_owner, get_deposit, rate_limit
from .presenters import record, deposit_summary, deposit_detail
from .risk import assess
from .rules import calculate
from .storage import store, validate_file
from .jobs import dispatch
from .workflows import current_instrument, detect, flag, instrument_conflicts, institution_profile

router = APIRouter(prefix="/api", tags=["Institutions and deposits"])


@router.get("/institutions")
def institutions(user=Depends(current_user), db=Depends(get_db)):
    query = select(Institution).order_by(Institution.name)
    if user.role == "institution":
        query = query.where(Institution.id == user.institution_id)
    return [{**record(i), "programmes": [record(p) for p in db.scalars(select(Programme).where(Programme.institution_id == i.id)).all()]} for i in db.scalars(query).all()]


@router.put("/institutions/{institution_id}")
def update_institution(institution_id: str, body: schemas.InstitutionInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "institution", "admin")
    if user.role == "institution" and user.institution_id != institution_id:
        raise HTTPException(404, "Institution not found")
    item = db.get(Institution, institution_id)
    if not item:
        raise HTTPException(404, "Institution not found")
    before = record(item)
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    audit(db, user, "institution_updated", item.id, item.id, before, record(item))
    db.commit()
    return record(item)


@router.post("/requirements/calculate")
def requirement(body: schemas.RequirementInput, user=Depends(current_user), db=Depends(get_db)):
    if user.role == "institution" and body.institution_id != user.institution_id:
        raise HTTPException(404, "Institution not found")
    institution, programme = db.get(Institution, body.institution_id), db.get(Programme, body.programme_id)
    if not institution or not programme or programme.institution_id != institution.id:
        raise HTTPException(404, "Programme not found")
    return calculate(db, institution, programme, body.as_of)


@router.get("/deposits")
def deposits(q: str = "", status: str = "", bank: str = "", programme: str = "", assigned: str = "", min_amount: float | None = None,
             max_amount: float | None = None, date_from: str = "", date_to: str = "", risk_level: str = "", sort: Literal["", "risk"] = "",
             user=Depends(current_user), db=Depends(get_db)):
    query = select(SecurityDeposit).order_by(SecurityDeposit.created_at.desc())
    if user.role == "institution":
        query = query.where(SecurityDeposit.institution_id == user.institution_id)
    if status:
        query = query.where(SecurityDeposit.status == status)
    if assigned == "me":
        query = query.where(SecurityDeposit.assigned_officer_id == user.id)
    results = [deposit_summary(db, d, user) for d in db.scalars(query).all()]
    if "risk" in (results[0] if results else {}):
        # Riskiest first, so the queue starts where scrutiny matters most.
        results = [r for r in results if not risk_level or (r["risk"] and r["risk"]["level"] == risk_level)]
        if sort == "risk":
            results.sort(key=lambda r: -(r["risk"]["score"] if r["risk"] else 0))
    return [r for r in results if (not q or q.lower() in " ".join([r["reference"], r["institution_name"], r["instrument"]["number"]]).lower())
            and (not bank or bank.lower() in r["instrument"]["bank"].lower()) and (not programme or programme.lower() in r["programme"].lower())
            and (min_amount is None or float(r["instrument"]["amount"]) >= min_amount) and (max_amount is None or float(r["instrument"]["amount"]) <= max_amount)
            and (not date_from or r["instrument"]["maturity_date"] >= date_from) and (not date_to or r["instrument"]["maturity_date"] <= date_to)]


def reject_duplicate(db, body, deposit_id=None):
    # Spacing, punctuation and bank abbreviations must not let one instrument be registered twice.
    if instrument_conflicts(db, body.bank, body.number, deposit_id)[0]:
        raise HTTPException(409, "This bank and instrument reference is already registered. Ask an officer to review the possible duplicate.")


@router.get("/institutions/{institution_id}/profile")
def profile(institution_id: str, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "verification", "clearance", "authority", "admin", "auditor")
    if not db.get(Institution, institution_id):
        raise HTTPException(404, "Institution not found")
    return institution_profile(db, institution_id)


@router.post("/deposits", status_code=201)
def create_deposit(body: schemas.DepositInput, user=Depends(current_user), db=Depends(get_db)):
    require_roles(user, "institution")
    programme = db.get(Programme, body.programme_id)
    if not programme or programme.institution_id != user.institution_id:
        raise HTTPException(404, "Programme not found")
    institution = db.get(Institution, user.institution_id)
    requirement = calculate(db, institution, programme)
    reject_duplicate(db, body)
    deposit = SecurityDeposit(institution_id=institution.id, programme_id=programme.id, reference="DF-" + str(utcnow().year) + "-" + secrets.token_hex(3).upper(),
                              rule_version_id=requirement["rule_version_id"], required_amount=requirement["required_amount"], requirement_snapshot=requirement,
                              regulatory_end_date=body.regulatory_end_date, renewal_due_date=body.renewal_due_date, submitted_by=user.id)
    db.add(deposit)
    db.flush()
    db.add(Instrument(deposit_id=deposit.id, **body.model_dump(exclude={"programme_id", "regulatory_end_date", "renewal_due_date"})))
    audit(db, user, "deposit_draft_created", deposit.id, deposit.institution_id, after={"reference": deposit.reference})
    db.commit()
    return deposit_detail(db, deposit, user)


@router.get("/deposits/{deposit_id}")
def detail(deposit_id: str, user=Depends(current_user), db=Depends(get_db)):
    return deposit_detail(db, get_deposit(db, user, deposit_id), user)


@router.patch("/deposits/{deposit_id}/instrument")
def update_instrument(deposit_id: str, body: schemas.InstrumentInput, user=Depends(current_user), db=Depends(get_db)):
    deposit = get_deposit(db, user, deposit_id, lock=True)
    require_owner(user, deposit)
    if deposit.status not in ("draft", "clarification_required"):
        raise HTTPException(409, "An officer must request clarification before submitted details can be changed")
    reject_duplicate(db, body, deposit.id)
    inst = current_instrument(db, deposit.id)
    before = record(inst)
    for key, value in body.model_dump().items():
        setattr(inst, key, value)
    inst.verification_status = "pending"
    audit(db, user, "submitted_fields_corrected", deposit.id, deposit.institution_id, before, record(inst))
    detect(db, deposit)
    db.commit()
    return deposit_detail(db, deposit, user)


@router.post("/deposits/{deposit_id}/submit")
def submit(deposit_id: str, user=Depends(current_user), db=Depends(get_db)):
    deposit = get_deposit(db, user, deposit_id, lock=True)
    require_owner(user, deposit)
    if deposit.status not in ("draft", "clarification_required"):
        raise HTTPException(409, "This case has already been submitted")
    inst = current_instrument(db, deposit.id)
    if not db.scalar(select(Document.id).where(Document.instrument_id == inst.id, Document.category == "instrument")):
        raise HTTPException(422, "Upload an instrument document before submission")
    deposit.status, deposit.submitted_at = "submitted", utcnow()
    detect(db, deposit)
    audit(db, user, "deposit_submitted", deposit.id, deposit.institution_id, after={"reference": deposit.reference})
    db.commit()
    return deposit_detail(db, deposit, user)


@router.post("/deposits/{deposit_id}/documents", status_code=201)
async def upload(deposit_id: str, background_tasks: BackgroundTasks, file: UploadFile = File(...),
                 category: Literal["instrument", "bank_confirmation", "release_request", "affidavit", "approval_letter", "supporting"] = Form("instrument"),
                 user=Depends(current_user), db=Depends(get_db)):
    deposit = get_deposit(db, user, deposit_id, lock=True)
    require_roles(user, "institution", "verification")
    if user.role == "institution" and category == "bank_confirmation":
        raise HTTPException(403, "Only authorised officers may record independent bank confirmations")
    if deposit.status in ("released", "release_authorised"):
        raise HTTPException(409, "An authorised or completed case cannot accept new documents")
    rate_limit("upload:" + user.id, 20)
    data = await file.read(settings.max_upload_bytes + 1)
    filename = Path((file.filename or "document").replace("\\", "/")).name[:180]
    content_type, scan_status = validate_file(data, filename)
    sha = hashlib.sha256(data).hexdigest()
    reused = db.scalar(select(Document.id).where(Document.sha256 == sha, Document.deposit_id != deposit.id))
    inst = current_instrument(db, deposit.id)
    doc = Document(deposit_id=deposit.id, instrument_id=inst.id if category == "instrument" else None,
                   filename=filename, content_type=content_type, size=len(data), sha256=sha, storage_key=store.put(data),
                   category=category, scan_status=scan_status, uploaded_by=user.id)
    db.add(doc)
    db.flush()
    if reused:
        flag(db, deposit, "reused_document:" + sha, "This document fingerprint also occurs in another submission. An authorised officer must investigate reuse.", "high", source="document_hash", instrument_id=inst.id)
        assess(db, deposit)
    audit(db, user, "document_uploaded", deposit.id, deposit.institution_id, after={"document_id": doc.id, "filename": filename, "category": category, "sha256": sha})
    db.commit()
    dispatch(doc.id, background_tasks)
    return record(doc)


@router.post("/documents/{document_id}/retry")
def retry_extraction(document_id: str, background_tasks: BackgroundTasks, user=Depends(current_user), db=Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    deposit = get_deposit(db, user, doc.deposit_id, lock=True)
    db.refresh(doc)
    require_roles(user, "institution", "verification")
    if doc.processing_status != "failed":
        raise HTTPException(409, "Only failed extraction jobs can be retried")
    if deposit.status in ('release_authorised', 'released'):
        raise HTTPException(409, 'Authorised cases cannot restart extraction')
    doc.processing_status = 'queued'
    doc.processing_attempts = 0
    doc.processing_error = None
    doc.processing_token = None
    doc.next_attempt_at = None
    audit(db, user, "ocr_retry_requested", deposit.id, deposit.institution_id, after={"document_id": doc.id})
    db.commit()
    dispatch(doc.id, background_tasks)
    return record(doc)


@router.get("/documents/{document_id}/access")
def document_access(document_id: str, user=Depends(current_user), db=Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    deposit = get_deposit(db, user, doc.deposit_id)
    token = jwt.encode({"sub": user.id, "doc": doc.id, "purpose": "document_access", "exp": utcnow() + timedelta(minutes=2)}, settings.secret_key, algorithm="HS256")
    audit(db, user, "document_access_granted", deposit.id, deposit.institution_id, after={"document_id": doc.id})
    db.commit()
    return {"url": f"/api/documents/{doc.id}/content?token={token}", "expires_in": 120}


@router.get("/documents/{document_id}/content")
def document_content(document_id: str, token: str, user=Depends(current_user), db=Depends(get_db)):
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"], options={"require": ["exp", "sub", "doc", "purpose"]})
        if claims["sub"] != user.id or claims["doc"] != document_id or claims["purpose"] != "document_access":
            raise ValueError()
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(403, "Document link has expired or is invalid")
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    get_deposit(db, user, doc.deposit_id)
    return Response(store.get(doc.storage_key), media_type=doc.content_type,
                    headers={"Content-Disposition": 'inline; filename="document' + (".pdf" if doc.content_type == "application/pdf" else ".png") + '"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/extractions/{extraction_id}/corrections")
def correction(extraction_id: str, body: schemas.Correction, user=Depends(current_user), db=Depends(get_db)):
    extraction = db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(404, "Extraction not found")
    doc = db.get(Document, extraction.document_id)
    deposit = get_deposit(db, user, doc.deposit_id, lock=True)
    require_roles(user, "institution", "verification")
    if deposit.status in ("released", "release_authorised"):
        raise HTTPException(409, "Authorised cases cannot be edited")
    item = FieldCorrection(extraction_id=extraction.id, field=body.field, corrected_value=body.corrected_value, reason=body.reason,
                           original_value=str(extraction.fields.get(body.field, "")), actor_id=user.id)
    db.add(item)
    audit(db, user, "extracted_field_corrected", deposit.id, deposit.institution_id, before={body.field: item.original_value}, after={body.field: body.corrected_value, "reason": body.reason})
    detect(db, deposit)
    db.commit()
    return record(item)


@router.post("/deposits/{deposit_id}/replace", status_code=201)
def replace(deposit_id: str, body: schemas.ReplacementInput, user=Depends(current_user), db=Depends(get_db)):
    deposit = get_deposit(db, user, deposit_id, lock=True)
    require_owner(user, deposit)
    if deposit.status in ("released", "release_authorised", "draft") or db.scalar(select(ReleaseRequest.id).where(ReleaseRequest.deposit_id == deposit.id)):
        raise HTTPException(409, "Replacement requires a submitted case without an existing release workflow")
    reject_duplicate(db, body, deposit.id)
    previous = current_instrument(db, deposit.id)
    replacement = Instrument(deposit_id=deposit.id, **body.model_dump(exclude={"reason"}))
    previous.status = "replaced"
    db.add(replacement)
    db.flush()
    db.add(Replacement(deposit_id=deposit.id, previous_id=previous.id, replacement_id=replacement.id, reason=body.reason, actor_id=user.id))
    deposit.status = "clarification_required"
    audit(db, user, "instrument_replaced", deposit.id, deposit.institution_id, before={"instrument_id": previous.id}, after={"instrument_id": replacement.id, "reason": body.reason})
    detect(db, deposit)
    db.commit()
    return deposit_detail(db, deposit, user)

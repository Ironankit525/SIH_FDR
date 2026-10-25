from datetime import date, datetime, timezone
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from .models import (Institution, Programme, Instrument, Document, Extraction, FieldCorrection,
                     Discrepancy, VerificationRequest, VerificationEvidence, Replacement, ReleaseRequest, Clearance, AuditLog, User)
from .workflows import current_instrument, release_blockers, release_reviewers, configuration, DEFAULT_WORKFLOW
from .config import settings


def record(obj, exclude=()):
    if obj is None:
        return None
    excluded = set(exclude) | {"password_hash", "storage_key", "token_hash", "csrf_token", "processing_token"}
    values = {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in excluded}
    for key, value in values.items():
        if isinstance(value, datetime) and value.tzinfo is None:
            values[key] = value.replace(tzinfo=timezone.utc)
    return jsonable_encoder(values)


def deposit_summary(db, deposit):
    result = record(deposit)
    institution = db.get(Institution, deposit.institution_id)
    programme = db.get(Programme, deposit.programme_id)
    inst = current_instrument(db, deposit.id)
    result.update(institution_name=institution.name, institution_code=institution.code, programme=programme.name,
                  instrument=record(inst), days_to_maturity=(inst.maturity_date - date.today()).days if inst else None,
                  open_discrepancies=len(db.scalars(select(Discrepancy.id).where(Discrepancy.deposit_id == deposit.id, Discrepancy.status != "resolved")).all()))
    return result


def deposit_detail(db, deposit):
    result = deposit_summary(db, deposit)
    result["instruments"] = [record(i) for i in db.scalars(select(Instrument).where(Instrument.deposit_id == deposit.id).order_by(Instrument.created_at)).all()]
    documents = db.scalars(select(Document).where(Document.deposit_id == deposit.id).order_by(Document.created_at)).all()
    result["documents"] = []
    for doc in documents:
        item = record(doc)
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc.id))
        item["extraction"] = record(extraction)
        item["corrections"] = [record(c) for c in db.scalars(select(FieldCorrection).where(FieldCorrection.extraction_id == extraction.id).order_by(FieldCorrection.created_at)).all()] if extraction else []
        result["documents"].append(item)
    result["discrepancies"] = [record(i) for i in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id).order_by(Discrepancy.created_at.desc())).all()]
    result["verifications"] = []
    for request in db.scalars(select(VerificationRequest).where(VerificationRequest.deposit_id == deposit.id).order_by(VerificationRequest.created_at.desc())).all():
        item = record(request)
        item["evidence"] = record(db.scalar(select(VerificationEvidence).where(VerificationEvidence.request_id == request.id)))
        result["verifications"].append(item)
    result["replacements"] = [record(i) for i in db.scalars(select(Replacement).where(Replacement.deposit_id == deposit.id)).all()]
    release = db.scalar(select(ReleaseRequest).where(ReleaseRequest.deposit_id == deposit.id))
    workflow = release.workflow_snapshot if release else configuration(db, 'workflow', DEFAULT_WORKFLOW)
    result['mock_verification_permitted'] = bool(workflow.get('allow_mock_for_demo') and settings.environment != 'production')
    result["release"] = release_detail(db, deposit, release) if release else None
    result["timeline"] = [audit_record(db, i) for i in db.scalars(select(AuditLog).where(AuditLog.entity_id == deposit.id).order_by(AuditLog.created_at.desc())).all()]
    return result


def release_detail(db, deposit, release):
    result = record(release)
    result["reference"] = deposit.reference
    result["institution_name"] = db.get(Institution, deposit.institution_id).name
    result["clearances"] = [record(c) for c in db.scalars(select(Clearance).where(Clearance.release_id == release.id)).all()]
    result["blockers"] = release_blockers(db, deposit, release)
    result['reviewer_ids'] = release_reviewers(db, deposit, release)
    return result


def audit_record(db, item):
    result = record(item)
    actor = db.get(User, item.actor_id) if item.actor_id else None
    result["actor_name"] = actor.name if actor else "System"
    return result

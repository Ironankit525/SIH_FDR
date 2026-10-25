from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from .audit import audit
from .models import (Instrument, Document, Extraction, FieldCorrection, Discrepancy, Configuration,
                     SecurityDeposit, Notification, ReleaseRequest, Clearance, VerificationRequest, VerificationEvidence, AuditLog)


def current_instrument(db, deposit_id):
    return db.scalar(select(Instrument).where(Instrument.deposit_id == deposit_id, Instrument.status != "replaced").order_by(Instrument.created_at.desc()).limit(1))


def flag(db, deposit, code, description, severity="warning", fields=None, source="automated_check", next_step="Review the evidence and record a reasoned resolution.", instrument_id=None):
    existing = db.scalar(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.code == code))
    if existing:
        return existing
    item = Discrepancy(deposit_id=deposit.id, instrument_id=instrument_id, code=code, description=description,
                       severity=severity, fields=fields or [], evidence_source=source, next_step=next_step,
                       assigned_officer_id=deposit.assigned_officer_id)
    db.add(item)
    audit(db, None, "discrepancy_flagged", deposit.id, deposit.institution_id, after={"code": code, "description": description})
    return item


def detect(db, deposit):
    inst = current_instrument(db, deposit.id)
    if not inst:
        return
    docs = db.scalars(select(Document).where(Document.instrument_id == inst.id, Document.category == "instrument")).all()
    suffix = ":" + inst.id
    if not docs:
        flag(db, deposit, "missing_document" + suffix, "No instrument document has been uploaded.", "high", source="document_inventory", next_step="Upload the bank-issued instrument document.", instrument_id=inst.id)
    if deposit.required_amount is not None and float(inst.amount) < float(deposit.required_amount):
        flag(db, deposit, "amount_shortfall" + suffix, f"Submitted INR {float(inst.amount):,.0f} is below the configured requirement of INR {float(deposit.required_amount):,.0f}. Check rule applicability.", "high", ["amount"], "configured_rule", "Provide sufficient security or an authorised explanation of the applicable requirement.", inst.id)
    if deposit.requirement_snapshot.get("manual_review"):
        flag(db, deposit, "rule_review" + suffix, "Requirement applicability needs officer review; the seeded rule is illustrative or incomplete.", "warning", source="configured_rule", instrument_id=inst.id)
    if inst.maturity_date <= date.today():
        flag(db, deposit, "matured" + suffix, "The bank maturity date has been reached. This does not establish release eligibility.", "warning", ["maturity_date"], "submitted_information", instrument_id=inst.id)
    if inst.verification_status == "pending":
        flag(db, deposit, "unverified" + suffix, "No bank verification finding has been recorded.", "warning", source="verification_history", next_step="Request authorised verification or run the labelled demo adapter.", instrument_id=inst.id)
    for doc in docs:
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc.id))
        if not extraction:
            continue
        fields = dict(extraction.fields)
        corrections = db.scalars(select(FieldCorrection).where(FieldCorrection.extraction_id == extraction.id).order_by(FieldCorrection.created_at)).all()
        for correction in corrections:
            fields[correction.field] = correction.corrected_value
        for key in ("bank", "number", "depositor_name", "amount", "issue_date", "maturity_date"):
            if key not in fields:
                flag(db, deposit, f"extraction_missing_{key}:{doc.id}", f"The document parser could not extract {key.replace('_', ' ')}.", fields=[key], source="document_extraction", next_step="Inspect the original document and record a correction with a reason.", instrument_id=inst.id)
                continue
            submitted = getattr(inst, key)
            extracted = fields[key]
            if key == "amount":
                try:
                    equal = Decimal(str(submitted)) == Decimal(str(extracted).replace(',', ''))
                except (InvalidOperation, ValueError):
                    equal = False
            else:
                equal = str(submitted).strip().casefold() == str(extracted).strip().casefold()
            if not equal:
                flag(db, deposit, f"mismatch_{key}:{doc.id}", f"Submitted {key.replace('_', ' ')} ({submitted}) differs from document evidence ({extracted}).", "high", [key], "submitted_vs_extracted", "Compare the original receipt, correct any transcription error and ask an officer to resolve the flag.", inst.id)


def configuration(db, key, default):
    item = db.get(Configuration, key)
    return item.value if item else default


DEFAULT_WORKFLOW = {"cells": ["PGRC", "Vigilance"], "required_documents": ["release_request", "affidavit", "approval_letter"], "allow_mock_for_demo": True, "require_regulatory_end": True}
DEFAULT_ALERTS = {"reminder_days": [90, 60, 30, 7, 0], "escalation_days": 7}


def release_reviewers(db, deposit, release):
    actions = ['officer_assigned', 'scrutiny_observation', 'clarification_requested',
               'discrepancy_resolved', 'mock_verification_recorded', 'bank_evidence_received',
               'clearance_decided', 'extracted_field_corrected']
    actors = set(db.scalars(select(AuditLog.actor_id).where(AuditLog.entity_id == deposit.id,
                           AuditLog.action.in_(actions), AuditLog.actor_id.is_not(None))).all())
    actors.update([deposit.assigned_officer_id, deposit.submitted_by, release.requested_by])
    return sorted(actor for actor in actors if actor)


def release_blockers(db, deposit, release):
    from .config import settings
    workflow = release.workflow_snapshot
    blockers = []
    instrument = current_instrument(db, deposit.id)
    valid_verification = ["officially_confirmed"]
    if workflow.get("allow_mock_for_demo") and settings.environment != "production":
        valid_verification.append("mock_confirmed")
    if not instrument or instrument.verification_status not in valid_verification:
        blockers.append("A permitted bank verification finding is required.")
    if workflow.get("require_regulatory_end") and (not deposit.regulatory_end_date or deposit.regulatory_end_date > date.today()):
        blockers.append("The regulatory security period has not been established as complete.")
    docs = db.scalars(select(Document).where(Document.deposit_id == deposit.id)).all()
    instrument_docs = [doc for doc in docs if instrument and doc.instrument_id == instrument.id and doc.category == 'instrument']
    if not instrument_docs:
        blockers.append('The current instrument receipt is missing.')
    if any(doc.processing_status in ('queued', 'processing') for doc in instrument_docs):
        blockers.append('Instrument document extraction is still in progress.')
    categories = {d.category for d in docs}
    for required in workflow.get("required_documents", []):
        if required not in categories:
            blockers.append(f"Missing required document: {required.replace('_', ' ')}.")
    unresolved = db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.status != "resolved")).all()
    if unresolved:
        blockers.append(f"{len(unresolved)} discrepancy or review task(s) remain unresolved.")
    clearances = db.scalars(select(Clearance).where(Clearance.release_id == release.id)).all()
    recorded_cells = {item.cell for item in clearances}
    for cell in workflow.get('cells', []):
        if cell not in recorded_cells:
            blockers.append(f'{cell} clearance is missing.')
    for item in clearances:
        if item.status != "approved":
            blockers.append(f"{item.cell} clearance is {item.status.replace('_', ' ')}.")
    if deposit.status == "draft":
        blockers.append("The deposit has not been submitted.")
    return blockers


def monitor(db, today=None):
    """Deduplicated reminders and escalations; daily date bucket, no duplicate emails."""
    today = today or date.today()
    config = configuration(db, "alerts", DEFAULT_ALERTS)
    created = 0
    deposits = db.scalars(select(SecurityDeposit).where(SecurityDeposit.status.not_in(["draft", "released"]))).all()
    for deposit in deposits:
        inst = current_instrument(db, deposit.id)
        if not inst:
            continue
        deadlines = {"bank_maturity": inst.maturity_date, "validity": inst.validity_date,
                     "renewal_action": deposit.renewal_due_date, "regulatory_period": deposit.regulatory_end_date}
        for kind, deadline in deadlines.items():
            if not deadline:
                continue
            days = (deadline - today).days
            offsets = sorted(config["reminder_days"])
            stage = "overdue" if days < 0 else next((str(n) for n in offsets if days <= n), None)
            if stage is None:
                continue
            # Weekly escalation buckets apply to overdue actions, preserving alert history.
            if days < -config["escalation_days"]:
                stage += ":" + str(abs(days) // config["escalation_days"])
            key = f"{inst.id}:{kind}:{deadline}:{stage}"
            if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
                continue
            title = f"{kind.replace('_', ' ').title()} {'overdue' if days < 0 else f'in {days} days'}"
            db.add(Notification(institution_id=deposit.institution_id, deposit_id=deposit.id, dedupe_key=key,
                                title=title, body=f"{deposit.reference}: {kind.replace('_', ' ')} date is {deadline}. Review the required next action; maturity does not authorise release."))
            audit(db, None, "deadline_notification_created", deposit.id, deposit.institution_id, after={"deadline": str(deadline), "kind": kind, "stage": stage})
            created += 1
    db.commit()
    return created

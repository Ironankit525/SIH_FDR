from datetime import date, timedelta
from sqlalchemy import func, select
from .audit import audit
from .consistency import maturity_problem
from .matching import (mentions_aicte, names_match, normalise_bank, normalise_number, same_amount, same_bank, same_name, same_reference,
                       same_text)
from .models import (Instrument, Institution, Document, Extraction, FieldCorrection, Discrepancy, Configuration, Replacement,
                     SecurityDeposit, Notification, ReleaseRequest, Clearance, VerificationRequest, VerificationEvidence, AuditLog)


def current_instrument(db, deposit_id):
    return db.scalar(select(Instrument).where(Instrument.deposit_id == deposit_id, Instrument.status != "replaced").order_by(Instrument.created_at.desc()).limit(1))


def flag(db, deposit, code, description, severity="warning", fields=None, source="automated_check", next_step="Review the evidence and record a reasoned resolution.", instrument_id=None):
    existing = db.scalar(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.code == code))
    if existing:
        # A resolution covers the evidence it was given. Different evidence, or a recurrence after
        # automatic clearing, reopens the task rather than being silently absorbed.
        if existing.status == "resolved" and (existing.resolution_kind == "automatic" or existing.description != description):
            before = {"status": existing.status, "description": existing.description, "resolution": existing.resolution,
                      "resolution_kind": existing.resolution_kind, "resolved_by": existing.resolved_by, "confirmed_by": existing.confirmed_by}
            existing.status, existing.response, existing.resolution = "open", "", ""
            existing.resolution_kind = existing.resolved_by = existing.confirmed_by = None
            existing.description, existing.severity, existing.assigned_officer_id = description, severity, deposit.assigned_officer_id
            audit(db, None, "discrepancy_reopened", deposit.id, deposit.institution_id, before, {"code": code, "description": description})
        elif existing.status != "resolved" and existing.description != description:
            audit(db, None, "discrepancy_evidence_changed", deposit.id, deposit.institution_id,
                  {"code": code, "description": existing.description}, {"code": code, "description": description})
            existing.description = description
        existing.condition_active = True
        return existing
    item = Discrepancy(deposit_id=deposit.id, instrument_id=instrument_id, code=code, description=description,
                       severity=severity, fields=fields or [], evidence_source=source, next_step=next_step,
                       assigned_officer_id=deposit.assigned_officer_id)
    db.add(item)
    audit(db, None, "discrepancy_flagged", deposit.id, deposit.institution_id, after={"code": code, "description": description})
    return item


DETECTOR_CODES = {"missing_document", "amount_shortfall", "rule_review", "matured", "unverified", "coverage_gap", "coverage_lapsed",
                  "depositor_not_institution", "lien_not_aicte", "lien_document_conflict", "duplicate_reference",
                  "duplicate_number_other_bank", "extracted_number_elsewhere", "reused_text", "maturity_value_inconsistent",
                  "bank_confirmed_mismatch"}
DETECTOR_PREFIXES = ("extraction_missing_", "mismatch_", "forensic_")


def detector_owned(code):
    base = code.split(":", 1)[0]
    return base in DETECTOR_CODES or base.startswith(DETECTOR_PREFIXES)


def reconcile(db, deposit, raised):
    """Close automated warnings whose condition is gone; high-severity tasks keep needing an officer."""
    for item in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id)).all():
        if not detector_owned(item.code) or item.code in raised:
            continue
        if item.status == "resolved":
            item.condition_active = False  # the risk score stops counting resolved warnings that no longer apply
            continue
        if item.severity == "high":
            if item.condition_active:
                item.condition_active = False
                audit(db, None, "discrepancy_condition_cleared", deposit.id, deposit.institution_id, after={"code": item.code, "discrepancy_id": item.id})
            continue
        item.status, item.resolution_kind, item.condition_active = "resolved", "automatic", False
        item.resolution = "Automatically cleared: the check no longer detects this condition on the current evidence."
        audit(db, None, "discrepancy_auto_cleared", deposit.id, deposit.institution_id, after={"code": item.code, "discrepancy_id": item.id})


def instrument_conflicts(db, bank, number, exclude_deposit_id=None):
    """Instruments in other deposits whose normalised reference matches: (same bank, different bank)."""
    query = select(Instrument).where(Instrument.number_key == normalise_number(number))
    if exclude_deposit_id:
        query = query.where(Instrument.deposit_id != exclude_deposit_id)
    same, other = [], []
    for item in db.scalars(query).all():
        (same if item.bank_key == normalise_bank(bank) else other).append(item)
    return same, other


def corrected_fields(db, extraction):
    fields = dict(extraction.fields)
    for correction in db.scalars(select(FieldCorrection).where(FieldCorrection.extraction_id == extraction.id).order_by(FieldCorrection.created_at)).all():
        fields[correction.field] = correction.corrected_value
    return fields


def detect(db, deposit):
    inst = current_instrument(db, deposit.id)
    if not inst:
        return
    raised = set()

    def raise_flag(code, *args, **kwargs):
        raised.add(code)
        return flag(db, deposit, code, *args, instrument_id=inst.id, **kwargs)

    workflow = configuration(db, "workflow", DEFAULT_WORKFLOW)
    institution = db.get(Institution, deposit.institution_id)
    docs = db.scalars(select(Document).where(Document.instrument_id == inst.id, Document.category == "instrument")).all()
    suffix = ":" + inst.id
    today = date.today()
    if not docs:
        raise_flag("missing_document" + suffix, "No instrument document has been uploaded.", "high", source="document_inventory", next_step="Upload the bank-issued instrument document.")
    if deposit.required_amount is not None and float(inst.amount) < float(deposit.required_amount):
        raise_flag("amount_shortfall" + suffix, f"Submitted INR {float(inst.amount):,.0f} is below the configured requirement of INR {float(deposit.required_amount):,.0f}. Check rule applicability.", "high", ["amount"], "configured_rule", "Provide sufficient security or an authorised explanation of the applicable requirement.")
    if deposit.requirement_snapshot.get("manual_review"):
        raise_flag("rule_review" + suffix, "Requirement applicability needs officer review; the seeded rule is illustrative or incomplete.", "warning", source="configured_rule")
    if inst.maturity_date <= today:
        raise_flag("matured" + suffix, "The bank maturity date has been reached. This does not establish release eligibility.", "warning", ["maturity_date"], "submitted_information")
    if inst.verification_status == "pending":
        raise_flag("unverified" + suffix, "No bank verification finding has been recorded.", "warning", source="verification_history", next_step="Request authorised verification or run the labelled demo adapter.")
    # The instrument must secure the whole obligation; one that matures earlier needs a renewal in time.
    if deposit.regulatory_end_date and inst.maturity_date < deposit.regulatory_end_date:
        if inst.maturity_date <= today:
            raise_flag("coverage_lapsed" + suffix, f"The instrument matured on {inst.maturity_date}, before the security period ends on {deposit.regulatory_end_date}. The obligation has no current security.", "high", ["maturity_date"], "coverage_check", "Obtain a renewed or replacement instrument and record it on this case.")
        elif (inst.maturity_date - today).days <= workflow.get("coverage_warning_days", 60):
            raise_flag("coverage_gap" + suffix, f"The instrument matures on {inst.maturity_date}, before the security period ends on {deposit.regulatory_end_date}. A renewal is needed before maturity.", "warning", ["maturity_date"], "coverage_check", "Ask the institution to renew or replace the instrument before it matures.")
    if not names_match(inst.depositor_name, institution.name):
        raise_flag("depositor_not_institution" + suffix, f"The depositor '{inst.depositor_name}' does not match the institution '{institution.name}'. A trust or society holding needs documentary support.", "high", ["depositor_name"], "identity_check", "Confirm the legal relationship between the depositor and the institution, or require an instrument in the institution's name.")
    same, other = instrument_conflicts(db, inst.bank, inst.number, deposit.id)
    if same:
        raise_flag("duplicate_reference" + suffix, f"Reference {inst.number} at {inst.bank} matches an instrument already recorded on another case ({same[0].number}, {same[0].bank}).", "high", ["number", "bank"], "duplicate_check", "Establish whether the same instrument is pledged twice.")
    if other:
        raise_flag("duplicate_number_other_bank" + suffix, f"Reference {inst.number} also appears on another case at a different bank ({other[0].bank}).", "warning", ["number"], "duplicate_check", "Confirm the issuing bank with the original document.")
    lien_required = workflow.get("require_aicte_lien", True)
    document_liens = []
    for doc in docs:
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc.id))
        if not extraction:
            continue
        fields = corrected_fields(db, extraction)
        for key in ("bank", "number", "depositor_name", "amount", "issue_date", "maturity_date"):
            if key not in fields:
                raise_flag(f"extraction_missing_{key}:{doc.id}", f"The document parser could not extract {key.replace('_', ' ')}.", fields=[key], source="document_extraction", next_step="Inspect the original document and record a correction with a reason.")
                continue
            submitted = getattr(inst, key)
            extracted = fields[key]
            # Formatting and abbreviations are not discrepancies; OCR letter/digit confusions are not either.
            compare = {"amount": same_amount, "bank": same_bank, "depositor_name": same_name,
                       "number": lambda a, b: same_reference(a, b, ocr=extraction.method != "embedded_pdf_text")}.get(key, same_text)
            equal = compare(submitted, extracted)
            if not equal:
                raise_flag(f"mismatch_{key}:{doc.id}", f"Submitted {key.replace('_', ' ')} ({submitted}) differs from document evidence ({extracted}).", "high", [key], "submitted_vs_extracted", "Compare the original receipt, correct any transcription error and ask an officer to resolve the flag.")
        if all(key in fields for key in ("amount", "maturity_value", "issue_date", "maturity_date")):
            try:
                problem = maturity_problem(fields["amount"], fields["maturity_value"], fields["issue_date"], fields["maturity_date"], fields.get("rate"))
            except (TypeError, ValueError):
                problem = None
            if problem:
                raise_flag(f"maturity_value_inconsistent:{doc.id}", problem, "high", ["amount", "maturity_date"], "document_arithmetic",
                           "Ask the bank to confirm principal, rate and maturity date; a changed principal or date usually leaves the printed maturity value behind.")
        if fields.get("lien"):
            document_liens.append(fields["lien"])
            if lien_required and not mentions_aicte(fields["lien"]):
                raise_flag(f"lien_document_conflict:{doc.id}", f"The document records the lien as '{fields['lien']}', which does not name AICTE.", "high", ["lien_details"], "document_extraction", "Obtain an instrument with the lien marked in favour of AICTE.")
        if "number" in fields:
            hits = db.scalars(select(Instrument).where(Instrument.number_key == normalise_number(fields["number"]),
                                                       Instrument.deposit_id != deposit.id, Instrument.created_at < doc.created_at)).all()
            if hits:
                raise_flag(f"extracted_number_elsewhere:{doc.id}", f"The document's reference {fields['number']} matches instrument {hits[0].number} recorded on another case.", "high", ["number"], "duplicate_check", "Establish whether one receipt has been submitted for more than one obligation.")
        if extraction.text_fingerprint and db.scalar(select(Document.id).join(Extraction, Extraction.document_id == Document.id).where(
                Extraction.text_fingerprint == extraction.text_fingerprint, Document.deposit_id != deposit.id, Document.category == "instrument",
                Document.created_at < doc.created_at, Document.sha256 != doc.sha256).limit(1)):
                raise_flag(f"reused_text:{doc.id}", "This document's text is identical to an instrument document on another case, although the file differs. It may be a re-saved or re-scanned copy.", "high", source="document_text_fingerprint", next_step="Compare both originals and confirm each instrument independently with the bank.")
        for item in (doc.forensics or {}).get("signals", []):
            raise_flag(f"forensic_{item['code']}:{doc.id}", item["detail"], item["severity"], source="document_forensics", next_step="Inspect the original document and confirm the instrument through an authorised bank channel.")
    # What the bank itself confirmed must agree with the declaration; an officer's "confirmed" alone does not settle it.
    official = db.scalar(select(VerificationEvidence).join(VerificationRequest, VerificationEvidence.request_id == VerificationRequest.id)
                         .where(VerificationRequest.instrument_id == inst.id, VerificationEvidence.simulated.is_(False))
                         .order_by(VerificationEvidence.created_at.desc()).limit(1))
    if official and official.confirmed_fields:
        compare = {"amount": same_amount, "bank": same_bank, "depositor_name": same_name, "number": same_reference}
        differing = [f"{key.replace('_', ' ')} (bank: {value}; declared: {getattr(inst, key)})" for key, value in official.confirmed_fields.items()
                     if hasattr(inst, key) and not compare.get(key, same_text)(value, getattr(inst, key))]
        if differing:
            raise_flag(f"bank_confirmed_mismatch:{official.id}", "The bank's confirmation differs from the declaration: " + "; ".join(differing) + ".", "high",
                       [key for key in official.confirmed_fields if hasattr(inst, key)], "bank_confirmation",
                       "Resolve the difference with the bank before relying on this confirmation.")
    if lien_required and not (mentions_aicte(inst.lien_details) or mentions_aicte(inst.depositor_name) or any(map(mentions_aicte, document_liens))):
        raise_flag("lien_not_aicte" + suffix, "No lien or joint holding in favour of AICTE is declared or shown on the document.", "high", ["lien_details"], "lien_check", "Obtain confirmation that the lien is marked in favour of AICTE.")
    reconcile(db, deposit, raised)
    from .risk import assess
    assess(db, deposit)


def configuration(db, key, default):
    item = db.get(Configuration, key)
    return item.value if item else default


DEFAULT_WORKFLOW = {"cells": ["PGRC", "Vigilance"], "required_documents": ["release_request", "affidavit", "approval_letter"], "allow_mock_for_demo": True, "require_regulatory_end": True,
                    "verification_max_age_days": 30, "coverage_warning_days": 60, "require_aicte_lien": True}
DEFAULT_ALERTS = {"reminder_days": [90, 60, 30, 7, 0], "escalation_days": 7}


def release_reviewers(db, deposit, release):
    actions = ['officer_assigned', 'scrutiny_observation', 'clarification_requested',
               'discrepancy_resolved', 'discrepancy_resolution_proposed', 'discrepancy_resolution_confirmed',
               'discrepancy_resolution_rejected', 'mock_verification_recorded', 'bank_evidence_received',
               'clearance_decided', 'extracted_field_corrected']
    actors = set(db.scalars(select(AuditLog.actor_id).where(AuditLog.entity_id == deposit.id,
                           AuditLog.action.in_(actions), AuditLog.actor_id.is_not(None))).all())
    actors.update([deposit.assigned_officer_id, deposit.submitted_by, release.requested_by])
    return sorted(actor for actor in actors if actor)


RISK_CLEARANCE_CELL = "Vigilance"
CRITICAL_MAX_VERIFICATION_AGE = 7


def release_blockers(db, deposit, release):
    from .config import settings
    from .risk import latest as latest_risk
    workflow = release.workflow_snapshot
    blockers = []
    instrument = current_instrument(db, deposit.id)
    # Unlike the workflow snapshot, risk safeguards follow the current evidence. The wording stays
    # neutral because institutions read these blockers.
    assessment = latest_risk(db, deposit.id)
    level = assessment.level if assessment else "low"
    valid_verification = ["officially_confirmed"]
    mock_permitted = workflow.get("allow_mock_for_demo") and settings.environment != "production"
    if mock_permitted and level not in ("high", "critical"):
        valid_verification.append("mock_confirmed")
    if not instrument or instrument.verification_status not in valid_verification:
        if mock_permitted and instrument and instrument.verification_status == "mock_confirmed":
            blockers.append("An official bank confirmation is required for this case; simulated findings are not accepted.")
        else:
            blockers.append("A permitted bank verification finding is required.")
    else:
        # A confirmation shows the instrument existed then; it may have been closed early since.
        max_age = workflow.get("verification_max_age_days", DEFAULT_WORKFLOW["verification_max_age_days"])
        if level == "critical":
            max_age = min(max_age, CRITICAL_MAX_VERIFICATION_AGE)
        query = select(VerificationEvidence).join(VerificationRequest, VerificationEvidence.request_id == VerificationRequest.id).where(
            VerificationRequest.instrument_id == instrument.id, VerificationEvidence.finding == "confirmed")
        if "mock_confirmed" not in valid_verification:
            query = query.where(VerificationEvidence.simulated.is_(False))
        latest = db.scalar(query.order_by(VerificationEvidence.verified_on.desc()).limit(1))
        if not latest:
            blockers.append("No confirming bank evidence is recorded for the current instrument.")
        elif (date.today() - latest.verified_on).days > max_age:
            blockers.append(f"The latest bank confirmation is from {latest.verified_on}, more than {max_age} days ago. Obtain a fresh confirmation before release.")
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
    if level == "critical" and RISK_CLEARANCE_CELL not in recorded_cells:
        blockers.append(f"A {RISK_CLEARANCE_CELL} clearance is required for this case.")
    for item in clearances:
        if item.status != "approved":
            blockers.append(f"{item.cell} clearance is {item.status.replace('_', ' ')}.")
    if deposit.status == "draft":
        blockers.append("The deposit has not been submitted.")
    return blockers


def monitor(db, today=None, force_detection=False):
    """Deduplicated reminders and escalations; daily date bucket, no duplicate emails."""
    today = today or date.today()
    config = configuration(db, "alerts", DEFAULT_ALERTS)
    created = 0
    deposits = db.scalars(select(SecurityDeposit).where(SecurityDeposit.status.not_in(["draft", "released"]))).all()
    # Date-driven checks (maturity, coverage) change with time, not only with events: re-run them daily.
    sweep = db.get(Configuration, "detection_sweep")
    if force_detection or not sweep or sweep.value.get("last_run") != today.isoformat():
        for deposit in deposits:
            detect(db, deposit)
        if sweep:
            sweep.value = {"last_run": today.isoformat()}
        else:
            db.add(Configuration(key="detection_sweep", value={"last_run": today.isoformat()}))
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


def institution_profile(db, institution_id):
    """Case history for one institution, for officers weighing a new submission."""
    deposit_ids = db.scalars(select(SecurityDeposit.id).where(SecurityDeposit.institution_id == institution_id)).all()
    flags = db.scalars(select(Discrepancy).where(Discrepancy.deposit_id.in_(deposit_ids))).all()
    late = 0
    for item in db.scalars(select(Replacement).where(Replacement.deposit_id.in_(deposit_ids))).all():
        previous = db.get(Instrument, item.previous_id)
        if previous and item.created_at.date() > previous.maturity_date:
            late += 1
    findings = db.scalars(select(VerificationEvidence.finding).join(VerificationRequest, VerificationEvidence.request_id == VerificationRequest.id)
                          .where(VerificationRequest.deposit_id.in_(deposit_ids))).all()
    clarifications = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id.in_(deposit_ids), AuditLog.action == "clarification_requested"))
    return {"deposits": len(deposit_ids),
            "replacements": db.scalar(select(func.count()).select_from(Replacement).where(Replacement.deposit_id.in_(deposit_ids))),
            "late_renewals": late, "clarification_requests": clarifications,
            "review_tasks": len(flags), "high_severity_tasks": sum(f.severity == "high" for f in flags),
            "open_high_severity_tasks": sum(f.severity == "high" and f.status != "resolved" for f in flags),
            "duplicate_or_reuse_tasks": sum(f.code.split(":", 1)[0] in ("reused_document", "reused_text", "duplicate_reference", "extracted_number_elsewhere") for f in flags),
            "bank_findings_not_confirmed": sum(f != "confirmed" for f in findings), "bank_findings": len(findings)}

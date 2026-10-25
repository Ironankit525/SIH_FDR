"""Explainable risk score that orders review work. A score prompts scrutiny; it never establishes fraud.

Signals come from review tasks, so nothing raises the score without also being in front of an officer,
plus a few score-only observations (parser confidence, verification age, institution history).
"""
import hashlib
import json
from datetime import date
from math import prod

from sqlalchemy import select

from .audit import audit
from .models import (Clearance, Discrepancy, Document, Extraction, FieldCorrection, Instrument, Replacement, RiskAssessment,
                     ReleaseRequest, RiskWeightVersion, SecurityDeposit, VerificationEvidence, VerificationRequest)
from .workflows import DEFAULT_WORKFLOW, RISK_CLEARANCE_CELL, configuration, current_instrument

ENGINE_VERSION = "1.0.0"
CATEGORIES = ("identity", "document_integrity", "financial", "coverage", "duplication", "verification", "behaviour", "process")

# key: (category, default weight, evidence strength). Weights are policy and versioned; strength is how
# directly the evidence shows the problem and stays in code.
SIGNALS = {
    "forensic_text_layer_mismatch": ("document_integrity", 0.7, 0.85),  # OCR misreads remain possible
    "forensic_conflicting_values": ("document_integrity", 0.65, 1.0),
    "forensic_editing_software": ("document_integrity", 0.2, 1.0),
    "forensic_modified_after_creation": ("document_integrity", 0.15, 1.0),
    "forensic_incremental_update": ("document_integrity", 0.15, 1.0),
    "maturity_value_inconsistent": ("document_integrity", 0.55, 1.0),
    "low_parser_confidence": ("document_integrity", 0.1, 1.0),
    "extracted_number_elsewhere": ("duplication", 0.65, 1.0),
    "duplicate_reference": ("duplication", 0.6, 1.0),
    "reused_document": ("duplication", 0.5, 1.0),
    "reused_text": ("duplication", 0.5, 1.0),
    "duplicate_number_other_bank": ("duplication", 0.15, 1.0),
    "bank_mismatched": ("verification", 0.55, 1.0),
    "bank_confirmed_mismatch": ("verification", 0.6, 1.0),
    "bank_inconclusive": ("verification", 0.2, 1.0),
    "bank_pending": ("verification", 0.05, 1.0),
    "unverified": ("verification", 0.1, 1.0),
    "stale_verification": ("verification", 0.1, 1.0),
    "mismatch_amount": ("financial", 0.5, 1.0),
    "mismatch_maturity_date": ("financial", 0.5, 1.0),
    "mismatch_issue_date": ("financial", 0.3, 1.0),
    "mismatch_number": ("identity", 0.5, 1.0),
    "mismatch_depositor_name": ("identity", 0.35, 1.0),
    "mismatch_bank": ("identity", 0.35, 1.0),
    "depositor_not_institution": ("identity", 0.4, 1.0),
    "amount_shortfall": ("financial", 0.3, 1.0),
    "lien_document_conflict": ("financial", 0.5, 1.0),
    "lien_not_aicte": ("financial", 0.4, 1.0),
    "coverage_lapsed": ("coverage", 0.4, 1.0),
    "coverage_gap": ("coverage", 0.1, 1.0),
    "matured": ("coverage", 0.05, 1.0),
    "missing_document": ("process", 0.3, 1.0),
    "officer_clarification": ("process", 0.15, 1.0),
    "extraction_failed": ("process", 0.1, 1.0),
    "extraction_missing": ("process", 0.05, 1.0),
    "rule_review": ("process", 0.0, 1.0),  # about the rule, not the instrument
    "unclassified_high": ("process", 0.3, 1.0),
    "unclassified_warning": ("process", 0.1, 1.0),
    "history_duplication": ("behaviour", 0.15, 1.0),
    "history_bank_mismatch": ("behaviour", 0.15, 1.0),
    "history_open_high": ("behaviour", 0.1, 1.0),
    "history_late_renewal": ("behaviour", 0.05, 1.0),
}
# Weak, indirect evidence must not outweigh direct evidence however much of it accumulates.
# History alone stays below the medium threshold: it can add weight to direct evidence, never replace it.
DEFAULT_CAPS = {"behaviour": 0.15}
DEFAULT_THRESHOLDS = {"medium": 20, "high": 50, "critical": 80}
LOW_CONFIDENCE = 0.6
CRITICAL_FIELDS = ("number", "amount", "issue_date", "maturity_date")


def active_policy(db):
    item = db.scalar(select(RiskWeightVersion).where(RiskWeightVersion.status == "active").order_by(RiskWeightVersion.version.desc()).limit(1))
    weights = {key: weight for key, (_, weight, _) in SIGNALS.items()}
    if not item:
        return {"version": 0, "weights": weights, "category_caps": dict(DEFAULT_CAPS), "thresholds": dict(DEFAULT_THRESHOLDS)}
    return {"version": item.version, "weights": {**weights, **item.weights}, "category_caps": item.category_caps, "thresholds": item.thresholds}


def signal_key(code):
    base = code.split(":", 1)[0]
    if base.startswith("forensic_"):
        return next((key for key in SIGNALS if key.startswith("forensic_") and base.startswith(key)), None)
    if base.startswith("extraction_missing_"):
        return "extraction_missing"
    if base == "officer":
        return "officer_clarification"
    return base if base in SIGNALS else None


def bank_key(db, code):
    """Bank review tasks are weighted by what the bank actually reported."""
    kind, _, ref = code.partition(":")
    if kind == "manual_bank":
        finding = db.scalar(select(VerificationRequest.status).where(VerificationRequest.id == ref))
    else:
        finding = db.scalar(select(VerificationRequest.status).where(VerificationRequest.instrument_id == ref,
                            VerificationRequest.channel.startswith("SIMULATED")).order_by(VerificationRequest.created_at.desc()).limit(1))
    return {"mismatched": "bank_mismatched", "pending": "bank_pending"}.get(finding, "bank_inconclusive")


def discount(item):
    """How much of a task still counts, given what humans have done with it."""
    if item.status == "resolved":
        # A warning that no longer applies counts for nothing. A resolved high-severity finding keeps a
        # trace, so an institution that once submitted, say, a reused receipt remains slightly more visible.
        if item.resolution_kind == "automatic" or (not item.condition_active and item.severity != "high"):
            return 0.0
        return 0.1 if item.resolution_kind == "officer_confirmed" else 0.2
    if item.status == "resolution_proposed" or not item.condition_active:
        return 0.5
    return 1.0


def make_signal(key, policy, explanation, source, strength=None, discount_factor=1.0, task=None):
    category, _, default_strength = SIGNALS[key]
    return {"key": key, "category": category, "weight": policy["weights"][key],
            "strength": round(default_strength if strength is None else strength, 3), "discount": discount_factor,
            "explanation": explanation, "source": source, "task_id": task.id if task else None,
            "task_code": task.code if task else None, "task_status": task.status if task else None}


def reading_strength(db, item, key):
    """A mismatch is only as strong as the parser's reading of the document (an OCR reading is less certain)."""
    if not key.startswith("mismatch_"):
        return None
    document_id = item.code.partition(":")[2]
    extraction = db.scalar(select(Extraction).where(Extraction.document_id == document_id))
    field = key.removeprefix("mismatch_")
    if not extraction or field in set(db.scalars(select(FieldCorrection.field).where(FieldCorrection.extraction_id == extraction.id)).all()):
        return None  # a human-corrected reading carries no parser uncertainty
    return max(0.3, min(1.0, extraction.confidences.get(field, 1.0)))


def task_signals(db, deposit, policy):
    signals = []
    for item in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id).order_by(Discrepancy.created_at, Discrepancy.code)).all():
        base = item.code.split(":", 1)[0]
        key = bank_key(db, item.code) if base in ("mock_bank", "manual_bank") else signal_key(item.code)
        key = key or ("unclassified_high" if item.severity == "high" else "unclassified_warning")
        signals.append(make_signal(key, policy, item.description, item.evidence_source, strength=reading_strength(db, item, key),
                                   discount_factor=discount(item), task=item))
    return signals


def confidence_signals(db, inst, policy):
    weakest = None
    for doc in db.scalars(select(Document).where(Document.instrument_id == inst.id, Document.category == "instrument")).all():
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == doc.id))
        if not extraction:
            continue
        corrected = set(db.scalars(select(FieldCorrection.field).where(FieldCorrection.extraction_id == extraction.id)).all())
        for field in CRITICAL_FIELDS:
            value = extraction.confidences.get(field)
            if value is not None and field not in corrected and value < LOW_CONFIDENCE and (weakest is None or value < weakest[1]):
                weakest = (field, value)
    if not weakest:
        return []
    field, value = weakest
    return [make_signal("low_parser_confidence", policy, f"The document states the {field.replace('_', ' ')} unclearly (parser confidence {value:.2f}).",
                        "document_extraction", strength=1 - value)]


def verification_signals(db, deposit, inst, policy):
    if inst.verification_status not in ("officially_confirmed", "mock_confirmed"):
        return []
    max_age = configuration(db, "workflow", DEFAULT_WORKFLOW).get("verification_max_age_days", DEFAULT_WORKFLOW["verification_max_age_days"])
    latest = db.scalar(select(VerificationEvidence.verified_on).join(VerificationRequest, VerificationEvidence.request_id == VerificationRequest.id)
                       .where(VerificationRequest.instrument_id == inst.id, VerificationEvidence.finding == "confirmed")
                       .order_by(VerificationEvidence.verified_on.desc()).limit(1))
    if latest and (date.today() - latest).days > max_age:
        return [make_signal("stale_verification", policy, f"The latest bank confirmation is from {latest}; the instrument may have changed since.", "verification_history")]
    return []


def history_signals(db, deposit, policy):
    """The institution's other cases. Indirect, so weighted lightly and capped."""
    others = db.scalars(select(SecurityDeposit.id).where(SecurityDeposit.institution_id == deposit.institution_id, SecurityDeposit.id != deposit.id)).all()
    if not others:
        return []
    tasks = db.scalars(select(Discrepancy).where(Discrepancy.deposit_id.in_(others))).all()
    live = [t for t in tasks if t.resolution_kind != "automatic"]
    duplication = sum(t.code.split(":", 1)[0] in ("reused_document", "reused_text", "duplicate_reference", "extracted_number_elsewhere") for t in live)
    open_high = sum(t.severity == "high" and t.status != "resolved" for t in live)
    mismatched = len(db.scalars(select(VerificationRequest.id).where(VerificationRequest.deposit_id.in_(others), VerificationRequest.status == "mismatched")).all())
    late = 0
    for item in db.scalars(select(Replacement).where(Replacement.deposit_id.in_(others))).all():
        previous = db.get(Instrument, item.previous_id)
        late += bool(previous and item.created_at.date() > previous.maturity_date)
    found = [("history_duplication", duplication, 2, f"{duplication} duplicate or reuse task(s) on this institution's other cases."),
             ("history_bank_mismatch", mismatched, 2, f"{mismatched} bank finding(s) on other cases did not match the submission."),
             ("history_open_high", open_high, 3, f"{open_high} unresolved high-severity task(s) on other cases."),
             ("history_late_renewal", late, 3, f"{late} instrument(s) on other cases were renewed after maturity.")]
    return [make_signal(key, policy, text, "institution_history", strength=min(1.0, count / full)) for key, count, full, text in found if count]


def combine(signals, caps, thresholds):
    """score = 100 × (1 − Π over categories (1 − min(cap, 1 − Π(1 − weight × strength × discount))))."""
    def total(items):
        remaining = 1.0
        for category in CATEGORIES:
            group = [s for s in items if s["category"] == category]
            if group:
                chance = 1 - prod(1 - s["weight"] * s["strength"] * s["discount"] for s in group)
                remaining *= 1 - min(chance, caps.get(category, 1.0))
        return 100 * (1 - remaining)

    raw = total(signals)
    for item in signals:
        # Explanation: how far the score would fall without this signal.
        item["contribution"] = round(raw - total([s for s in signals if s is not item]), 1)
    # The level follows the score as displayed, so 20.0 is never shown as low.
    score = round(raw, 1)
    level = next((name for name in ("critical", "high", "medium") if score >= thresholds[name]), "low")
    return score, level


def evaluate(db, deposit, policy=None):
    policy = policy or active_policy(db)
    inst = current_instrument(db, deposit.id)
    signals = task_signals(db, deposit, policy)
    if inst:
        signals += confidence_signals(db, inst, policy) + verification_signals(db, deposit, inst, policy)
    signals += history_signals(db, deposit, policy)
    signals = [s for s in signals if s["weight"] * s["strength"] * s["discount"] > 0]
    score, level = combine(signals, policy["category_caps"], policy["thresholds"])
    signals.sort(key=lambda s: -s["contribution"])
    return {"score": score, "level": level, "signals": signals, "instrument_id": inst.id if inst else None, "weights_version": policy["version"]}


def latest(db, deposit_id):
    return db.scalar(select(RiskAssessment).where(RiskAssessment.deposit_id == deposit_id).order_by(RiskAssessment.created_at.desc()).limit(1))


def assess(db, deposit, policy=None):
    """Score the deposit inside the caller's transaction; store a new row only when the inputs changed."""
    result = evaluate(db, deposit, policy)
    scored = [(s["key"], s["task_id"], s["weight"], s["strength"], s["discount"]) for s in result["signals"]]
    digest = hashlib.sha256(json.dumps({"engine": ENGINE_VERSION, "weights": result["weights_version"], "instrument": result["instrument_id"],
                                        "signals": scored}, sort_keys=True).encode()).hexdigest()
    previous = latest(db, deposit.id)
    if previous and previous.inputs_digest == digest:
        return previous
    item = RiskAssessment(deposit_id=deposit.id, instrument_id=result["instrument_id"], score=result["score"], level=result["level"],
                          signals=result["signals"], engine_version=ENGINE_VERSION, weights_version=result["weights_version"], inputs_digest=digest)
    db.add(item)
    if result["level"] == "critical":
        require_risk_clearance(db, deposit)
    audit(db, None, "risk_assessed", deposit.id, deposit.institution_id,
          {"score": float(previous.score), "level": previous.level} if previous else {},
          {"score": result["score"], "level": result["level"], "engine_version": ENGINE_VERSION, "weights_version": result["weights_version"]})
    return item


def require_risk_clearance(db, deposit):
    """A critical case needs the risk clearance cell on its open release, even if the workflow omitted it."""
    release = db.scalar(select(ReleaseRequest).where(ReleaseRequest.deposit_id == deposit.id, ReleaseRequest.status.in_(["under_review", "returned"])))
    if not release or db.scalar(select(Clearance.id).where(Clearance.release_id == release.id, Clearance.cell == RISK_CLEARANCE_CELL)):
        return
    db.add(Clearance(release_id=release.id, cell=RISK_CLEARANCE_CELL))
    audit(db, None, "risk_clearance_required", deposit.id, deposit.institution_id, after={"release_id": release.id, "cell": RISK_CLEARANCE_CELL})

"""Suspicion score: how strongly the evidence suggests something is wrong with a case. 0 means nothing suspicious.

Only suspicion counts. Waiting for the bank, missing paperwork or an early maturity are statuses and requirements,
shown and enforced elsewhere, never points. Signals come from review tasks, so nothing raises the score without also
being in front of a reviewer; institution history only adds weight to a case that is already suspicious.
At the policy's high threshold the case is escalated to Vigilance (see escalate()).
"""
import hashlib
import json
from math import prod

from sqlalchemy import select

from .audit import audit
from .models import (Clearance, Discrepancy, Extraction, FieldCorrection, Instrument, Replacement, RiskAssessment, ReleaseRequest,
                     RiskWeightVersion, SecurityDeposit, VerificationEvidence, VerificationRequest, utcnow)
from .workflows import RISK_CLEARANCE_CELL, current_instrument, reopen_verification

ENGINE_VERSION = "2.0.0"
CATEGORIES = ("identity", "document_integrity", "financial", "duplication", "verification", "behaviour")

# key: (category, default weight, evidence strength). Weights are policy and versioned; strength is how
# directly the evidence shows the problem and stays in code.
SIGNALS = {
    "forensic_text_layer_mismatch": ("document_integrity", 0.7, 0.85),  # OCR misreads remain possible
    "forensic_conflicting_values": ("document_integrity", 0.65, 1.0),
    "forensic_editing_software": ("document_integrity", 0.2, 1.0),
    "forensic_modified_after_creation": ("document_integrity", 0.15, 1.0),
    "forensic_incremental_update": ("document_integrity", 0.15, 1.0),
    "maturity_value_inconsistent": ("document_integrity", 0.55, 1.0),
    "extracted_number_elsewhere": ("duplication", 0.65, 1.0),
    "duplicate_reference": ("duplication", 0.6, 1.0),
    "reused_document": ("duplication", 0.5, 1.0),
    "reused_text": ("duplication", 0.5, 1.0),
    "duplicate_number_other_bank": ("duplication", 0.15, 1.0),
    "bank_mismatched": ("verification", 0.55, 1.0),
    "bank_confirmed_mismatch": ("verification", 0.6, 1.0),
    "bank_no_record": ("verification", 0.55, 1.0),     # the bank has no such instrument
    "bank_inconclusive": ("verification", 0.2, 1.0),   # the bank could neither confirm nor deny
    "mismatch_amount": ("financial", 0.5, 1.0),
    "mismatch_maturity_date": ("financial", 0.5, 1.0),
    "mismatch_issue_date": ("financial", 0.3, 1.0),
    "mismatch_number": ("identity", 0.5, 1.0),
    "mismatch_depositor_name": ("identity", 0.35, 1.0),
    "mismatch_bank": ("identity", 0.35, 1.0),
    "lien_document_conflict": ("financial", 0.5, 1.0),
    "history_duplication": ("behaviour", 0.15, 1.0),
    "history_bank_mismatch": ("behaviour", 0.15, 1.0),
    "history_open_high": ("behaviour", 0.1, 1.0),
    "history_late_renewal": ("behaviour", 0.05, 1.0),
}
# Weak, indirect evidence must not outweigh direct evidence however much of it accumulates.
DEFAULT_CAPS = {"behaviour": 0.15}
DEFAULT_THRESHOLDS = {"medium": 20, "high": 50, "critical": 80}


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
    return base if base in SIGNALS and not base.startswith("history_") else None


def bank_key(db, code):
    """Bank review tasks are weighted by what the bank actually reported; "not yet answered" is not suspicion."""
    kind, _, ref = code.partition(":")
    query = select(VerificationRequest).where(VerificationRequest.id == ref) if kind == "manual_bank" else select(VerificationRequest).where(
        VerificationRequest.instrument_id == ref, VerificationRequest.channel.startswith("SIMULATED")).order_by(VerificationRequest.created_at.desc()).limit(1)
    request = db.scalar(query)
    if not request or request.status == "pending":
        return None
    if request.status == "mismatched":
        return "bank_mismatched"
    evidence = db.scalar(select(VerificationEvidence).where(VerificationEvidence.request_id == request.id))
    no_record = evidence is not None and evidence.simulated and not evidence.confirmed_fields
    return "bank_no_record" if no_record else "bank_inconclusive"


def suspicion_key(db, item):
    """The suspicion signal a review task carries, or None for paperwork and status tasks."""
    base = item.code.split(":", 1)[0]
    return bank_key(db, item.code) if base in ("mock_bank", "manual_bank") else signal_key(item.code)


def is_escalated(deposit):
    return bool(deposit.escalated_at and not deposit.vigilance_cleared_at)


def discount(item):
    """How much of a task still counts, given what humans have done with it."""
    if item.status == "resolved":
        # A warning that no longer applies counts for nothing. A resolved high-severity finding keeps a
        # trace, so an institution that once submitted, say, a reused receipt remains slightly more visible.
        if item.resolution_kind == "automatic" or (not item.condition_active and item.severity != "high"):
            return 0.0
        return 0.1 if item.resolution_kind in ("officer_confirmed", "vigilance") else 0.2
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
        key = suspicion_key(db, item)
        if key:
            signals.append(make_signal(key, policy, item.description, item.evidence_source, strength=reading_strength(db, item, key),
                                       discount_factor=discount(item), task=item))
    return signals


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

    if not signals:
        return 0.0, "none"
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
    signals = [s for s in task_signals(db, deposit, policy) if s["weight"] * s["strength"] * s["discount"] > 0]
    if signals:  # history adds weight to a suspicious case; it never makes a clean case suspicious
        signals += [s for s in history_signals(db, deposit, policy) if s["weight"] * s["strength"] > 0]
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
    escalate(db, deposit, result["score"], (policy or active_policy(db))["thresholds"]["high"])
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


def escalate(db, deposit, score, limit):
    """At or above the limit the suspicious findings go to Vigilance; the officer can no longer clear them alone."""
    if score < limit or is_escalated(deposit):
        return
    deposit.escalated_at, deposit.vigilance_cleared_at, deposit.vigilance_cleared_by = utcnow(), None, None
    reopen_verification(db, deposit, "Suspicion reached the escalation limit")
    audit(db, None, "escalated_to_vigilance", deposit.id, deposit.institution_id, after={"score": score, "limit": limit})

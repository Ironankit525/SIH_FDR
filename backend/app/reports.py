"""Management reports named in the problem statement. Each builder returns a CSV header and rows."""
from datetime import date

from sqlalchemy import func, select

from . import risk
from .models import Discrepancy, Document, Institution, ReleaseRequest, User
from .workflows import current_instrument

MATURITY_HORIZON_DAYS = 90
CONFIRMED = ("officially_confirmed", "mock_confirmed")


def open_cases(deposits):
    return [d for d in deposits if d.status not in ("draft", "released")]


def institution_name(db, deposit):
    return db.get(Institution, deposit.institution_id).name


def pending_verification(db, deposits):
    header = ["Reference", "Institution", "Bank", "Instrument", "Amount INR", "Submitted on", "Days waiting", "Verification", "Assigned officer"]
    rows = []
    for d in open_cases(deposits):
        inst = current_instrument(db, d.id)
        if not inst or inst.verification_status in CONFIRMED:
            continue
        submitted = d.submitted_at.date() if d.submitted_at else None
        officer = db.get(User, d.assigned_officer_id) if d.assigned_officer_id else None
        rows.append([d.reference, institution_name(db, d), inst.bank, inst.number, inst.amount, submitted or "",
                     (date.today() - submitted).days if submitted else "", inst.verification_status, officer.name if officer else "Unassigned"])
    return header, sorted(rows, key=lambda r: -(r[6] or 0))


def upcoming_maturity(db, deposits):
    header = ["Reference", "Institution", "Bank", "Instrument", "Amount INR", "Maturity", "Days to maturity", "Security period ends",
              "Renewal due", "Covers the security period"]
    rows = []
    for d in open_cases(deposits):
        inst = current_instrument(db, d.id)
        if not inst:
            continue
        days = (inst.maturity_date - date.today()).days
        if days > MATURITY_HORIZON_DAYS:
            continue
        covers = "Not recorded" if not d.regulatory_end_date else "Yes" if inst.maturity_date >= d.regulatory_end_date else "No"
        rows.append([d.reference, institution_name(db, d), inst.bank, inst.number, inst.amount, inst.maturity_date, days,
                     d.regulatory_end_date or "", d.renewal_due_date or "", covers])
    return header, sorted(rows, key=lambda r: r[6])


def missing_documents(db, deposits):
    header = ["Reference", "Institution", "Status", "Missing"]
    rows = []
    for d in open_cases(deposits):
        inst = current_instrument(db, d.id)
        docs = db.scalars(select(Document).where(Document.deposit_id == d.id)).all()
        missing = []
        if inst and not any(doc.instrument_id == inst.id and doc.category == "instrument" for doc in docs):
            missing.append("current instrument receipt")
        release = db.scalar(select(ReleaseRequest).where(ReleaseRequest.deposit_id == d.id))
        if release and release.status in ("under_review", "returned"):
            categories = {doc.category for doc in docs}
            missing += [f"{name.replace('_', ' ')} (release)" for name in release.workflow_snapshot.get("required_documents", []) if name not in categories]
        if missing:
            rows.append([d.reference, institution_name(db, d), d.status, "; ".join(missing)])
    return header, rows


def intervention(db, deposits):
    """Cases an official should look at now: high risk, open high-severity tasks, or lapsed security."""
    header = ["Reference", "Institution", "Risk score", "Risk level", "Open high-severity tasks", "Security lapsed", "Main reasons"]
    rows = []
    for d in open_cases(deposits):
        assessment = risk.latest(db, d.id)
        open_high = db.scalar(select(func.count()).select_from(Discrepancy).where(
            Discrepancy.deposit_id == d.id, Discrepancy.severity == "high", Discrepancy.status != "resolved"))
        inst = current_instrument(db, d.id)
        lapsed = bool(inst and d.regulatory_end_date and inst.maturity_date < d.regulatory_end_date and inst.maturity_date <= date.today())
        elevated = assessment and assessment.level in ("high", "critical")
        if not (elevated or open_high or lapsed):
            continue
        reasons = " | ".join(s["explanation"] for s in (assessment.signals if assessment else [])[:3])
        rows.append([d.reference, institution_name(db, d), float(assessment.score) if assessment else "", assessment.level if assessment else "",
                     open_high, "Yes" if lapsed else "No", reasons])
    return header, sorted(rows, key=lambda r: -(r[2] or 0))


# kind: (builder, roles allowed or None for everyone with access to the deposits)
REPORTS = {
    "pending_verification": (pending_verification, None),
    "upcoming_maturity": (upcoming_maturity, None),
    "missing_documents": (missing_documents, None),
    "intervention": (intervention, ("verification", "clearance", "authority", "admin", "auditor")),
}

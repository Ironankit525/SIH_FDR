"""Idempotent fictional demo fixtures. Refuses to seed a production environment."""
import hashlib
from datetime import date, timedelta
from pathlib import Path
import pymupdf as fitz
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import *
from .security import passwords
from .rules import calculate
from .storage import store
from .extraction import structure
from .audit import audit
from .workflows import detect, monitor, DEFAULT_WORKFLOW, DEFAULT_ALERTS
from .bank import MockBankAdapter
from . import forensics

DEMO_PASSWORD = "DemoFlow2026!"


def receipt_pdf(inst, institution_name):
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(35, 35, 560, 800), color=(.1, .2, .4), width=1)
    text = ("DEPOSITFLOW - FICTIONAL DEMONSTRATION DOCUMENT\n\n"
            "Not a real bank instrument. No financial value.\n\n"
            f"Bank: {inst.bank}\nBranch: {inst.branch}\nFDR Number: {inst.number}\n"
            f"Depositor Name: {inst.depositor_name}\nInstitution: {institution_name}\n"
            f"Amount: INR {float(inst.amount):.2f}\nIssue Date: {inst.issue_date}\nMaturity Date: {inst.maturity_date}\n"
            + (f"Lien Marked in Favour of: {inst.lien_details}\n" if inst.lien_details else "") + "\n"
            "Security details: Fictional educational institution deposit.\n"
            "This sample is for software workflow testing only.")
    page.insert_textbox(fitz.Rect(55, 70, 540, 730), text, fontsize=12, lineheight=1.7)
    data = doc.tobytes()
    doc.close()
    return data, text


def add_document(db, deposit, inst, user, institution, category="instrument", save_files=False):
    data, text = receipt_pdf(inst, institution.name)
    if category != "instrument":
        pdf = fitz.open()
        page = pdf.new_page()
        text = f"FICTIONAL DEMO SUPPORTING DOCUMENT\n\nCategory: {category}\nInstitution: {institution.name}\nDeposit: {deposit.reference}\n\nNo legal or financial validity."
        page.insert_textbox(fitz.Rect(50, 60, 550, 700), text, fontsize=13)
        data = pdf.tobytes()
        pdf.close()
    document = Document(deposit_id=deposit.id, instrument_id=inst.id if category == "instrument" else None,
                        filename=f"{inst.number}-{category}.pdf", content_type="application/pdf", size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(), storage_key=store.put(data), category=category,
                        scan_status="fictional_seed_fixture", processing_status="completed", uploaded_by=user.id)
    db.add(document)
    db.flush()
    fields, confidences = structure(text, "embedded_pdf_text")
    db.add(Extraction(document_id=document.id, method="embedded_pdf_text", original_text=text, fields=fields, confidences=confidences))
    if category == "instrument":
        document.forensics = forensics.inspect(data, "application/pdf", ocr=False)
    audit(db, user, "document_uploaded", deposit.id, deposit.institution_id, after={"filename": document.filename, "fictional_seed": True})
    audit(db, None, "ocr_completed", deposit.id, deposit.institution_id, after={"document_id": document.id, "method": "embedded_pdf_text"})
    if save_files:
        folder = Path(__file__).resolve().parents[2] / "demo-data"
        folder.mkdir(exist_ok=True)
        (folder / document.filename).write_bytes(data)
    return document


def seed(db, save_files=False):
    if settings.environment == "production":
        raise RuntimeError("Demo seeding is disabled in production")
    if db.scalar(select(User.id).limit(1)):
        return
    for name, actions in {"institution": ["own_records", "submit", "request_release"], "verification": ["review", "verify", "resolve"],
                          "clearance": ["assigned_cell_decision"], "authority": ["authorise_release"],
                          "admin": ["users", "rules", "configuration"], "auditor": ["read", "export_audit"]}.items():
        db.add(Role(name=name, permissions=actions))
    db.flush()
    institutions = []
    for idx, (name, state) in enumerate([("Meridian Institute of Technology", "Odisha"), ("Sahyadri College of Engineering", "Maharashtra"), ("Northstar School of Management", "Karnataka")]):
        inst = Institution(code=f"DEMO-INST-00{idx + 1}", name=name, state=state, contact_email=f"institution{idx + 1}@demo.local", address=f"Knowledge Park, {state}", approval_year=2016)
        db.add(inst)
        db.flush()
        db.add(Programme(institution_id=inst.id, name="Engineering and Technology" if idx < 2 else "Management", level="undergraduate"))
        institutions.append(inst)
    db.flush()
    password_hash = passwords.hash(settings.demo_password or DEMO_PASSWORD)
    accounts = [("institution", "Ananya Rao", "institution", institutions[0].id, None),
                ("institution2", "Rohan Desai", "institution", institutions[1].id, None),
                ("institution3", "Meera Iyer", "institution", institutions[2].id, None),
                ("officer", "Arjun Mehta", "verification", None, None),
                ("officer2", "Sana Qureshi", "verification", None, None),
                ("clearance", "Priya Sharma", "clearance", None, "PGRC"),
                ("vigilance", "Vikram Sen", "clearance", None, "Vigilance"),
                ("authority", "Dr. Kavita Nair", "authority", None, None),
                ("admin", "Aditi Verma", "admin", None, None),
                ("admin2", "Neel Kapoor", "admin", None, None),
                ("auditor", "Dev Patel", "auditor", None, None)]
    users = {}
    for prefix, name, role, institution_id, cell in accounts:
        user = User(email=f"{prefix}@demo.local", name=name, role=role, institution_id=institution_id, clearance_cell=cell, password_hash=password_hash)
        db.add(user)
        users[prefix] = user
    db.flush()
    rule = RegulatoryRule(code="ILLUSTRATIVE-APH-2024-27", title="Illustrative security deposit requirements")
    db.add(rule)
    db.flush()
    version = RuleVersion(rule_id=rule.id, version=1, status="active", effective_from=date(2024, 1, 1), effective_to=date(2027, 12, 31), illustrative=True,
                          source_reference="Illustrative examples inspired by AICTE APH 2024–2027 clause 1.12; not verified current regulatory advice.",
                          config={"amounts": {"Engineering and Technology|undergraduate": 3500000, "Engineering and Technology|diploma": 1500000, "Management|undergraduate": 500000},
                                  "exempt_ownership": ["government", "government_aided"], "private_lease_multiplier": 2})
    db.add(version)
    db.add(Configuration(key="workflow", value=DEFAULT_WORKFLOW))
    db.add(Configuration(key="alerts", value=DEFAULT_ALERTS))
    db.flush()
    today = date.today()
    specs = [
        ("MATCH-001", 3500000, 365, 0), ("SHORT-002", 1500000, 320, 0),
        ("UNKNOWN-003", 3500000, 400, 0), ("MATURITY-004", 3500000, 7, 0),
        ("RENEWED-005", 3500000, 700, 0), ("RELEASE-006", 3500000, -12, 0),
        ("AMOUNT-007", 3500000, 200, 1), ("NAME-008", 3500000, 60, 1),
        ("UNAVAILABLE-009", 500000, 90, 2),
    ]
    for idx, (number, amount, days, institution_index) in enumerate(specs):
        institution = institutions[institution_index]
        owner = users[["institution", "institution2", "institution3"][institution_index]]
        programme = db.scalar(select(Programme).where(Programme.institution_id == institution.id))
        requirement = calculate(db, institution, programme)
        deposit = SecurityDeposit(institution_id=institution.id, programme_id=programme.id, reference=f"DF-{today.year}-{idx + 1:06}",
                                  rule_version_id=version.id, requirement_snapshot=requirement, required_amount=requirement["required_amount"],
                                  regulatory_end_date=today + timedelta(days=-15 if idx == 5 else 720), renewal_due_date=today + timedelta(days=7) if idx == 3 else None,
                                  status="submitted", submitted_by=owner.id, submitted_at=utcnow() - timedelta(days=idx + 1),
                                  created_at=utcnow() - timedelta(days=idx * 17), assigned_officer_id=users["officer"].id if idx == 5 else None)
        db.add(deposit)
        db.flush()
        inst = Instrument(deposit_id=deposit.id, bank="DEMO NATIONAL BANK", branch="Education Services Branch", number=number,
                          depositor_name=institution.name, amount=amount, issue_date=today - timedelta(days=3660 if idx == 5 else 180), maturity_date=today + timedelta(days=days), lien_details="AICTE, New Delhi (fictional demo lien)")
        db.add(inst)
        db.flush()
        audit(db, owner, "deposit_submitted", deposit.id, institution.id, after={"reference": deposit.reference, "fictional_seed": True})
        add_document(db, deposit, inst, owner, institution, save_files=save_files)
        if not number.startswith("UNKNOWN"):
            fields = {"bank": inst.bank, "number": number, "amount": float(amount), "depositor_name": inst.depositor_name, "issue_date": str(inst.issue_date), "maturity_date": str(inst.maturity_date)}
            if number.startswith("AMOUNT"):
                fields["amount"] = 1500000.0
            if number.startswith("NAME"):
                fields["depositor_name"] = "Different Fictional Trust"
            db.add(MockBankRecord(number=number, fields=fields, available=not number.startswith("UNAVAILABLE")))
        if idx == 4:
            previous = Instrument(deposit_id=deposit.id, bank=inst.bank, branch=inst.branch, number="ORIGINAL-005", depositor_name=inst.depositor_name,
                                  amount=3500000, issue_date=today - timedelta(days=720), maturity_date=today - timedelta(days=5), status="replaced",
                                  lien_details=inst.lien_details)
            db.add(previous)
            db.flush()
            add_document(db, deposit, previous, owner, institution, save_files=save_files)
            db.add(Replacement(deposit_id=deposit.id, previous_id=previous.id, replacement_id=inst.id, reason="Illustrative renewal after review", actor_id=owner.id))
            audit(db, owner, "instrument_replaced", deposit.id, institution.id, before={"instrument_id": previous.id}, after={"instrument_id": inst.id})
        db.flush()
        detect(db, deposit)
        if idx == 5:
            result = MockBankAdapter(db).verify(inst)
            req = VerificationRequest(deposit_id=deposit.id, instrument_id=inst.id, channel="SIMULATED / MOCK BANK DATA", requested_by=users["officer"].id, status="confirmed")
            db.add(req)
            db.flush()
            db.add(VerificationEvidence(request_id=req.id, source=result["source"], reference="MOCK-RELEASE-006", finding="confirmed", observations=result["observations"], confirmed_fields=result["fields"], simulated=True, verified_on=today, recorded_by=users["officer"].id))
            inst.verification_status = "mock_confirmed"
            audit(db, users["officer"], "mock_verification_recorded", deposit.id, institution.id, after=result)
            for discrepancy in db.scalars(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id)).all():
                discrepancy.status, discrepancy.resolution = "resolved", "Fictional demo officer reviewed this task; illustrative applicability accepted for simulation only."
                discrepancy.resolved_by, discrepancy.resolution_kind = users["officer"].id, "officer"
                if discrepancy.severity == "high":
                    discrepancy.confirmed_by, discrepancy.resolution_kind = users["officer2"].id, "officer_confirmed"
                audit(db, users["officer"], "discrepancy_resolved", deposit.id, institution.id, after={"code": discrepancy.code, "notes": discrepancy.resolution})
            for category in DEFAULT_WORKFLOW["required_documents"]:
                add_document(db, deposit, inst, owner, institution, category, save_files)
            release = ReleaseRequest(deposit_id=deposit.id, requested_by=owner.id, reason="Illustrative completed regulatory term; request discharge after all clearances.", workflow_snapshot=DEFAULT_WORKFLOW)
            db.add(release)
            db.flush()
            db.add(Clearance(release_id=release.id, cell="PGRC", status="approved", notes="Fictional demo clearance recorded.", officer_id=users["clearance"].id))
            db.add(Clearance(release_id=release.id, cell="Vigilance"))
            deposit.status = "release_requested"
            audit(db, owner, "release_requested", deposit.id, institution.id, after={"release_id": release.id})
            audit(db, users["clearance"], "clearance_decided", deposit.id, institution.id, after={"cell": "PGRC", "status": "approved"})
    db.commit()
    monitor(db)


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session, save_files=True)
    print("Fictional demo seeded. See README for local demo sign-in accounts.")

"""Regression tests for the automated review checks that feed the risk engine."""
import io
from datetime import date, timedelta

import pymupdf as fitz
import pytest
from PIL import Image
from sqlalchemy import select

from app import forensics
from app.extraction import structure
from app.matching import names_match, normalise_bank, normalise_number
from app.storage import store
from app.models import (Discrepancy, Document, Instrument, MockBankRecord, ReleaseRequest, SecurityDeposit, VerificationEvidence,
                        VerificationRequest)
from app.bank import MockBankAdapter
from app.workflows import detect, monitor, release_blockers
from test_workflows import get_case, payload, pdf_for


def codes(detail, status=None):
    return {d["code"].split(":")[0]: d for d in detail["discrepancies"] if status is None or d["status"] == status}


def new_case(c, **overrides):
    values = {**payload(c), "lien_details": "Lien marked in favour of AICTE", **overrides}
    result = c.post("/api/deposits", json=values)
    assert result.status_code == 201, result.text
    case = result.json()
    upload = c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", pdf_for(case), "application/pdf")})
    assert upload.status_code == 201, upload.text
    return c.get(f"/api/deposits/{case['id']}").json()


def text_pdf(lines, metadata=None, incremental_dir=None):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(55, 70, 540, 730), "\n".join(lines), fontsize=12, lineheight=1.7)
    if metadata:
        doc.set_metadata(metadata)
    data = doc.tobytes()
    doc.close()
    if incremental_dir:
        # Incremental saves append to an existing file, as editors do.
        path = incremental_dir / "edited.pdf"
        path.write_bytes(data)
        with fitz.open(path) as edited:
            edited[0].insert_text((60, 780), "Endorsed")
            edited.saveIncr()
        data = path.read_bytes()
    return data


# 1 — flags reopen on new evidence; warnings clear themselves; high-severity tasks stay with an officer.

def test_resolved_flag_reopens_when_evidence_changes(env):
    factory, client = env
    with factory() as db:
        deposit = db.scalar(select(SecurityDeposit).join(Instrument).where(Instrument.number == "SHORT-002"))
        task = db.scalar(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.code.startswith("amount_shortfall")))
        task.status, task.resolution, task.resolution_kind = "resolved", "Accepted reduced amount", "officer"
        db.commit()
        instrument = db.scalar(select(Instrument).where(Instrument.number == "SHORT-002"))
        instrument.amount = 1000000
        detect(db, deposit)
        db.commit()
        db.refresh(task)
        assert task.status == "open" and "1,000,000" in task.description and task.resolution == ""


def test_warning_clears_automatically_but_high_severity_waits_for_officer(env):
    factory, client = env
    officer = client("officer")
    case = get_case(officer)
    officer.post(f"/api/deposits/{case['id']}/assign")
    assert codes(officer.get(f"/api/deposits/{case['id']}").json())["unverified"]["status"] == "open"
    officer.post(f"/api/deposits/{case['id']}/verification/mock")
    unverified = codes(officer.get(f"/api/deposits/{case['id']}").json())["unverified"]
    assert unverified["status"] == "resolved" and unverified["resolution_kind"] == "automatic"
    with factory() as db:
        deposit = db.get(SecurityDeposit, case["id"])
        instrument = db.scalar(select(Instrument).where(Instrument.deposit_id == deposit.id))
        instrument.amount = 1000000
        detect(db, deposit)
        db.commit()
        shortfall = db.scalar(select(Discrepancy).where(Discrepancy.deposit_id == deposit.id, Discrepancy.code.startswith("amount_shortfall")))
        instrument.amount = 3500000
        detect(db, deposit)
        db.commit()
        db.refresh(shortfall)
        assert shortfall.status == "open" and shortfall.condition_active is False


# 2 — coverage of the whole security period.

def test_coverage_gap_and_lapse(env):
    factory, client = env
    c = client()
    today = date.today()
    gap = new_case(c, number="COVER-GAP-01", maturity_date=str(today + timedelta(days=30)), regulatory_end_date=str(today + timedelta(days=400)))
    assert codes(gap)["coverage_gap"]["severity"] == "warning"
    fine = new_case(c, number="COVER-OK-01", maturity_date=str(today + timedelta(days=500)), regulatory_end_date=str(today + timedelta(days=400)))
    assert "coverage_gap" not in codes(fine)
    with factory() as db:
        deposit = db.get(SecurityDeposit, gap["id"])
        db.scalar(select(Instrument).where(Instrument.deposit_id == deposit.id)).maturity_date = today
        detect(db, deposit)
        db.commit()
    assert codes(c.get(f"/api/deposits/{gap['id']}").json())["coverage_lapsed"]["severity"] == "high"


# 3 — the bank check compares dates.

def test_bank_check_detects_altered_maturity(env):
    factory, _ = env
    with factory() as db:
        inst = db.scalar(select(Instrument).where(Instrument.number == "MATCH-001"))
        record = db.scalar(select(MockBankRecord).where(MockBankRecord.number == "MATCH-001"))
        record.fields = {**record.fields, "maturity_date": str(inst.maturity_date - timedelta(days=200))}
        result = MockBankAdapter(db).verify(inst)
        assert result["finding"] == "mismatched" and "maturity_date" in result["observations"]


# 4 — stale confirmations block release.

def test_stale_verification_blocks_release(env):
    factory, _ = env
    with factory() as db:
        release = db.scalar(select(ReleaseRequest))
        deposit = db.get(SecurityDeposit, release.deposit_id)
        evidence = db.scalar(select(VerificationEvidence).join(VerificationRequest).where(VerificationRequest.deposit_id == deposit.id))
        assert not any("fresh confirmation" in b for b in release_blockers(db, deposit, release))
        evidence.verified_on = date.today() - timedelta(days=45)
        db.flush()
        assert any("fresh confirmation" in b for b in release_blockers(db, deposit, release))


# 5 — lien in favour of AICTE.

def test_lien_must_name_aicte(env):
    _, client = env
    c = client()
    missing = new_case(c, number="LIEN-NONE-01", lien_details="General security")
    assert codes(missing)["lien_not_aicte"]["severity"] == "high"
    joint = new_case(c, number="LIEN-JOINT-01", lien_details="", depositor_name="Member Secretary AICTE and Meridian Institute of Technology")
    assert "lien_not_aicte" not in codes(joint) and "depositor_not_institution" not in codes(joint)


def test_document_lien_conflict(env):
    _, client = env
    c = client()
    case = new_case(c, number="LIEN-DOC-01")
    lines = ["Bank: TEST BANK", "FDR Number: LIEN-DOC-01", f"Depositor Name: {case['institution_name']}", "Amount: INR 3500000.00",
             f"Issue Date: {case['instrument']['issue_date']}", f"Maturity Date: {case['instrument']['maturity_date']}", "Lien Marked in Favour of: Example Cooperative Society"]
    c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("lien.pdf", text_pdf(lines), "application/pdf")})
    assert "lien_document_conflict" in codes(c.get(f"/api/deposits/{case['id']}").json())


# 6 — the depositor must be the institution.

def test_third_party_depositor_flagged(env):
    _, client = env
    c = client()
    case = new_case(c, number="THIRD-PARTY-01", depositor_name="Unrelated Holdings Private Limited")
    assert codes(case)["depositor_not_institution"]["severity"] == "high"


def test_name_and_reference_normalisation():
    assert names_match("MERIDIAN INSTITUTE OF TECHNOLOGY.", "Meridian Institute of Technology")
    assert not names_match("Different Fictional Trust", "Meridian Institute of Technology")
    assert normalise_bank("SBI") == normalise_bank("State Bank of India Ltd")
    assert normalise_bank("Bank of India") != normalise_bank("State Bank of India")
    assert normalise_number("FDR-001/A") == normalise_number("fdr 001 a")


# 7 — duplicates that differ only in formatting, reused numbers and re-saved copies.

def test_formatting_variants_cannot_register_the_same_instrument(env):
    _, client = env
    c = client()
    new_case(c, number="DUP-123-45", bank="State Bank of India")
    assert c.post("/api/deposits", json={**payload(c, "DUP12345"), "bank": "SBI"}).status_code == 409
    other_bank = c.post("/api/deposits", json={**payload(c, "DUP/123/45"), "bank": "Canara Bank"})
    assert other_bank.status_code == 201


def test_receipt_reused_with_new_file_bytes_is_flagged(env):
    factory, client = env
    c = client()
    with factory() as db:
        inst = db.scalar(select(Instrument).where(Instrument.number == "MATCH-001"))
        original = db.scalar(select(Document).where(Document.instrument_id == inst.id))
        # Same receipt content in a new file: the bytes differ, the text does not.
        copy = store.get(original.storage_key) + b"\n%resaved copy\n"
    case = c.post("/api/deposits", json={**payload(c, "REUSE-TEST-01"), "lien_details": "AICTE"}).json()
    c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("copy.pdf", copy, "application/pdf")})
    found = codes(c.get(f"/api/deposits/{case['id']}").json())
    assert "extracted_number_elsewhere" in found
    assert found["reused_text"]["severity"] == "high" and "reused_document" not in found


# 8 — document forensics.

def test_overlay_edit_shows_conflicting_values():
    lines = ["Bank: TEST BANK", "FDR Number: OVERLAY-01", "Amount: INR 3500000.00", "Issue Date: 2026-01-01", "Maturity Date: 2027-01-01"]
    doc = fitz.open(stream=text_pdf(lines), filetype="pdf")
    page = doc[0]
    hit = page.search_for("3500000.00")[0]
    page.draw_rect(hit, color=(1, 1, 1), fill=(1, 1, 1))
    page.insert_text((hit.x0, hit.y1 - 2), "9500000.00", fontsize=12)
    report = forensics.inspect(doc.tobytes(), "application/pdf")
    # The covered figure stays in the text layer while the page shows the new one.
    assert "text_layer_mismatch_amount" in {s["code"] for s in report["signals"]}


def test_hidden_text_layer_disagreeing_with_page_is_flagged():
    doc = fitz.open()
    page = doc.new_page()
    visible = "Bank: TEST BANK\nFDR Number: HIDDEN-01\nAmount: INR 3500000.00\nIssue Date: 2026-01-01\nMaturity Date: 2027-01-01"
    pix = fitz.open()
    image_page = pix.new_page()
    image_page.insert_textbox(fitz.Rect(55, 70, 540, 730), visible, fontsize=12, lineheight=1.7)
    page.insert_image(page.rect, pixmap=image_page.get_pixmap(matrix=fitz.Matrix(2, 2)))
    # Invisible text (render mode 3) claims a different amount from what the page shows.
    page.insert_textbox(fitz.Rect(55, 70, 540, 730), visible.replace("3500000.00", "9500000.00"), fontsize=12, lineheight=1.7, render_mode=3)
    report = forensics.inspect(doc.tobytes(), "application/pdf")
    assert report["ocr_crosscheck"] == "completed"
    assert "text_layer_mismatch_amount" in {s["code"] for s in report["signals"]}


def test_metadata_and_incremental_save_indicators(tmp_path):
    lines = ["Bank: TEST BANK", "FDR Number: META-01", "Amount: INR 3500000.00"]
    clean = forensics.inspect(text_pdf(lines), "application/pdf", ocr=False)
    assert clean["signals"] == []
    edited = forensics.inspect(text_pdf(lines, incremental_dir=tmp_path, metadata={"producer": "Adobe Photoshop 25", "creationDate": "D:20260101100000", "modDate": "D:20260301100000"}), "application/pdf", ocr=False)
    found = {s["code"] for s in edited["signals"]}
    assert {"editing_software", "modified_after_creation", "incremental_update"} <= found


def test_forensic_signals_become_review_tasks(env):
    _, client = env
    c, officer = client(), client("officer")
    case = c.post("/api/deposits", json={**payload(c, "FORENSIC-01"), "lien_details": "AICTE"}).json()
    lines = ["Bank: TEST BANK", "FDR Number: FORENSIC-01", f"Depositor Name: {case['institution_name']}", "Amount: INR 3500000.00",
             "Amount: INR 9500000.00", f"Issue Date: {case['instrument']['issue_date']}", f"Maturity Date: {case['instrument']['maturity_date']}"]
    c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", text_pdf(lines), "application/pdf")})
    detail = officer.get(f"/api/deposits/{case['id']}").json()
    assert codes(detail)["forensic_conflicting_values_amount"]["evidence_source"] == "document_forensics"
    assert detail["documents"][0]["forensics"]["version"] == forensics.VERSION
    # The institution learns that verification is needed, not which check noticed the problem.
    own = c.get(f"/api/deposits/{case['id']}").json()
    assert "forensic_conflicting_values_amount" not in codes(own) and "document_review" in codes(own)
    assert "forensics" not in own["documents"][0]
    assert "different amount values" not in str(own) and "document_forensics" not in str(own)


# 9 — confidence reflects the content.

def test_confidence_depends_on_content():
    clear = structure("FDR Number: AB-1\nAmount: INR 3500000.00", "embedded_pdf_text")
    conflicted = structure("FDR Number: AB-1\nAmount: INR 3500000.00\nAmount: INR 9500000.00", "embedded_pdf_text")
    fallback = structure("Reference: AB-1", "embedded_pdf_text")
    assert clear[1]["amount"] == 0.9 and conflicted[1]["amount"] < 0.5 and fallback[1]["number"] < 0.9
    assert structure("FDR Number: AMOUNT-007\nAmount: INR 3500000.00", "embedded_pdf_text")[0]["amount"] == 3500000
    assert structure("Amount: INR 3500000.00\nMaturity Amount: INR 3800000.00", "embedded_pdf_text")[1]["amount"] == 0.9


# 10 — a second officer confirms high-severity resolutions.

def test_high_severity_resolution_needs_second_officer(env):
    _, client = env
    officer, second, owner = client("officer"), client("officer2"), client()
    case = get_case(officer, "SHORT-002")
    officer.post(f"/api/deposits/{case['id']}/assign")
    task = codes(officer.get(f"/api/deposits/{case['id']}").json())["amount_shortfall"]
    assert officer.post(f"/api/discrepancies/{task['id']}/resolve", json={"notes": "Looks fine"}).status_code == 422
    proposed = officer.post(f"/api/discrepancies/{task['id']}/resolve", json={"notes": "Reduced requirement confirmed by the approval order on file"})
    assert proposed.json()["status"] == "resolution_proposed"
    assert owner.post(f"/api/discrepancies/{task['id']}/respond", json={"notes": "Additional explanation"}).status_code == 409
    assert officer.post(f"/api/discrepancies/{task['id']}/review", json={"decision": "confirm", "notes": "Self check"}).status_code == 403
    rejected = second.post(f"/api/discrepancies/{task['id']}/review", json={"decision": "reject", "notes": "Approval order not attached"})
    assert rejected.json()["status"] == "open" and rejected.json()["resolved_by"] is None
    officer.post(f"/api/discrepancies/{task['id']}/resolve", json={"notes": "Approval order attached as supporting document"})
    confirmed = second.post(f"/api/discrepancies/{task['id']}/review", json={"decision": "confirm", "notes": "Checked the approval order"})
    assert confirmed.json()["status"] == "resolved" and confirmed.json()["resolution_kind"] == "officer_confirmed"


def test_warning_resolution_needs_one_officer(env):
    _, client = env
    officer = client("officer")
    case = get_case(officer)
    officer.post(f"/api/deposits/{case['id']}/assign")
    task = codes(officer.get(f"/api/deposits/{case['id']}").json())["rule_review"]
    assert officer.post(f"/api/discrepancies/{task['id']}/resolve", json={"notes": "Rule applies"}).json()["status"] == "resolved"


# 11 — institution history.

def test_institution_profile(env):
    _, client = env
    officer, owner = client("officer"), client()
    institution = owner.get("/api/institutions").json()[0]
    assert owner.get(f"/api/institutions/{institution['id']}/profile").status_code == 403
    profile = officer.get(f"/api/institutions/{institution['id']}/profile").json()
    assert profile["deposits"] == 6 and profile["replacements"] == 1 and profile["high_severity_tasks"] >= 1


# 12 — date-driven checks run without waiting for an event.

def test_daily_sweep_flags_newly_matured_instruments(env):
    factory, _ = env
    with factory() as db:
        inst = db.scalar(select(Instrument).where(Instrument.number == "MATCH-001"))
        inst.maturity_date = date.today() + timedelta(days=1)
        db.commit()
        monitor(db, today=date.today() + timedelta(days=2))
        assert not db.scalar(select(Discrepancy).where(Discrepancy.deposit_id == inst.deposit_id, Discrepancy.code.startswith("matured")))
        inst.maturity_date = date.today()
        db.commit()
        monitor(db, today=date.today() + timedelta(days=3))
        assert db.scalar(select(Discrepancy).where(Discrepancy.deposit_id == inst.deposit_id, Discrepancy.code.startswith("matured")))


def test_report_records_what_was_examined(tmp_path):
    lines = ["Bank: TEST BANK", "FDR Number: SHOWN-01", "Amount: INR 3500000.00", "Issue Date: 2026-01-01", "Maturity Date: 2027-01-01"]
    report = forensics.inspect(text_pdf(lines), "application/pdf")
    assert report["structure"] == {"pages": 1, "saves": 1, "linearised": False, "text_layer": True}
    assert report["ocr_crosscheck"] == "completed" and set(report["compared_fields"]) == {"number", "amount", "issue_date", "maturity_date"}
    assert set(report["text_fields"]) == {"number", "amount", "issue_date", "maturity_date"}
    assert forensics.inspect(text_pdf(lines, incremental_dir=tmp_path), "application/pdf", ocr=False)["structure"]["saves"] == 2
    assert forensics.inspect(text_pdf(lines), "application/pdf", ocr=False)["ocr_crosscheck"] == "skipped"
    scanned = fitz.open()
    page = scanned.new_page()
    page.insert_image(page.rect, pixmap=fitz.open(stream=text_pdf(lines), filetype="pdf")[0].get_pixmap())
    assert forensics.inspect(scanned.tobytes(), "application/pdf")["ocr_crosscheck"] == "not_applicable"
    image = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(image, "PNG")
    assert forensics.inspect(image.getvalue(), "image/png")["ocr_crosscheck"] == "not_applicable"

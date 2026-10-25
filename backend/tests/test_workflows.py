import hashlib
import io
import shutil
from datetime import date, timedelta
from unittest.mock import patch

import jwt
import pymupdf as fitz
import pytest
from PIL import Image
from sqlalchemy import select, func
from app.audit import event_digest
from app.bank import MockBankAdapter
from app.config import settings
from app.extraction import extract_text, structure
from app.models import *
from app.seed import receipt_pdf
from app.storage import store
from app.workflows import monitor


def get_case(client, number="MATCH-001"):
    return next(d for d in client.get("/api/deposits").json() if d["instrument"]["number"] == number)


def payload(client, number="NEW-TEST-001", amount=3500000):
    institution = client.get("/api/institutions").json()[0]
    today = date.today()
    return {"programme_id": institution["programmes"][0]["id"], "instrument_type": "FDR", "bank": "Test Bank", "branch": "Test Branch", "number": number,
            "depositor_name": institution["name"], "amount": amount, "issue_date": str(today - timedelta(days=5)), "maturity_date": str(today + timedelta(days=365)),
            "regulatory_end_date": str(today + timedelta(days=730)), "lien_details": "Test security"}


def pdf_for(case, amount=None):
    i = case["instrument"]
    inst = Instrument(bank=i["bank"], branch=i["branch"], number=i["number"], depositor_name=i["depositor_name"], amount=amount if amount is not None else i["amount"],
                      issue_date=date.fromisoformat(i["issue_date"]), maturity_date=date.fromisoformat(i["maturity_date"]))
    return receipt_pdf(inst, case["institution_name"])[0]


def test_authentication_and_logout(env):
    _, client = env
    anonymous = client(None)
    assert anonymous.get("/api/deposits").status_code == 401
    assert anonymous.post("/api/auth/login", json={"email": "institution@demo.local", "password": "wrong"}).status_code == 401
    owner = client()
    assert owner.get("/api/auth/me").json()["role"] == "institution"
    assert "password_hash" not in owner.get("/api/auth/me").text
    assert owner.post("/api/auth/logout").status_code == 200
    assert owner.get("/api/deposits").status_code == 401


def test_csrf_and_origin(env):
    _, client = env
    c = client()
    c.headers.pop("X-CSRF-Token")
    assert c.post("/api/deposits", json=payload(c)).status_code == 403
    assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "wrong"}, headers={"Origin": "https://untrusted.example"}).status_code == 403


def test_cross_institution_isolation_and_export(env):
    _, client = env
    a, b = client(), client("institution2")
    other = get_case(b, "AMOUNT-007")
    assert a.get(f"/api/deposits/{other['id']}").status_code == 404
    assert a.post(f"/api/deposits/{other['id']}/submit").status_code == 404
    doc = b.get(f"/api/deposits/{other['id']}").json()["documents"][0]
    assert a.get(f"/api/documents/{doc['id']}/access").status_code == 404
    assert "Sahyadri" not in a.get("/api/reports/export").text
    assert a.get("/api/admin/users").status_code == 403
    assert a.get("/api/audit").status_code == 403


@pytest.mark.parametrize("role", ["institution", "officer", "clearance", "admin", "auditor"])
def test_only_authority_can_authorise(env, role):
    _, client = env
    c = client(role)
    release = c.get("/api/releases").json()[0]
    assert c.post(f"/api/releases/{release['id']}/decision", json={"decision": "approved", "notes": "Role boundary test"}).status_code == 403


def test_requirement_exemption_and_effective_dates(env):
    factory, client = env
    c = client()
    institution = c.get("/api/institutions").json()[0]
    body = {"institution_id": institution["id"], "programme_id": institution["programmes"][0]["id"], "as_of": "2026-10-24"}
    result = c.post("/api/requirements/calculate", json=body).json()
    assert result["required_amount"] == 3500000
    assert result["illustrative"] and result["manual_review"]
    with factory() as db:
        db.get(Institution, institution["id"]).land_arrangement = "private_lease"
        db.commit()
    assert c.post("/api/requirements/calculate", json=body).json()["required_amount"] == 7000000
    with factory() as db:
        db.get(Institution, institution["id"]).ownership = "government"
        db.commit()
    assert c.post("/api/requirements/calculate", json=body).json()["exempt"] is True
    assert c.post("/api/requirements/calculate", json={**body, "as_of": "2035-01-01"}).json()["required_amount"] is None


def test_submission_requires_document_and_detects_amount_mismatch(env):
    _, client = env
    c = client()
    result = c.post("/api/deposits", json=payload(c))
    assert result.status_code == 201, result.text
    case = result.json()
    assert c.post(f"/api/deposits/{case['id']}/submit").status_code == 422
    upload = c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", pdf_for(case, 1500000), "application/pdf")})
    assert upload.status_code == 201, upload.text
    submitted = c.post(f"/api/deposits/{case['id']}/submit")
    assert submitted.status_code == 200
    assert any(d["code"].startswith("mismatch_amount") for d in submitted.json()["discrepancies"])
    assert submitted.json()["documents"][0]["extraction"]["fields"]["amount"] == 1500000
    assert c.post(f"/api/deposits/{case['id']}/submit").status_code == 409


@pytest.mark.parametrize("override", [{"amount": -1}, {"maturity_date": "2000-01-01"}, {"issue_date": "2099-01-01"}, {"instrument_type": "FAKE"}, {"number": "<script>"}])
def test_submission_validation(env, override):
    _, client = env
    c = client()
    assert c.post("/api/deposits", json={**payload(c), **override}).status_code == 422


def test_duplicate_prevention(env):
    _, client = env
    c = client()
    values = payload(c)
    assert c.post("/api/deposits", json=values).status_code == 201
    assert c.post("/api/deposits", json=values).status_code == 409
    assert c.post("/api/deposits", json={**values, "bank": "test bank", "number": "new-test-001"}).status_code == 409


def test_amount_shortfall_explained(env):
    _, client = env
    c = client()
    case = get_case(c, "SHORT-002")
    result = c.get(f"/api/deposits/{case['id']}").json()
    discrepancy = next(d for d in result["discrepancies"] if d["code"].startswith("amount_shortfall"))
    assert "1,500,000" in discrepancy["description"] and "3,500,000" in discrepancy["description"]
    assert discrepancy["evidence_source"] == "configured_rule"


@pytest.mark.parametrize("number,finding", [("MATCH-001", "confirmed"), ("AMOUNT-007", "mismatched"), ("NAME-008", "mismatched"), ("UNKNOWN-003", "inconclusive"), ("RELEASE-006", "confirmed"), ("UNAVAILABLE-009", "pending")])
def test_mock_bank_scenarios(env, number, finding):
    factory, _ = env
    with factory() as db:
        inst = db.scalar(select(Instrument).where(Instrument.number == number))
        response = MockBankAdapter(db).verify(inst)
        assert response["finding"] == finding
        assert response["simulated"] is True
        assert response["source"] == "SIMULATED / MOCK BANK DATA"
        if number == "UNKNOWN-003":
            assert "not proof of fraud" in response["observations"]


def test_officer_assignment_and_verification(env):
    _, client = env
    c = client("officer")
    case = get_case(c)
    assert c.post(f"/api/deposits/{case['id']}/verification/mock").status_code == 403
    assert c.post(f"/api/deposits/{case['id']}/assign").status_code == 200
    response = c.post(f"/api/deposits/{case['id']}/verification/mock")
    assert response.status_code == 200
    assert response.json()["simulated"] is True
    result = c.get(f"/api/deposits/{case['id']}").json()
    assert result["instrument"]["verification_status"] == "mock_confirmed"
    assert result["verifications"][0]["evidence"]["simulated"] is True


def test_official_verification_needs_bank_document(env):
    _, client = env
    c = client("officer")
    case = get_case(c)
    c.post(f"/api/deposits/{case['id']}/assign")
    request = c.post(f"/api/deposits/{case['id']}/verification/manual", json={"channel": "branch_confirmation"}).json()
    detail = c.get(f"/api/deposits/{case['id']}").json()
    body = {"document_id": detail["documents"][0]["id"], "source": "Authorised demo branch correspondence", "reference": "OFFICIAL-TEST-001", "finding": "confirmed", "observations": "Officer reviewed authorised confirmation evidence.", "verified_on": str(date.today())}
    assert c.post(f"/api/verifications/{request['id']}/evidence", json=body).status_code == 422
    doc = c.post(f"/api/deposits/{case['id']}/documents", data={"category": "bank_confirmation"}, files={"file": ("bank.pdf", pdf_for(case), "application/pdf")}).json()
    assert c.post(f"/api/verifications/{request['id']}/evidence", json={**body, "document_id": doc["id"]}).status_code == 200
    assert c.get(f"/api/deposits/{case['id']}").json()["instrument"]["verification_status"] == "officially_confirmed"


def test_original_extraction_preserved_after_correction(env):
    _, client = env
    c = client()
    case = get_case(c)
    detail = c.get(f"/api/deposits/{case['id']}").json()
    extraction = detail["documents"][0]["extraction"]
    result = c.post(f"/api/extractions/{extraction['id']}/corrections", json={"field": "bank", "corrected_value": "Corrected Bank Name", "reason": "Read directly from original bank confirmation"})
    assert result.status_code == 200
    updated = c.get(f"/api/deposits/{case['id']}").json()["documents"][0]
    assert updated["extraction"]["fields"] == extraction["fields"]
    assert updated["corrections"][0]["corrected_value"] == "Corrected Bank Name"


def test_secure_file_access_is_expiring_and_user_bound(env):
    _, client = env
    c, other = client(), client("institution2")
    case = get_case(c)
    doc = c.get(f"/api/deposits/{case['id']}").json()["documents"][0]
    assert "storage_key" not in doc
    access = c.get(f"/api/documents/{doc['id']}/access").json()
    assert access["expires_in"] == 120
    assert c.get(access["url"]).content.startswith(b"%PDF")
    assert other.get(access["url"]).status_code == 403
    expired = jwt.encode({"sub": c.get('/api/auth/me').json()['id'], "doc": doc['id'], "purpose": "document_access", "exp": 0}, settings.secret_key, algorithm="HS256")
    assert c.get(f"/api/documents/{doc['id']}/content?token={expired}").status_code == 403


def test_files_encrypted_at_rest(env):
    factory, _ = env
    with factory() as db:
        doc = db.scalar(select(Document))
        from pathlib import Path
        encrypted = (Path(settings.storage_path) / doc.storage_key).read_bytes()
        assert not encrypted.startswith(b"%PDF")
        assert b"FICTIONAL" not in encrypted
        assert hashlib.sha256(store.get(doc.storage_key)).hexdigest() == doc.sha256


@pytest.mark.parametrize("filename,data", [("malware.html", b"<script>alert(1)</script>"), ("fake.pdf", b"Not a real PDF"), ("empty.pdf", b"")])
def test_unsafe_upload_rejected(env, filename, data):
    _, client = env
    c = client()
    case = get_case(c)
    assert c.post(f"/api/deposits/{case['id']}/documents", files={"file": (filename, data, "application/pdf")}).status_code == 422


def test_scan_fail_closed_when_required(env, monkeypatch):
    _, client = env
    c = client()
    case = get_case(c)
    monkeypatch.setattr(settings, "require_malware_scan", True)
    assert c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", pdf_for(case), "application/pdf")}).status_code == 503


def test_ocr_fallback_and_failure_reporting(env):
    _, client = env
    img = Image.new("RGB", (800, 300), "white")
    buffer = io.BytesIO(); img.save(buffer, format="PNG")
    with patch("app.extraction.pytesseract.image_to_string", return_value="Amount: INR 3500000\nFDR Number: OCR-001") as ocr:
        text, method = extract_text(buffer.getvalue(), "image/png")
        assert method == "tesseract_ocr" and ocr.called
        assert structure(text, method)[0]["amount"] == 3500000
    c = client(); case = get_case(c)
    with patch("app.extraction.pytesseract.image_to_string", side_effect=RuntimeError("OCR unavailable")):
        doc = c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("scan.png", buffer.getvalue(), "image/png")}).json()
    detail = c.get(f"/api/deposits/{case['id']}").json()
    assert next(d for d in detail["documents"] if d["id"] == doc["id"])["processing_status"] == "failed"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract executable is not installed")
def test_real_tesseract_scanned_pdf(env):
    _, client = env
    case = get_case(client())
    source = fitz.open(stream=pdf_for(case), filetype="pdf")
    pixels = source[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    scanned = fitz.open(); page = scanned.new_page(); page.insert_image(page.rect, stream=pixels.tobytes("png"))
    text, method = extract_text(scanned.tobytes(), "application/pdf")
    assert method == "pdf_text_and_ocr"
    assert "MATCH-001" in text
    fields, _ = structure(text, method)
    assert fields["amount"] == 3500000


def test_notification_idempotency_and_user_read_state(env):
    factory, client = env
    with factory() as db:
        before = db.scalar(select(func.count()).select_from(Notification))
        assert monitor(db) == 0
        assert monitor(db) == 0
        assert db.scalar(select(func.count()).select_from(Notification)) == before
    c = client(); officer = client("officer")
    notification = c.get("/api/notifications").json()[0]
    assert c.post(f"/api/notifications/{notification['id']}/read").status_code == 200
    assert next(n for n in officer.get("/api/notifications").json() if n["id"] == notification["id"])["read"] is False


def test_replacement_preserves_original_and_requires_receipt(env):
    _, client = env
    c = client(); case = get_case(c)
    values = payload(c, "REPLACEMENT-TEST-001")
    for key in ("programme_id", "regulatory_end_date"):
        values.pop(key)
    values["reason"] = "Replace instrument following an authorised renewal review"
    result = c.post(f"/api/deposits/{case['id']}/replace", json=values)
    assert result.status_code == 201, result.text
    detail = result.json()
    assert len(detail["instruments"]) == 2
    assert len(detail["replacements"]) == 1
    assert any(i["number"] == "MATCH-001" and i["status"] == "replaced" for i in detail["instruments"])
    assert detail["documents"][0]["instrument_id"] != detail["instrument"]["id"]
    assert c.post(f"/api/deposits/{case['id']}/submit").status_code == 422


def test_release_blocked_until_assigned_clearance_and_authority_decision(env):
    _, client = env
    authority, pgrc, vigilance = client("authority"), client("clearance"), client("vigilance")
    release = authority.get("/api/releases").json()[0]
    assert any("Vigilance" in b for b in release["blockers"])
    decision = {"decision": "approved", "notes": "Reviewed the fictional demonstration evidence"}
    blocked = authority.post(f"/api/releases/{release['id']}/decision", json=decision)
    assert blocked.status_code == 409
    clearance = next(c for c in release["clearances"] if c["cell"] == "Vigilance")
    assert pgrc.post(f"/api/clearances/{clearance['id']}/decision", json=decision).status_code == 403
    assert vigilance.post(f"/api/clearances/{clearance['id']}/decision", json=decision).status_code == 200
    assert authority.post(f"/api/releases/{release['id']}/decision", json=decision).status_code == 200
    assert authority.post(f"/api/releases/{release['id']}/decision", json=decision).status_code == 409
    owner = client(); case = get_case(owner, "RELEASE-006")
    assert owner.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", pdf_for(case), "application/pdf")}).status_code == 409
    assert authority.post(f"/api/releases/{release['id']}/complete", json={"reference": "DEMO-NOC-12345"}).status_code == 200
    assert get_case(owner, "RELEASE-006")["status"] == "released"


def test_rule_changes_require_second_administrator(env):
    _, client = env
    admin, second = client("admin"), client("admin2")
    rule = admin.get("/api/rules").json()[0]
    body = {k: rule[k] for k in ("rule_id", "effective_from", "effective_to", "config", "source_reference", "illustrative")}
    body["config"]["amounts"]["Engineering and Technology|undergraduate"] = 4000000
    version = admin.post("/api/admin/rules", json=body)
    assert version.status_code == 201, version.text
    path = f"/api/admin/rules/{version.json()['id']}/approve"
    assert admin.post(path, json={"notes": "Self approval should be denied"}).status_code == 403
    assert second.post(path, json={"notes": "Second administrator reviewed the example"}).status_code == 200
    owner = client()
    assert get_case(owner)["required_amount"] == '3500000.00' or float(get_case(owner)["required_amount"]) == 3500000


def test_audit_integrity_and_immutability(env):
    factory, client = env
    c = client("admin")
    monitor = c.get("/api/admin/monitor").json()
    assert monitor["audit_chain_intact"] is True
    with factory() as db:
        item = db.scalar(select(AuditLog))
        assert item.event_hash == event_digest(item)
        item.action = "tampered"
        with pytest.raises(ValueError, match="append-only"):
            db.commit()


def test_login_rate_limit(env):
    _, client = env
    c = client(None)
    for _ in range(20):
        c.post("/api/auth/login", json={"email": "nobody@demo.local", "password": "invalid"})
    assert c.post("/api/auth/login", json={"email": "nobody@demo.local", "password": "invalid"}).status_code == 429


def test_production_mock_verification_disabled(env, monkeypatch):
    _, client = env
    c = client("officer"); case = get_case(c)
    monkeypatch.setattr(settings, "environment", "production")
    assert c.post(f"/api/deposits/{case['id']}/verification/mock").status_code == 403


def test_production_never_accepts_old_demo_verification_for_release(env, monkeypatch):
    _, client = env
    authority, vigilance = client("authority"), client("vigilance")
    release = authority.get("/api/releases").json()[0]
    clearance = next(c for c in release["clearances"] if c["cell"] == "Vigilance")
    decision = {"decision": "approved", "notes": "Clearance confirmed for the demo test"}
    assert vigilance.post(f"/api/clearances/{clearance['id']}/decision", json=decision).status_code == 200
    monkeypatch.setattr(settings, "environment", "production")
    result = authority.post(f"/api/releases/{release['id']}/decision", json=decision)
    assert result.status_code == 409
    assert "permitted bank verification" in result.text


def test_future_rule_approval_keeps_current_rule_applicable(env):
    _, client = env
    admin, second, owner = client("admin"), client("admin2"), client()
    original = admin.get("/api/rules").json()[0]
    body = {k: original[k] for k in ("rule_id", "config", "source_reference", "illustrative")}
    body.update(effective_from="2027-01-01", effective_to="2028-12-31")
    body["config"]["amounts"]["Engineering and Technology|undergraduate"] = 4000000
    proposed = admin.post("/api/admin/rules", json=body).json()
    assert second.post(f"/api/admin/rules/{proposed['id']}/approve", json={"notes": "Approve for the future effective period"}).status_code == 200
    inst = owner.get("/api/institutions").json()[0]
    request = {"institution_id": inst["id"], "programme_id": inst["programmes"][0]["id"]}
    assert owner.post("/api/requirements/calculate", json={**request, "as_of": "2026-10-24"}).json()["required_amount"] == 3500000
    assert owner.post("/api/requirements/calculate", json={**request, "as_of": "2027-03-01"}).json()["required_amount"] == 4000000


def test_mutated_required_workflow_does_not_change_existing_request(env):
    _, client = env
    admin = client("admin")
    existing = admin.get("/api/releases").json()[0]
    config = {"cells": ["PGRC"], "required_documents": ["release_request"], "allow_mock_for_demo": True, "require_regulatory_end": True}
    assert admin.put("/api/admin/config/workflow", json=config).status_code == 200
    unchanged = admin.get("/api/releases").json()[0]
    assert unchanged["workflow_snapshot"] == existing["workflow_snapshot"]
    assert any("Vigilance" in message for message in unchanged["blockers"])


def test_csv_formula_injection_escaped(env):
    factory, client = env
    c = client(); institution = c.get("/api/institutions").json()[0]
    with factory() as db:
        db.get(Institution, institution["id"]).name = '=HYPERLINK("https://example.org")'
        db.commit()
    text = c.get("/api/reports/export").text
    assert "'=HYPERLINK" in text


def test_oversized_upload_rejected(env):
    _, client = env
    c = client(); case = get_case(c)
    response = c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("large.pdf", b"%PDF-" + b"0" * settings.max_upload_bytes, "application/pdf")})
    assert response.status_code == 422


def test_database_migrations_and_raw_sql_audit_protection(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError
    db_url = f"sqlite:///{tmp_path / 'migration-test.db'}"
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env={**os.environ, "DATABASE_URL": db_url}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    engine = create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO audit_logs (id,created_at,entity_id,action,\"before\",\"after\",previous_hash,event_hash) VALUES ('00000000000000000000000000000001','2026-01-01','test','created','{}','{}','','hash')"))
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="append-only"):
            connection.execute(text("UPDATE audit_logs SET action='changed'"))
        with pytest.raises(IntegrityError, match="append-only"):
            connection.execute(text("DELETE FROM audit_logs"))
    engine.dispose()


def test_postgresql_migrations_render_without_a_server_or_credentials():
    # env.py's offline mode only needs a URL to pick the dialect; nothing connects, so a placeholder is enough.
    import os
    import subprocess
    import sys
    from pathlib import Path
    url = "postgresql+psycopg://placeholder:placeholder-password@localhost:5432/depositflow"
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head", "--sql"], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE risk_assessments" in result.stdout and "CREATE TRIGGER audit_no_change" in result.stdout
    assert "placeholder-password" not in result.stdout

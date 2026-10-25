"""Management reports, audit search, notifications, case assignment, bank-stated values and bulk import."""
import csv
import io
from datetime import date, timedelta

from sqlalchemy import select, update

from app.models import Document, ReleaseRequest, utcnow
from test_workflows import get_case, pdf_for

IMPORT_HEADER = "institution_code,programme,level,bank,branch,number,depositor_name,amount,issue_date,maturity_date,lien_details,regulatory_end_date\n"


def csv_rows(response):
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.text)))


def test_named_management_reports(env):
    _, client = env
    officer, owner = client("officer"), client()
    pending = csv_rows(officer.get("/api/reports/export?kind=pending_verification"))
    assert {"MATCH-001", "SHORT-002"} <= {r["Instrument"] for r in pending} and "RELEASE-006" not in {r["Instrument"] for r in pending}
    upcoming = csv_rows(officer.get("/api/reports/export?kind=upcoming_maturity"))
    maturity = next(r for r in upcoming if r["Instrument"] == "MATURITY-004")
    assert maturity["Days to maturity"] == "7" and maturity["Covers the security period"] == "No"
    intervention = csv_rows(officer.get("/api/reports/export?kind=intervention"))
    assert any(r["Reference"] == get_case(officer, "SHORT-002")["reference"] for r in intervention)
    assert owner.get("/api/reports/export?kind=intervention").status_code == 403
    own = csv_rows(owner.get("/api/reports/export?kind=pending_verification"))
    assert own and all(r["Institution"] == "Meridian Institute of Technology" for r in own)


def test_missing_documents_report_lists_release_documents(env):
    factory, client = env
    officer = client("officer")
    with factory() as db:
        release = db.scalar(select(ReleaseRequest))
        db.execute(update(Document).where(Document.deposit_id == release.deposit_id, Document.category == "affidavit").values(category="supporting"))
        db.commit()
    rows = csv_rows(officer.get("/api/reports/export?kind=missing_documents"))
    assert any("affidavit (release)" in r["Missing"] for r in rows)


def test_audit_search_filters_and_pages(env):
    _, client = env
    auditor = client("auditor")
    everything = auditor.get("/api/audit?limit=5").json()
    assert len(everything["items"]) == 5 and everything["total"] > 5 and "deposit_submitted" in everything["actions"]
    reference = get_case(auditor, "SHORT-002")["reference"]
    case_events = auditor.get(f"/api/audit?entity={reference}&limit=500").json()
    assert case_events["total"] > 0 and len({e["entity_id"] for e in case_events["items"]}) == 1
    submitted = auditor.get("/api/audit?action=deposit_submitted&limit=500").json()
    assert submitted["total"] == 9 and all(e["action"] == "deposit_submitted" for e in submitted["items"])
    assert all(e["actor_name"] == "System" for e in auditor.get("/api/audit?actor=system").json()["items"])
    assert auditor.get(f"/api/audit?actor=Ananya&action=deposit_submitted").json()["total"] == 6
    today = utcnow().date()  # audit timestamps are UTC
    assert auditor.get(f"/api/audit?date_from={today}&date_to={today}").json()["total"] == everything["total"]
    assert auditor.get(f"/api/audit?date_to={today - timedelta(days=30)}").json()["total"] == 0
    second_page = auditor.get("/api/audit?limit=5&offset=5").json()["items"]
    assert {e["id"] for e in second_page}.isdisjoint({e["id"] for e in everything["items"]})


def test_mark_all_notifications_read(env):
    _, client = env
    owner = client()
    assert any(not n["read"] for n in owner.get("/api/notifications").json())
    assert owner.post("/api/notifications/read-all").json()["marked"] > 0
    assert all(n["read"] for n in owner.get("/api/notifications").json())
    assert owner.post("/api/notifications/read-all").json()["marked"] == 0


def test_evaluation_details_for_officials(env):
    _, client = env
    details = client("officer").get("/api/risk/evaluation/details").json()
    assert {"intake", "after_bank_check"} == set(details["metrics"]["stages"]) and details["kinds"]["overlay_amount"]["problem"]
    assert all(m["score"] < details["metrics"]["thresholds"]["medium"] for m in details["misses"])
    assert client().get("/api/risk/evaluation/details").status_code == 403


def test_reassignment_rules(env):
    factory, client = env
    officer, admin = client("officer"), client("admin")
    case = get_case(officer)
    officer.post(f"/api/deposits/{case['id']}/assign")
    officer2 = next(u for u in admin.get("/api/admin/users").json() if u["email"] == "officer2@demo.local")
    clearance = next(u for u in admin.get("/api/admin/users").json() if u["email"] == "clearance@demo.local")
    reason = {"reason": "Workload balancing this week"}
    assert officer.post(f"/api/deposits/{case['id']}/assignment", json={**reason, "officer_id": officer2["id"]}).status_code == 403
    assert admin.post(f"/api/deposits/{case['id']}/assignment", json={**reason, "officer_id": clearance["id"]}).status_code == 422
    moved = admin.post(f"/api/deposits/{case['id']}/assignment", json={**reason, "officer_id": officer2["id"]}).json()
    assert moved["assigned_officer_id"] == officer2["id"] and moved["status"] == "under_review"
    assert any(e["action"] == "officer_reassigned" for e in moved["timeline"])
    second = client("officer2")
    handed_back = second.post(f"/api/deposits/{case['id']}/assignment", json={"officer_id": None, "reason": "Conflict of interest declared"}).json()
    assert handed_back["assigned_officer_id"] is None and handed_back["status"] == "submitted"


def test_bank_stated_values_are_compared_with_the_declaration(env):
    _, client = env
    officer = client("officer")
    case = get_case(officer)
    officer.post(f"/api/deposits/{case['id']}/assign")
    request = officer.post(f"/api/deposits/{case['id']}/verification/manual", json={"channel": "branch_confirmation"}).json()
    doc = officer.post(f"/api/deposits/{case['id']}/documents", data={"category": "bank_confirmation"},
                       files={"file": ("bank.pdf", pdf_for(case), "application/pdf")}).json()
    body = {"document_id": doc["id"], "source": "Branch manager letter", "reference": "BR-2026-0042", "finding": "confirmed",
            "observations": "Branch confirmed the deposit by letter.", "verified_on": str(date.today()),
            "confirmed_fields": {"amount": 2500000, "maturity_date": case["instrument"]["maturity_date"]}}
    assert officer.post(f"/api/verifications/{request['id']}/evidence", json=body).status_code == 200
    detail = officer.get(f"/api/deposits/{case['id']}").json()
    task = next(d for d in detail["discrepancies"] if d["code"].startswith("bank_confirmed_mismatch"))
    assert task["severity"] == "high" and "amount (bank: 2500000" in task["description"]
    assert any(s["key"] == "bank_confirmed_mismatch" for s in officer.get(f"/api/deposits/{case['id']}/risk").json()["signals"])


def test_bulk_import_checks_then_imports_valid_rows(env):
    _, client = env
    admin, owner = client("admin"), client()
    today = date.today()
    good = f"DEMO-INST-001,Engineering and Technology,undergraduate,Canara Bank,Main,LEGACY-0001,Meridian Institute of Technology,3500000,{today - timedelta(days=400)},{today + timedelta(days=700)},AICTE New Delhi,{today + timedelta(days=600)}\n"
    rows = (good + good  # repeated in the file
            + f"DEMO-INST-999,Engineering and Technology,undergraduate,Canara Bank,Main,LEGACY-0002,X Institute,3500000,{today},{today + timedelta(days=10)},,\n"
            + f"DEMO-INST-001,Engineering and Technology,undergraduate,Canara Bank,Main,LEGACY-0003,Meridian Institute of Technology,3500000,{today},{today - timedelta(days=10)},,\n"
            + f"DEMO-INST-001,Engineering and Technology,undergraduate,DEMO NATIONAL BANK,Main,match-001,Meridian Institute of Technology,3500000,{today},{today + timedelta(days=10)},,\n")
    upload = lambda commit: admin.post("/api/admin/import", data={"commit": str(commit).lower()}, files={"file": ("legacy.csv", IMPORT_HEADER + rows, "text/csv")})
    check = upload(False).json()
    assert (check["rows"], check["ready"], check["errors"], check["committed"]) == (5, 1, 4, False)
    errors = {r["row"]: " ".join(r["errors"]) for r in check["results"]}
    assert "appears earlier in this file" in errors[3] and "Unknown institution code" in errors[4]
    assert "Maturity must be after the issue date" in errors[5] and "already registered" in errors[6]
    assert not any(d["instrument"]["number"] == "LEGACY-0001" for d in admin.get("/api/deposits").json())
    done = upload(True).json()
    assert done["committed"] and done["results"][0]["status"] == "imported"
    imported = next(d for d in admin.get("/api/deposits").json() if d["instrument"]["number"] == "LEGACY-0001")
    assert imported["status"] == "submitted" and any(t["code"].startswith("missing_document") for t in admin.get(f"/api/deposits/{imported['id']}").json()["discrepancies"])
    assert upload(True).json()["ready"] == 0  # a re-run cannot import the same instrument twice
    assert owner.post("/api/admin/import", data={"commit": "false"}, files={"file": ("x.csv", IMPORT_HEADER, "text/csv")}).status_code == 403
    assert admin.post("/api/admin/import", files={"file": ("x.csv", "bank,number\nA,B\n", "text/csv")}).status_code == 422

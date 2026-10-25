"""Phase 2: the risk score orders queues, tightens release safeguards and stays hidden from institutions."""
import csv
import io
from datetime import date, timedelta

from sqlalchemy import select

from app.models import (AuditLog, Clearance, Discrepancy, Instrument, ReleaseRequest, SecurityDeposit, VerificationEvidence,
                        VerificationRequest)
from test_workflows import get_case


def set_thresholds(client, medium, high, critical):
    """Approve a policy that moves the seeded release case into a chosen level, as administrators would."""
    admin, admin2 = client("admin"), client("admin2")
    proposal = admin.post("/api/admin/risk-weights", json={"weights": {}, "thresholds": {"medium": medium, "high": high, "critical": critical},
                                                          "notes": "Test policy with lowered thresholds"}).json()
    assert admin2.post(f"/api/admin/risk-weights/{proposal['id']}/approve", json={"notes": "Approved for this test"}).status_code == 200


def release_case(client):
    authority = client("authority")
    return authority, authority.get("/api/releases").json()[0]


def approve(authority, release, **extra):
    return authority.post(f"/api/releases/{release['id']}/decision", json={"decision": "approved", "notes": "Reviewed all evidence on file", **extra})


def test_queue_sorts_and_filters_by_risk(env):
    _, client = env
    officer, owner = client("officer"), client()
    rows = officer.get("/api/deposits?sort=risk").json()
    scores = [r["risk"]["score"] for r in rows]
    assert scores == sorted(scores, reverse=True) and rows[0]["instrument"]["number"] == "SHORT-002"
    assert {r["risk"]["level"] for r in officer.get("/api/deposits?risk_level=medium").json()} == {"medium"}
    assert all("risk" not in r for r in owner.get("/api/deposits?sort=risk").json())


def test_institutions_never_see_scores(env):
    _, client = env
    officer, owner = client("officer"), client()
    case = get_case(owner)
    own = owner.get(f"/api/deposits/{case['id']}").json()
    assert "risk" not in own and all(e["action"] != "risk_assessed" for e in own["timeline"])
    assert "risk_distribution" not in owner.get("/api/dashboard").json()
    assert "Risk score" not in owner.get("/api/reports/export?kind=deposits").text
    official = officer.get(f"/api/deposits/{case['id']}").json()
    assert official["risk"]["level"] in ("low", "medium", "high", "critical")
    assert any(e["action"] == "risk_assessed" for e in official["timeline"])


def test_dashboard_and_export_show_risk_to_officials(env):
    _, client = env
    officer = client("officer")
    dashboard = officer.get("/api/dashboard").json()
    assert [d["name"] for d in dashboard["risk_distribution"]] == ["low", "medium", "high", "critical"]
    assert sum(d["value"] for d in dashboard["risk_distribution"]) == 9
    assert dashboard["risk_institutions"][0]["institution"] == "Meridian Institute of Technology"
    rows = list(csv.DictReader(io.StringIO(officer.get("/api/reports/export?kind=deposits").text)))
    assert rows[0]["Risk level"] in ("low", "medium", "high", "critical")


def test_high_risk_refuses_simulated_verification(env):
    _, client = env
    authority, release = release_case(client)
    vigilance = client("vigilance")
    clearance = next(c for c in release["clearances"] if c["cell"] == "Vigilance")
    vigilance.post(f"/api/clearances/{clearance['id']}/decision", json={"decision": "approved", "notes": "No vigilance concerns"})
    set_thresholds(client, 1, 2, 99)
    detail = authority.get("/api/releases").json()[0]
    assert detail["risk"]["level"] == "high"
    blocked = approve(authority, release)
    assert blocked.status_code == 409 and "simulated findings are not accepted" in blocked.text


def test_critical_risk_requires_vigilance_fresh_check_and_acknowledgement(env):
    factory, client = env
    with factory() as db:
        release = db.scalar(select(ReleaseRequest))
        # A workflow without Vigilance: the critical safeguard must add it.
        release.workflow_snapshot = {**release.workflow_snapshot, "cells": ["PGRC"]}
        for item in db.scalars(select(Clearance).where(Clearance.release_id == release.id, Clearance.cell == "Vigilance")).all():
            db.delete(item)
        evidence = db.scalar(select(VerificationEvidence).join(VerificationRequest).where(VerificationRequest.deposit_id == release.deposit_id))
        evidence.verified_on = date.today() - timedelta(days=10)
        db.commit()
    set_thresholds(client, 1, 2, 3)
    authority, detail = release_case(client)
    assert detail["risk"]["level"] == "critical" and detail["risk_acknowledgement_required"]
    assert any(c["cell"] == "Vigilance" and c["status"] == "pending" for c in detail["clearances"])
    unacknowledged = approve(authority, detail)
    assert unacknowledged.status_code == 409 and "risk explanation" in unacknowledged.text
    blocked = approve(authority, detail, risk_acknowledged=True).json()["detail"]["blockers"]
    assert any("simulated findings are not accepted" in b for b in blocked)
    with factory() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "risk_clearance_required"))
        evidence = db.scalar(select(VerificationEvidence).join(VerificationRequest).where(VerificationRequest.deposit_id == detail["deposit_id"]))
        evidence.simulated, db.get(VerificationRequest, evidence.request_id).channel = False, "branch_confirmation"
        db.scalar(select(Instrument).where(Instrument.deposit_id == detail["deposit_id"], Instrument.status == "active")).verification_status = "officially_confirmed"
        db.commit()
    blocked = approve(authority, detail, risk_acknowledged=True).json()["detail"]["blockers"]
    assert any("more than 7 days ago" in b for b in blocked) and any("Vigilance clearance" in b for b in blocked)


def test_decisions_record_the_risk_at_the_time(env):
    factory, client = env
    authority, release = release_case(client)
    authority.post(f"/api/releases/{release['id']}/decision", json={"decision": "returned", "notes": "Please attach the original receipt"})
    with factory() as db:
        event = db.scalar(select(AuditLog).where(AuditLog.action == "release_returned"))
        assert event.after["risk_level"] == "low" and "risk_score" in event.after


def test_institution_response_to_hidden_task_stays_generic(env):
    factory, client = env
    owner = client()
    case = get_case(owner)
    with factory() as db:
        deposit = db.get(SecurityDeposit, case["id"])
        task = Discrepancy(deposit_id=deposit.id, code="forensic_editing_software:doc", severity="warning",
                           description="PDF metadata names editing software (photoshop).", evidence_source="document_forensics", next_step="Inspect")
        db.add(task)
        db.commit()
        task_id = task.id
    response = owner.post(f"/api/discrepancies/{task_id}/respond", json={"notes": "This is the bank's original file"}).json()
    assert response["code"].startswith("document_review") and "photoshop" not in str(response)

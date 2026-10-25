"""Risk score: combination maths, signal mapping, persistence, access and weight governance."""
import pytest
from sqlalchemy import select

from app import risk
from app.models import AuditLog, Discrepancy, Instrument, RiskAssessment, SecurityDeposit
from test_workflows import get_case, payload
from test_risk_checks import text_pdf


def sig(category, weight, strength=1.0, discount=1.0):
    return {"category": category, "weight": weight, "strength": strength, "discount": discount}


def test_combination_is_bounded_noisy_or_with_caps():
    thresholds = risk.DEFAULT_THRESHOLDS
    assert risk.combine([], {}, thresholds) == (0, "low")
    # 1 − (1 − 0.5)(1 − 0.5) = 0.75
    assert risk.combine([sig("financial", 0.5), sig("identity", 0.5)], {}, thresholds) == (75.0, "high")
    # Many weak behaviour signals stay within the category cap.
    many = [sig("behaviour", 0.15) for _ in range(20)]
    assert risk.combine(many, {"behaviour": 0.3}, thresholds)[0] == 30.0
    # Strength and discount scale a signal; the score never exceeds 100.
    assert risk.combine([sig("financial", 0.5, strength=0.5, discount=0.5)], {}, thresholds)[0] == 12.5
    assert risk.combine([sig(c, 0.95) for c in risk.CATEGORIES], {}, thresholds)[0] <= 100


def test_contribution_is_the_drop_without_the_signal():
    signals = [sig("financial", 0.5), sig("identity", 0.2)]
    score, _ = risk.combine(signals, {}, risk.DEFAULT_THRESHOLDS)
    assert score == 60.0
    assert signals[0]["contribution"] == 40.0 and signals[1]["contribution"] == 10.0


@pytest.mark.parametrize("score,level", [(19.9, "low"), (20, "medium"), (50, "high"), (80, "critical")])
def test_levels(score, level):
    weight = score / 100
    assert risk.combine([sig("financial", weight)], {}, risk.DEFAULT_THRESHOLDS)[1] == level


@pytest.mark.parametrize("code,key", [("forensic_text_layer_mismatch_amount:d", "forensic_text_layer_mismatch"),
                                      ("forensic_conflicting_values_maturity_date:d", "forensic_conflicting_values"),
                                      ("extraction_missing_bank:d", "extraction_missing"), ("officer:abc", "officer_clarification"),
                                      ("mismatch_amount:d", "mismatch_amount"), ("coverage_gap:i", "coverage_gap"), ("something_new:x", None)])
def test_task_codes_map_to_signals(code, key):
    assert risk.signal_key(code) == key


def test_discount_follows_human_review():
    item = Discrepancy(status="open", severity="high", condition_active=True)
    assert risk.discount(item) == 1.0
    item.status = "resolution_proposed"
    assert risk.discount(item) == 0.5
    item.status, item.resolution_kind = "resolved", "officer_confirmed"
    assert risk.discount(item) == 0.1
    item.condition_active = False
    assert risk.discount(item) == 0.1  # resolved high-severity findings keep a trace
    warning = Discrepancy(status="resolved", severity="warning", resolution_kind="officer", condition_active=False)
    assert risk.discount(warning) == 0.0
    warning.resolution_kind, warning.condition_active = "automatic", True
    assert risk.discount(warning) == 0.0


def test_document_evidence_raises_the_score(env):
    _, client = env
    c, officer = client(), client("officer")
    case = c.post("/api/deposits", json={**payload(c, "RISK-DOC-01"), "lien_details": "AICTE"}).json()
    lines = ["Bank: TEST BANK", "FDR Number: RISK-DOC-01", f"Depositor Name: {case['institution_name']}", "Amount: INR 3500000.00",
             "Amount: INR 9500000.00", f"Issue Date: {case['instrument']['issue_date']}", f"Maturity Date: {case['instrument']['maturity_date']}"]
    c.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", text_pdf(lines), "application/pdf")})
    result = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert result["level"] in ("high", "critical")
    top = result["signals"][0]
    assert top["key"] == "forensic_conflicting_values" and top["task_code"].startswith("forensic_conflicting_values_amount")
    assert "not a finding of fraud" in result["notice"]


def test_bank_mismatch_and_resolution_move_the_score(env):
    _, client = env
    officer, second = client("officer"), client("officer2")
    case = get_case(officer, "AMOUNT-007")
    before = officer.get(f"/api/deposits/{case['id']}/risk").json()["score"]
    officer.post(f"/api/deposits/{case['id']}/assign")
    officer.post(f"/api/deposits/{case['id']}/verification/mock")
    flagged = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert flagged["score"] > before and any(s["key"] == "bank_mismatched" for s in flagged["signals"])
    task = next(d for d in officer.get(f"/api/deposits/{case['id']}").json()["discrepancies"] if d["code"].startswith("mock_bank"))
    officer.post(f"/api/discrepancies/{task['id']}/resolve", json={"notes": "Branch letter confirms the fixture amount was entered wrongly"})
    proposed = officer.get(f"/api/deposits/{case['id']}/risk").json()["score"]
    second.post(f"/api/discrepancies/{task['id']}/review", json={"decision": "confirm", "notes": "Checked the branch letter"})
    confirmed = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert flagged["score"] > proposed > confirmed["score"]
    assert [h["score"] for h in confirmed["history"]][-3:] == [flagged["score"], proposed, confirmed["score"]]


def test_assessments_are_deduplicated_append_only_and_audited(env):
    factory, _ = env
    with factory() as db:
        deposit = db.scalar(select(SecurityDeposit).join(Instrument).where(Instrument.number == "MATCH-001"))
        count = len(db.scalars(select(RiskAssessment).where(RiskAssessment.deposit_id == deposit.id)).all())
        risk.assess(db, deposit)
        risk.assess(db, deposit)
        db.commit()
        assert len(db.scalars(select(RiskAssessment).where(RiskAssessment.deposit_id == deposit.id)).all()) == count
        assert db.scalar(select(AuditLog).where(AuditLog.entity_id == deposit.id, AuditLog.action == "risk_assessed"))
        item = risk.latest(db, deposit.id)
        item.score = 1
        with pytest.raises(ValueError, match="append-only"):
            db.commit()


def test_every_seeded_case_is_scored(env):
    factory, _ = env
    with factory() as db:
        for deposit in db.scalars(select(SecurityDeposit)).all():
            assert risk.latest(db, deposit.id).engine_version == risk.ENGINE_VERSION


@pytest.mark.parametrize("role,status", [("institution", 403), ("officer", 200), ("authority", 200), ("auditor", 200)])
def test_risk_is_visible_to_officials_only(env, role, status):
    _, client = env
    c = client(role)
    case = get_case(client("officer"))
    assert c.get(f"/api/deposits/{case['id']}/risk").status_code == status


def test_weight_changes_need_a_second_administrator_and_rescore(env):
    _, client = env
    admin, admin2, officer = client("admin"), client("admin2"), client("officer")
    thresholds = {"medium": 20, "high": 50, "critical": 80}
    assert admin.post("/api/admin/risk-weights", json={"weights": {"made_up": 0.5}, "thresholds": thresholds, "notes": "Invalid signal name"}).status_code == 422
    assert admin.post("/api/admin/risk-weights", json={"weights": {}, "thresholds": {"medium": 60, "high": 50, "critical": 80}, "notes": "Thresholds out of order"}).status_code == 422
    proposal = admin.post("/api/admin/risk-weights", json={"weights": {"unverified": 0.3}, "thresholds": thresholds, "notes": "Unverified instruments matter more"}).json()
    assert admin.post(f"/api/admin/risk-weights/{proposal['id']}/approve", json={"notes": "Self approval"}).status_code == 403
    case = get_case(officer)
    before = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert admin2.post(f"/api/admin/risk-weights/{proposal['id']}/approve", json={"notes": "Reviewed with the bureau"}).status_code == 200
    after = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert after["weights_version"] == 1 and after["score"] > before["score"]
    second = admin2.post("/api/admin/risk-weights", json={"weights": {}, "thresholds": thresholds, "notes": "Return to default weights"}).json()
    admin.post(f"/api/admin/risk-weights/{second['id']}/approve", json={"notes": "Agreed"})
    listing = admin.get("/api/admin/risk-weights").json()
    assert listing["active"]["version"] == 2 and [v["status"] for v in listing["versions"]] == ["active", "superseded"]

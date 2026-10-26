"""Risk score: combination maths, signal mapping, persistence, access and weight governance."""
import pytest
from sqlalchemy import select

from app import risk
from app.models import AuditLog, Discrepancy, Instrument, RiskAssessment, SecurityDeposit
from test_workflows import get_case, payload
from test_risk_checks import text_pdf


def add_suspicion(factory, number, code="forensic_editing_software", severity="warning", resolution_kind=None):
    """Record a suspicious finding on a seeded case (optionally already resolved) and rescore it."""
    with factory() as db:
        deposit = db.scalar(select(SecurityDeposit).join(Instrument).where(Instrument.number == number))
        db.add(Discrepancy(deposit_id=deposit.id, code=f"{code}:test", severity=severity, description=f"Test finding: {code}",
                           evidence_source="test", next_step="Inspect", status="resolved" if resolution_kind else "open",
                           resolution_kind=resolution_kind, resolution="Reviewed in test" if resolution_kind else ""))
        db.flush()
        risk.assess(db, deposit)
        db.commit()
        return deposit.id


def sig(category, weight, strength=1.0, discount=1.0):
    return {"category": category, "weight": weight, "strength": strength, "discount": discount}


def test_combination_is_bounded_noisy_or_with_caps():
    thresholds = risk.DEFAULT_THRESHOLDS
    assert risk.combine([], {}, thresholds) == (0, "none")  # nothing suspicious: no score at all
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
                                      ("mismatch_amount:d", "mismatch_amount"), ("something_new:x", None),
                                      # Paperwork and status are requirements, not suspicion.
                                      ("extraction_missing_bank:d", None), ("officer:abc", None), ("coverage_gap:i", None),
                                      ("unverified:i", None), ("missing_document:i", None), ("amount_shortfall:i", None)])
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


def test_bank_mismatch_raises_the_score_and_vigilance_clears_it(env):
    _, client = env
    officer, vigilance = client("officer"), client("vigilance")
    case = get_case(officer, "AMOUNT-007")
    before = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert (before["score"], before["level"]) == (0, "none")   # not yet confirmed by the bank is not suspicion
    officer.post(f"/api/deposits/{case['id']}/assign")
    officer.post(f"/api/deposits/{case['id']}/verification/mock")
    flagged = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert flagged["score"] == 55 and any(s["key"] == "bank_mismatched" for s in flagged["signals"])
    task = next(d for d in officer.get(f"/api/deposits/{case['id']}").json()["discrepancies"] if d["code"].startswith("mock_bank"))
    note = {"notes": "Branch letter confirms the fixture amount was entered wrongly"}
    assert officer.post(f"/api/discrepancies/{task['id']}/resolve", json=note).status_code == 403   # escalated: not the officer's call
    assert vigilance.post(f"/api/discrepancies/{task['id']}/resolve", json=note).status_code == 200
    cleared = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert cleared["score"] < flagged["score"] and [h["score"] for h in cleared["history"]][-2:] == [flagged["score"], cleared["score"]]


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
    proposal = admin.post("/api/admin/risk-weights", json={"weights": {"forensic_editing_software": 0.4}, "thresholds": thresholds, "notes": "Editing software matters more"}).json()
    assert admin.post(f"/api/admin/risk-weights/{proposal['id']}/approve", json={"notes": "Self approval"}).status_code == 403
    add_suspicion(env[0], "MATCH-001")
    case = get_case(officer)
    before = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert admin2.post(f"/api/admin/risk-weights/{proposal['id']}/approve", json={"notes": "Reviewed with the bureau"}).status_code == 200
    after = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert after["weights_version"] == 1 and after["score"] > before["score"]
    second = admin2.post("/api/admin/risk-weights", json={"weights": {}, "thresholds": thresholds, "notes": "Return to default weights"}).json()
    admin.post(f"/api/admin/risk-weights/{second['id']}/approve", json={"notes": "Agreed"})
    listing = admin.get("/api/admin/risk-weights").json()
    assert listing["active"]["version"] == 2 and [v["status"] for v in listing["versions"]] == ["active", "superseded"]


def test_preview_shows_impact_without_storing_anything(env):
    factory, client = env
    admin, auditor, officer = client("admin"), client("auditor"), client("officer")
    add_suspicion(factory, "MATCH-001")   # editing software alone: 20, medium
    with factory() as db:
        stored = len(db.scalars(select(RiskAssessment)).all())
    lowered = {"weights": {}, "thresholds": {"medium": 25, "high": 50, "critical": 80}}
    preview = admin.post("/api/admin/risk-weights/preview", json=lowered).json()
    assert preview["cases"] == sum(preview["current"].values()) == sum(preview["proposed"].values())
    assert preview["proposed"]["low"] > preview["current"]["low"] and preview["changed"] == len(preview["changes"]) == 1
    assert all(c["from_level"] == "medium" and c["to_level"] == "low" for c in preview["changes"])
    assert auditor.post("/api/admin/risk-weights/preview", json=lowered).status_code == 200
    assert officer.post("/api/admin/risk-weights/preview", json=lowered).status_code == 403
    with factory() as db:
        assert len(db.scalars(select(RiskAssessment)).all()) == stored


def test_versions_name_people_and_caps_can_be_removed(env):
    _, client = env
    admin = client("admin")
    admin.post("/api/admin/risk-weights", json={"weights": {}, "category_caps": {}, "thresholds": {"medium": 20, "high": 50, "critical": 80},
                                                "notes": "Remove the behaviour cap for comparison"})
    version = admin.get("/api/admin/risk-weights").json()["versions"][0]
    assert version["proposed_by_name"] == "Aditi Verma" and version["approved_by_name"] is None
    assert version["category_caps"] == {}

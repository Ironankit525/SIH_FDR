"""Receipt arithmetic and the indexed comparison keys used by duplicate and reuse checks."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.consistency import maturity_problem
from app.extraction import structure
from app.models import Extraction, Instrument
from test_risk_checks import codes, text_pdf
from test_workflows import payload

ISSUE, FIVE_YEARS = "2026-01-01", "2030-12-31"  # 1825 days


@pytest.mark.parametrize("value,rate", [(3500000 * (1 + 0.075 * 5), 7.5), (3500000 * (1 + 0.075 / 4) ** 20, 7.5),
                                        (3500000 * (1 + 0.075 / 12) ** 60, 7.5), (3500000 * 1.375 * 1.004, 7.5), (4800000, None)])
def test_genuine_figures_pass_under_any_common_convention(value, rate):
    assert maturity_problem(3500000, value, ISSUE, FIVE_YEARS, rate) is None


def test_raised_principal_or_extended_term_is_caught():
    genuine_value = 1500000 * (1 + 0.075 * 5)
    assert "not above its principal" in maturity_problem(3500000, genuine_value, ISSUE, FIVE_YEARS, 7.5)
    extended = (date.fromisoformat(FIVE_YEARS) + timedelta(days=730)).isoformat()
    assert "does not fit" in maturity_problem(3500000, 3500000 * 1.375, ISSUE, extended, 7.5)
    assert "outside the usual range" in maturity_problem(3500000, 3500000 * 3, ISSUE, FIVE_YEARS)


def test_rate_and_maturity_value_are_read_but_not_mistaken_for_the_principal():
    fields, _ = structure("Principal Amount: Rs. 35,00,000.00\nRate of Interest: 7.25% p.a.\nMaturity Value: Rs. 47,68,750.00", "embedded_pdf_text")
    assert fields["amount"] == 3500000 and fields["rate"] == 7.25 and fields["maturity_value"] == 4768750


def test_inconsistent_receipt_is_flagged_and_hidden_from_the_institution(env):
    _, client = env
    owner, officer = client(), client("officer")
    case = owner.post("/api/deposits", json={**payload(owner, "ARITH-0001"), "lien_details": "AICTE"}).json()
    i = case["instrument"]
    lines = ["Bank: TEST BANK", "FDR Number: ARITH-0001", f"Depositor Name: {case['institution_name']}", "Amount: INR 3500000.00",
             f"Issue Date: {i['issue_date']}", f"Maturity Date: {i['maturity_date']}", "Rate of Interest: 7.5% p.a.", "Maturity Value: INR 1612500.00"]
    owner.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", text_pdf(lines), "application/pdf")})
    task = codes(officer.get(f"/api/deposits/{case['id']}").json())["maturity_value_inconsistent"]
    assert task["severity"] == "high" and task["evidence_source"] == "document_arithmetic"
    assert "maturity_value_inconsistent" not in codes(owner.get(f"/api/deposits/{case['id']}").json())
    risk = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert any(s["key"] == "maturity_value_inconsistent" for s in risk["signals"])


def test_comparison_keys_follow_every_save(env):
    factory, client = env
    owner = client()
    case = owner.post("/api/deposits", json={**payload(owner, "KEY-12/34"), "bank": "State Bank of India Ltd"}).json()
    with factory() as db:
        inst = db.get(Instrument, case["instrument"]["id"])
        assert (inst.number_key, inst.bank_key) == ("KEY1234", "STATEINDIA")
        inst.number = "KEY-99/99"
        db.commit()
        assert db.get(Instrument, inst.id).number_key == "KEY9999"
        assert all(e.text_fingerprint for e in db.scalars(select(Extraction)).all() if len(e.original_text) > 40)
    # The indexed keys still treat abbreviations and formatting as the same instrument.
    assert owner.post("/api/deposits", json={**payload(owner, "key9999"), "bank": "SBI"}).status_code == 409

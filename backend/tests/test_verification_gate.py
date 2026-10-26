"""The boundary around officers: verification needs the bank, the paperwork and no uncleared suspicion;
suspicion at the limit goes to Vigilance, and the case officer cannot clear it."""
from datetime import date

from test_workflows import get_case, pdf_for


def note(text="Reviewed the evidence on file for this case"):
    return {"notes": text}


def test_awaiting_the_bank_is_a_status_not_a_score(env):
    _, client = env
    officer = client("officer")
    case = get_case(officer)
    risk = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert (risk["score"], risk["level"], risk["signals"]) == (0, "none", [])
    bank = next(c for c in officer.get(f"/api/deposits/{case['id']}").json()["readiness"] if c["key"] == "bank")
    assert not bank["met"] and bank["detail"] == "The bank has not confirmed yet."


def test_verification_complete_needs_bank_paperwork_and_resolved_tasks(env):
    _, client = env
    officer, owner = client("officer"), client()
    case = get_case(officer)
    officer.post(f"/api/deposits/{case['id']}/assign")
    refused = officer.post(f"/api/deposits/{case['id']}/verification-complete", json=note())
    assert refused.status_code == 409 and "bank has not confirmed" in refused.text
    officer.post(f"/api/deposits/{case['id']}/verification/mock")              # MATCH-001: the bank confirms
    detail = officer.get(f"/api/deposits/{case['id']}").json()
    for task in [t for t in detail["discrepancies"] if t["status"] != "resolved"]:
        officer.post(f"/api/discrepancies/{task['id']}/resolve", json=note())
    assert all(c["met"] for c in officer.get(f"/api/deposits/{case['id']}").json()["readiness"])
    verified = officer.post(f"/api/deposits/{case['id']}/verification-complete", json=note()).json()
    assert verified["status"] == "verified" and verified["verified_by"]
    # Any new evidence means verifying again.
    owner.post(f"/api/deposits/{case['id']}/documents", files={"file": ("receipt.pdf", pdf_for(case), "application/pdf")})
    reopened = officer.get(f"/api/deposits/{case['id']}").json()
    assert reopened["verified_at"] is None and reopened["status"] == "under_review"


def test_release_cannot_be_requested_before_verification(env):
    _, client = env
    owner = client()
    case = get_case(owner)
    response = owner.post(f"/api/deposits/{case['id']}/release", json={"kind": "release", "reason": "Requesting release after the term"})
    assert response.status_code == 409 and "complete verification" in response.text


def test_suspicion_at_the_limit_goes_to_vigilance(env):
    _, client = env
    officer, vigilance, pgrc, owner = client("officer"), client("vigilance"), client("clearance"), client("institution2")
    case = get_case(officer, "AMOUNT-007")
    officer.post(f"/api/deposits/{case['id']}/assign")
    officer.post(f"/api/deposits/{case['id']}/verification/mock")              # bank: amount differs (55)
    detail = officer.get(f"/api/deposits/{case['id']}").json()
    assert detail["escalated"] and not next(c for c in detail["readiness"] if c["key"] == "suspicion")["met"]
    assert case["id"] in {d["id"] for d in vigilance.get("/api/deposits?escalated=true").json()}
    assert "escalated_at" not in owner.get(f"/api/deposits/{case['id']}").json()   # the institution is not told
    task = next(t for t in detail["discrepancies"] if t["code"].startswith("mock_bank"))
    assert task["suspicious"]
    assert officer.post(f"/api/discrepancies/{task['id']}/resolve", json=note()).status_code == 403
    assert pgrc.post(f"/api/discrepancies/{task['id']}/resolve", json=note()).status_code == 403     # only the Vigilance cell
    assert vigilance.post(f"/api/deposits/{case['id']}/vigilance-clearance", json=note()).status_code == 409  # findings still open
    assert vigilance.post(f"/api/discrepancies/{task['id']}/resolve", json=note()).status_code == 200
    cleared = vigilance.post(f"/api/deposits/{case['id']}/vigilance-clearance", json=note()).json()
    assert cleared["escalated"] is False
    # Cleared suspicion does not replace the bank: the bank still has not confirmed this amount.
    refused = officer.post(f"/api/deposits/{case['id']}/verification-complete", json=note())
    assert refused.status_code == 409 and "bank" in refused.text.lower()


def test_bank_with_no_record_is_suspicion(env):
    _, client = env
    officer = client("officer")
    case = get_case(officer, "UNKNOWN-003")
    officer.post(f"/api/deposits/{case['id']}/assign")
    officer.post(f"/api/deposits/{case['id']}/verification/mock")
    risk = officer.get(f"/api/deposits/{case['id']}/risk").json()
    assert any(s["key"] == "bank_no_record" for s in risk["signals"]) and risk["level"] == "high"
    assert officer.get(f"/api/deposits/{case['id']}").json()["escalated"]

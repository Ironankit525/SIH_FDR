"""Tests for the Bank role and institution-officer-bank FDR verification workflow."""
from datetime import date
import pytest
from sqlalchemy import select
from app.models import SecurityDeposit, Instrument, VerificationRequest, VerificationEvidence, Discrepancy, User
from app.workflows import current_instrument


def test_bank_user_auth(env):
    factory, client = env
    bank_client = client("bank")
    me = bank_client.get("/api/auth/me").json()
    assert me["role"] == "bank"
    assert me["bank_name"] == "DEMO NATIONAL BANK"


def test_officer_forward_to_bank(env):
    factory, client = env
    officer_client = client("officer")

    # Find a submitted deposit
    with factory() as db:
        deposit = db.scalar(select(SecurityDeposit).join(Instrument).where(Instrument.number == "SHORT-002"))
        deposit_id = deposit.id

    # Assign to officer
    assign_res = officer_client.post(f"/api/deposits/{deposit_id}/assign")
    assert assign_res.status_code in (200, 409)

    # Forward to DEMO NATIONAL BANK
    res = officer_client.post(
        f"/api/deposits/{deposit_id}/verification/forward-to-bank",
        json={"bank_name": "DEMO NATIONAL BANK", "notes": "Please verify instrument authenticity."}
    )
    assert res.status_code == 201, res.text
    detail = res.json()
    verifications = detail["verifications"]
    bank_req = next((v for v in verifications if v.get("bank_name") == "DEMO NATIONAL BANK"), None)
    assert bank_req is not None
    assert bank_req["status"] == "sent"
    assert bank_req["officer_notes"] == "Please verify instrument authenticity."

    # Cannot forward duplicate active request to the same bank
    res_dup = officer_client.post(
        f"/api/deposits/{deposit_id}/verification/forward-to-bank",
        json={"bank_name": "DEMO NATIONAL BANK", "notes": "Duplicate attempt"}
    )
    assert res_dup.status_code == 409


def test_bank_overview_and_isolation(env):
    factory, client = env

    # Bank 1 client
    bank1 = client("bank")
    overview = bank1.get("/api/bank/overview").json()
    assert overview["bank_name"] == "DEMO NATIONAL BANK"
    assert overview["total_requests"] >= 1

    queue = bank1.get("/api/bank/verifications").json()
    assert len(queue) >= 1
    req_id = queue[0]["id"]

    # Bank 1 can open detail and it transitions to under_verification
    detail_res = bank1.get(f"/api/bank/verifications/{req_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["request"]["status"] == "under_verification"
    assert "instrument" in detail
    assert "institution" in detail
    assert "documents" in detail

    # Bank 2 client
    bank2 = client("bank2")
    overview2 = bank2.get("/api/bank/overview").json()
    assert overview2["bank_name"] == "STATE BANK OF INDIA"
    assert overview2["total_requests"] == 0

    queue2 = bank2.get("/api/bank/verifications").json()
    assert len(queue2) == 0

    # Bank 2 cannot access Bank 1's request
    detail_res2 = bank2.get(f"/api/bank/verifications/{req_id}")
    assert detail_res2.status_code == 404

    # Bank 2 cannot decide Bank 1's request
    decide_res2 = bank2.post(
        f"/api/bank/verifications/{req_id}/decision",
        json={"decision": "verified", "remarks": "Unauthorized verify"}
    )
    assert decide_res2.status_code == 404


def test_bank_verify_decision(env):
    factory, client = env
    # Bank 1
    bank1 = client("bank")
    queue = bank1.get("/api/bank/verifications").json()
    req_id = queue[0]["id"]
    deposit_id = queue[0]["deposit_id"]

    # Decision validation: rejection requires >= 10 chars remarks
    short_res = bank1.post(
        f"/api/bank/verifications/{req_id}/decision",
        json={"decision": "rejected", "remarks": "Too short"}
    )
    assert short_res.status_code == 422

    # Decision validation: additional_info_required requires >= 10 chars remarks
    short_info_res = bank1.post(
        f"/api/bank/verifications/{req_id}/decision",
        json={"decision": "additional_info_required", "remarks": "Too short"}
    )
    assert short_info_res.status_code == 422

    # Valid verification
    decide_res = bank1.post(
        f"/api/bank/verifications/{req_id}/decision",
        json={
            "decision": "verified",
            "remarks": "FDR confirmed genuine and verified against core banking records."
        }
    )
    assert decide_res.status_code == 200, decide_res.text
    data = decide_res.json()
    assert data["request"]["status"] == "verified"
    assert data["request"]["bank_decision"] == "verified"
    assert data["evidence"]["finding"] == "confirmed"

    # Officer checks the result
    officer = client("officer")
    dep_detail = officer.get(f"/api/deposits/{deposit_id}").json()
    assert dep_detail["instrument"]["verification_status"] == "bank_verified"
    v_item = next(v for v in dep_detail["verifications"] if v["id"] == req_id)
    assert v_item["status"] == "verified"
    assert v_item["bank_decision"] == "verified"
    assert v_item["bank_remarks"] == "FDR confirmed genuine and verified against core banking records."
    assert v_item["bank_user_name"] == "Vikram Malhotra"
    assert v_item["bank_verified_at"] is not None


def test_bank_rejection_and_additional_info(env):
    factory, client = env
    # Officer forwards another case
    officer = client("officer")
    with factory() as db:
        dep = db.scalar(select(SecurityDeposit).join(Instrument).where(Instrument.number == "UNKNOWN-003"))
        dep_id = dep.id
    officer.post(f"/api/deposits/{dep_id}/assign")
    fwd = officer.post(
        f"/api/deposits/{dep_id}/verification/forward-to-bank",
        json={"bank_name": "DEMO NATIONAL BANK", "notes": "Check UNKNOWN-003"}
    ).json()
    req_id = next(v["id"] for v in fwd["verifications"] if v["bank_name"] == "DEMO NATIONAL BANK")

    # Bank logs in and requests additional info
    bank1 = client("bank")
    info_res = bank1.post(
        f"/api/bank/verifications/{req_id}/decision",
        json={
            "decision": "additional_info_required",
            "remarks": "Please provide the branch manager stamp and joint endorsement document."
        }
    )
    assert info_res.status_code == 200
    info_data = info_res.json()
    assert info_data["request"]["bank_decision"] == "additional_info_required"

    # Officer sees clarification needed
    officer_check = client("officer")
    dep_detail = officer_check.get(f"/api/deposits/{dep_id}").json()
    assert dep_detail["status"] == "clarification_required"
    assert dep_detail["instrument"]["verification_status"] == "bank_info_requested"
    assert any("bank requested additional information" in d["description"].lower() for d in dep_detail["discrepancies"])


def test_unauthorized_cross_role_access(env):
    factory, client = env
    # Bank user cannot access officer endpoints
    bank = client("bank")
    res_assign = bank.post("/api/deposits/some-id/assign")
    assert res_assign.status_code == 403

    res_admin = bank.get("/api/admin/users")
    assert res_admin.status_code == 403

    # Officer cannot access bank-only endpoints
    officer = client("officer")
    res_bank_queue = officer.get("/api/bank/verifications")
    assert res_bank_queue.status_code == 403

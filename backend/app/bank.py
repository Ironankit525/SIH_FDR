"""Adapter contract. No live bank integration or bank credentials are assumed."""
from datetime import date
from typing import Protocol
from sqlalchemy import select
from .matching import same_amount, same_bank, same_name, same_text
from .models import MockBankRecord


class BankAdapter(Protocol):
    def verify(self, instrument) -> dict: ...


class MockBankAdapter:
    def __init__(self, db):
        self.db = db

    def verify(self, instrument):
        record = self.db.scalar(select(MockBankRecord).where(MockBankRecord.number == instrument.number))
        response = {"simulated": True, "source": "SIMULATED / MOCK BANK DATA", "finding": "inconclusive", "fields": {}, "observations": ""}
        if not record:
            response["observations"] = "Unknown reference in the fictional bank dataset. Further review is required; this is not proof of fraud."
        elif not record.available:
            response["finding"] = "pending"
            response["observations"] = "Simulated bank service is unavailable for this fixture. Retry or use authorised manual verification."
        else:
            response["fields"] = record.fields
            # Dates matter as much as amounts: an extended maturity is a typical alteration.
            mismatch = [key for key in ("amount", "depositor_name", "bank", "issue_date", "maturity_date") if key in record.fields
                        and not {"amount": same_amount, "bank": same_bank, "depositor_name": same_name}.get(key, same_text)(record.fields[key], getattr(instrument, key))]
            response["finding"] = "mismatched" if mismatch else "confirmed"
            response["observations"] = "Mismatched fields: " + ", ".join(mismatch) if mismatch else "Submitted fields match the fictional bank fixture."
            if record.fields.get("maturity_date", "9999") <= date.today().isoformat():
                response["observations"] += " The fictional instrument has matured; release still requires authorisation."
        return response

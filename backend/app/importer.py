"""Bulk import of existing security deposits from CSV, with a dry run that reports every problem by row."""
import csv
import io
import secrets

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from .audit import audit
from .matching import normalise_bank, normalise_number
from .models import Institution, Instrument, Programme, SecurityDeposit, utcnow
from .rules import calculate
from .schemas import DepositInput
from .workflows import detect, instrument_conflicts

REQUIRED = ["institution_code", "programme", "level", "bank", "branch", "number", "depositor_name", "amount", "issue_date", "maturity_date"]
OPTIONAL = ["instrument_type", "validity_date", "lien_details", "regulatory_end_date", "renewal_due_date"]
MAX_ROWS = 2000
MAX_BYTES = 1024 * 1024


def read_rows(data: bytes):
    if len(data) > MAX_BYTES:
        raise HTTPException(422, "Import files are limited to 1 MB; split larger files")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Save the file as UTF-8 CSV")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in reader.fieldnames or []]
    missing = [column for column in REQUIRED if column not in header]
    if missing:
        raise HTTPException(422, "Missing columns: " + ", ".join(missing))
    rows = [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]
    if not rows:
        raise HTTPException(422, "The file has no data rows")
    if len(rows) > MAX_ROWS:
        raise HTTPException(422, f"Import at most {MAX_ROWS} rows at a time")
    return rows


def check(db, row, seen):
    errors = []
    institution = db.scalar(select(Institution).where(Institution.code == row["institution_code"]))
    programme = institution and db.scalar(select(Programme).where(Programme.institution_id == institution.id,
                                                                  Programme.name == row["programme"], Programme.level == row["level"]))
    if not institution:
        errors.append(f"Unknown institution code '{row['institution_code']}'")
    elif not programme:
        errors.append(f"{institution.name} has no programme '{row['programme']}' at level '{row['level']}'")
    values = {key: row[key] for key in REQUIRED[3:]} | {key: row.get(key) or None for key in OPTIONAL}
    values["instrument_type"] = values["instrument_type"] or "FDR"
    values["lien_details"] = values["lien_details"] or ""
    body = None
    try:
        body = DepositInput.model_validate({**values, "programme_id": programme.id if programme else "unknown"})
    except ValidationError as exc:
        errors += [f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg'].removeprefix('Value error, ')}" for e in exc.errors()]
    if body:
        key = (normalise_bank(body.bank), normalise_number(body.number))
        if instrument_conflicts(db, body.bank, body.number)[0]:
            errors.append(f"Instrument {body.number} at {body.bank} is already registered")
        elif key in seen:
            errors.append(f"Instrument {body.number} at {body.bank} appears earlier in this file")
        seen.add(key)
    return institution, programme, body, errors


def run(db, user, rows, filename, commit):
    seen, results = set(), []
    for index, row in enumerate(rows):
        institution, programme, body, errors = check(db, row, seen)
        result = {"row": index + 2, "institution_code": row["institution_code"], "number": row["number"], "errors": errors,
                  "status": "error" if errors else ("imported" if commit else "ready")}
        if commit and not errors:
            requirement = calculate(db, institution, programme)
            deposit = SecurityDeposit(institution_id=institution.id, programme_id=programme.id,
                                      reference="DF-" + str(utcnow().year) + "-" + secrets.token_hex(3).upper(),
                                      rule_version_id=requirement["rule_version_id"], required_amount=requirement["required_amount"],
                                      requirement_snapshot=requirement, regulatory_end_date=body.regulatory_end_date,
                                      renewal_due_date=body.renewal_due_date, status="submitted", submitted_by=user.id, submitted_at=utcnow())
            db.add(deposit)
            db.flush()
            db.add(Instrument(deposit_id=deposit.id, **body.model_dump(exclude={"programme_id", "regulatory_end_date", "renewal_due_date"})))
            db.flush()
            audit(db, user, "deposit_imported", deposit.id, institution.id, after={"source": filename, "row": result["row"], "reference": deposit.reference})
            # Imported records go through the same checks; most will first need their receipt uploaded.
            detect(db, deposit)
            result["reference"] = deposit.reference
        results.append(result)
    return {"rows": len(results), "ready": sum(r["status"] != "error" for r in results), "errors": sum(r["status"] == "error" for r in results),
            "committed": commit, "results": results}

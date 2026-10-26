"""Prepare local demo data, the two test receipts, and their independent mock-bank records."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'demo-data/receipt-tests'


def receipt(path, fields):
    if path.exists():
        with pymupdf.open(path) as existing:
            text = existing[0].get_text() if len(existing) == 1 else ''
            if not all(value in text for value in (fields['number'], fields['depositor_name'],
                       f"{fields['amount']:.2f}", fields['issue_date'], fields['maturity_date'], 'FICTIONAL DEMO')):
                raise ValueError(f'{path.name} differs from the fixture; preserved without overwriting.')
        return
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=720, height=940)
        navy, red = (0.09, 0.16, 0.24), (0.65, 0.12, 0.12)
        page.draw_rect(pymupdf.Rect(30, 30, 690, 910), color=navy, width=1.3)
        page.draw_rect(pymupdf.Rect(30, 30, 690, 76), color=None, fill=(0.96, 0.92, 0.89))
        page.insert_text((48, 60), 'FICTIONAL DEMO - NOT A REAL BANK INSTRUMENT', fontsize=17, color=red)
        page.insert_text((48, 119), fields['bank'], fontsize=26, color=navy)
        page.insert_text((48, 153), 'FIXED DEPOSIT RECEIPT', fontsize=22, color=navy)
        page.insert_text((48, 184), 'Branch: ' + fields['branch'], fontsize=16)
        page.draw_line((48, 205), (672, 205), color=navy)
        rows = [('FDR NUMBER', fields['number']), ('DEPOSITOR / INSTITUTION NAME', fields['depositor_name']),
                ('PRINCIPAL DEPOSIT AMOUNT (INR)', f"{fields['amount']:.2f}"),
                ('ISSUE DATE (YYYY-MM-DD)', fields['issue_date']), ('MATURITY DATE (YYYY-MM-DD)', fields['maturity_date'])]
        for index, (label, value) in enumerate(rows):
            y = 236 + index * 76
            page.insert_text((48, y), label, fontsize=12, color=(0.3, 0.35, 0.4))
            page.insert_text((48, y + 30), value, fontsize=20 if index == 1 else 22, color=navy)
        page.draw_line((48, 612), (672, 612), color=navy)
        page.insert_text((48, 642), 'HOLDING ARRANGEMENT - FICTIONAL TEST DETAILS', fontsize=12, color=navy)
        page.insert_text((48, 671), 'Joint holders: Depositor institution and AICTE.', fontsize=18)
        page.insert_text((48, 704), 'Lien: Deposit pledged in favour of AICTE.', fontsize=18)
        page.draw_rect(pymupdf.Rect(48, 744, 298, 818), color=navy)
        page.insert_text((65, 774), 'SIMULATED BANK STAMP', fontsize=16, color=navy)
        page.insert_text((65, 799), 'FOR SOFTWARE TESTING ONLY', fontsize=12, color=navy)
        page.insert_text((48, 856), 'No financial value. No real bank signature or digital certificate.', fontsize=14, color=red)
        page.insert_text((48, 881), 'Independent confirmation is provided only by the local mock-bank dataset.', fontsize=12)
        pdf.set_metadata({'title': 'Fictional FDR receipt for DepositFlow testing', 'author': 'DepositFlow demo fixture'})
        pdf.save(path, deflate=True)


def main():
    os.chdir(ROOT / 'backend')
    sys.path.insert(0, str(ROOT / 'backend'))
    from sqlalchemy import select
    from app.config import settings
    if settings.environment != 'development' or settings.database_url != 'sqlite:///./.data/depositflow.db' or settings.storage_backend != 'local':
        raise SystemExit('This helper supports only the default local SQLite development setup.')
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True)
    subprocess.run([sys.executable, '-m', 'app.seed'], check=True)
    from app.audit import audit
    from app.bank import MockBankAdapter
    from app.db import SessionLocal
    from app.models import Institution, MockBankRecord, User
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = [
        {'kind': 'correct', 'number': 'TEST-VALID-001', 'amount': 3500000,
         'filename': 'CORRECT-TEST-VALID-001.pdf', 'expected_mock_finding': 'confirmed'},
        {'kind': 'altered', 'number': 'TEST-ALTERED-001', 'amount': 5000000,
         'filename': 'INCORRECT-TEST-ALTERED-001.pdf', 'expected_mock_finding': 'mismatched'},
    ]
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == 'institution@demo.local'))
        if owner is None:
            raise SystemExit('The expected demo institution is missing; existing data was preserved.')
        institution = db.get(Institution, owner.institution_id)
        for case in cases:
            fields = {'bank': 'EXAMPLE LEARNING BANK', 'branch': 'DEMO BRANCH', 'depositor_name': institution.name,
                      'issue_date': '2026-01-15', 'maturity_date': '2034-01-15',
                      'number': case['number'], 'amount': case['amount']}
            bank_fields = {key: value for key, value in fields.items() if key != 'branch'}
            bank_fields['amount'] = 3500000.0
            fixture = db.scalar(select(MockBankRecord).where(MockBankRecord.number == case['number']))
            if fixture is not None:
                if fixture.fields != bank_fields or not fixture.available:
                    raise SystemExit('An existing mock-bank fixture differs. Preserved without overwriting.')
            else:
                fixture = MockBankRecord(number=case['number'], fields=bank_fields, available=True)
                db.add(fixture)
                db.flush()
                audit(db, None, 'demo_bank_fixture_created', fixture.id, institution.id,
                      after={'fictional': True, 'number': case['number'], 'fields': bank_fields})
            finding = MockBankAdapter(db).verify(SimpleNamespace(**fields))
            if finding['finding'] != case['expected_mock_finding']:
                raise SystemExit('Unexpected mock-bank comparison; transaction rolled back.')
            receipt(OUTPUT / case['filename'], fields)
            case.update(institution_form=fields, mock_bank=bank_fields,
                        sha256=hashlib.sha256((OUTPUT / case['filename']).read_bytes()).hexdigest())
        db.commit()
    (OUTPUT / 'expected-results.json').write_text(json.dumps(cases, indent=2) + '\n')
    print('Demo ready: receipts in demo-data/receipt-tests; both bank fixtures contain INR 3500000.')
    print('Correct form: mock confirmed. Altered INR 5000000 form: amount mismatch.')
    print('Existing records preserved. Create the two deposits through the portal to test the workflow.')


if __name__ == '__main__':
    main()

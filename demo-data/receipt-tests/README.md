# Fictional receipt test pair

These documents have no financial value and are not issued by a real bank.
On each fresh checkout, run `.venv/bin/python scripts/prepare_team_demo.py` from the project root to generate these PDFs and add their reference records to that laptop's local demo database. See [team setup](../../docs/TEAM_TESTING.md).
Both independent mock-bank records contain INR 3500000.00.

| Field | Correct PDF | Altered PDF |
| --- | --- | --- |
| FDR number | TEST-VALID-001 | TEST-ALTERED-001 |
| Amount to enter in the institution form | 3500000 | 5000000 |
| Bank | EXAMPLE LEARNING BANK | EXAMPLE LEARNING BANK |
| Branch | DEMO BRANCH | DEMO BRANCH |
| Depositor | Meridian Institute of Technology | Meridian Institute of Technology |
| Issue date | 2026-01-15 | 2026-01-15 |
| Maturity date | 2034-01-15 | 2034-01-15 |
| Expected mock-bank finding | Mock confirmed | Mock mismatched: amount |

1. Sign in as institution@demo.local (default password: DemoFlow2026!).
2. Create two new FDR deposits for Engineering and Technology, using the table.
3. Upload the corresponding PDF as an Instrument document. Leave optional regulatory-end and renewal dates blank for this extraction/bank test.
4. Wait for extraction and inspect Evidence comparison. The VLM may misread fields; compare with the original and retain any correction history.
5. Submit each case. As officer@demo.local, assign each case to yourself and run Bank verification > Run mock verification.
6. Expect a matching fixture for the correct form and an amount mismatch for the altered form. VLM warnings remain subject to officer review.

The altered PDF intentionally contains only the altered amount. The expected bank amount is in the separate fixture, not embedded as a hint in the receipt.
The stamp and holding/lien details are simulated. A matching test receipt does not imply regulatory clearance or release eligibility.
No deposit cases or release approvals were created by this fixture preparation. Bank maturity is not the regulatory security-period end.

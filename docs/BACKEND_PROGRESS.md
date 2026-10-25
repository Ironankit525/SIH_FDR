# Backend improvements and current scope

The portal keeps its existing SQL database. Local development uses SQLite without Docker; PostgreSQL remains the optional deployment database. MongoDB preparation is archived under the ignored `.data/` directory and is not part of the active application.

## VLM later

`EXTRACTION_PROVIDER=ocr` is the default. Existing PDF text extraction and Tesseract continue to work without a model server. No trained VLM is connected or downloaded. The optional extraction-provider interface can be adapted and tested against the trained model when integration is requested later.

## Implemented safeguards

- Institution declarations, document extraction, human corrections and bank evidence remain separate. The comparison screen preserves raw values and labels simulated bank findings.
- The case progress panel shows outstanding work and the next action for the signed-in role.
- Release approval checks prior review history, preventing a previous reviewer from becoming the final approver even after reassignment. Missing required clearance records and in-progress receipt extraction block approval.
- Extraction jobs persist their attempt count and worker claim. Expired claims can recover; delayed results from an old claim cannot overwrite a new claim. Retries are bounded and inference runs outside database transactions.
- Extraction records retain their provider and document checksum. Errors shown to users omit unexpected internal exception details.
- Audit appends serialize through a per-entity chain head in the same transaction. Existing update/delete protections remain. This is tamper evidence, not protection against a privileged database owner.

## Apply the update

Stop the old backend before applying migrations, retain a database backup, then run `python3 scripts/dev.py` from the project root. The launcher applies migrations and seeds idempotently; do not run the demo reset script to upgrade an existing database.

Rules remain illustrative and bank adapters remain simulated/manual. These changes do not certify AICTE compliance or enable automatic fraud decisions or automatic release.

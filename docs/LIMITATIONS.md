# Known limits and remaining work

This is a working hackathon prototype with production-oriented boundaries, not a certified production deployment.

## Deliberate local choices

- The default runtime is SQLite, encrypted local files and one in-process scheduler to avoid Docker memory pressure. Run a single API worker in this mode. PostgreSQL/MinIO/Redis/Celery code and configuration are included, but the full optional stack was not launched or load-tested on this machine.
- Lightweight uploads have format/structure validation but no antivirus unless ClamAV is configured. The UI displays the scan status. Production configuration requires a scanner and refuses uploads if it is unavailable.
- Local sessions use HTTP and non-Secure cookies on loopback only. Production requires TLS termination, `COOKIE_SECURE=true`, proper origin settings and explicit secret keys. Database disk encryption, backups, restore exercises, key rotation, non-owner database roles, bucket-scoped service credentials in place of local MinIO administrator credentials, and production infrastructure hardening are deployment work.
- Local background processing is intended for small demos. OCR runs in a background thread or Celery worker, with file/page/pixel limits and OCR timeouts. Durable claims, bounded retries, expired-claim recovery and one extraction at a time per process are implemented. Stronger process/container isolation and deployment load testing remain necessary at scale.

## External dependencies

- Trained VLM integration is deferred. The application defaults to OCR and requires no model endpoint or model download. Optional provider hooks are inactive; compatibility with the user's trained model has not been tested. MongoDB migration work is archived and the active runtime remains SQLAlchemy with SQLite/PostgreSQL.
- No live AICTE access or bank partnership is available. The mock-bank dataset is fictional and disabled in production. The `BankAdapter` protocol is the extension point; a real adapter needs institutional authorisation, contracts, authentication, mapping, retries and provenance verification.
- Manual verification trusts the assigned officer's judgement and uploaded authorised confirmation. It is not an automatic cryptographic verification of bank correspondence.
- Rule values and clearance requirements are illustrative. They need formal review against current applicable AICTE requirements, amendments and case-specific conditions. Current rule configuration can be edited through authenticated APIs; the UI provides a focused illustrative Engineering-amount proposal form rather than a general rules authoring language.
- Notifications are real in-app records with a development email-outbox representation; no SMTP/SMS provider is integrated. Delivery receipts, retries and provider credentials are future integrations.

## Workflow scope

- Supported uploads are PDF/PNG/JPEG, at most 10 MB and 15 PDF pages. Heuristic field extraction supports labelled receipt formats and English OCR. Confidence is not calibrated and does not measure authenticity. A bank-template evaluation corpus and additional language support remain future work.
- Duplicate bank/reference combinations are blocked and reused document fingerprints are flagged. There is no probabilistic fraud classifier or claim of fraud detection accuracy.
- One release workflow is permitted per deposit. Returned requests can be resubmitted; a rejected final request is terminal in the prototype. Appeals/reopening and post-authorisation amendment processes require a defined institutional procedure.
- Administrative user management creates accounts and enables/disables them. Existing role reassignment is deliberately not exposed; create a properly scoped replacement account and disable the old one. SSO/MFA, invitation delivery, recovery and periodic access reviews are not implemented.
- Optional validity and regulatory dates remain institution declarations subject to review, not independently established bank/regulatory facts.
- Search operates over authorised records and client-side pagination. Large deployments need database-level pagination, indexed search, aggregation queries and workload benchmarks.
- Audit hash chains and update/delete triggers provide an immutable-style history. A privileged database owner can still alter protections; externally anchored audit storage and privileged-access controls are future deployment work.
- Fictional demo sign-in shortcuts are part of this prototype UI; remove them from a real deployment. Seeding and registration are disabled in production configuration.

## Validation limits

Automated checks cover role boundaries, institution isolation, calculation, validation, extraction (including real Tesseract), simulated and manual evidence, private documents, deadlines, renewal preservation, release blocking and audit events. See `VERIFICATION.md` for actual run results. No official AICTE validation, external penetration test, accessibility certification, PostgreSQL runtime test or scalability benchmark is claimed.

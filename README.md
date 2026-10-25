# AICTE DepositFlow — SIH26265

DepositFlow is a working prototype for managing institutional security deposits and Fixed Deposit Receipts (FDRs): submission, document review, bank evidence, maturity monitoring, renewal, clearances and release authorisation.

The project includes a **React/TypeScript frontend**, a **FastAPI backend**, a relational database, encrypted document storage, OCR, role-based workflows and automated tests. **The recommended local setup uses SQLite and runs without Docker.** PostgreSQL, MinIO and Redis/Celery are included as an optional deployment configuration.

This is a Smart India Hackathon prototype, not an official AICTE service or a certified production deployment. Demo institutions and bank records are fictional; regulatory rules are illustrative. The portal records release decisions and completion references; it never transfers money.

## Current implementation

| Area | Included |
| --- | --- |
| Institutions | Institution/programme records, scoped access and development registration |
| Deposits | Drafts, requirement calculations, instrument details, submission and status tracking |
| Documents | PDF/PNG/JPEG validation, encrypted storage, authenticated previews and extraction |
| Evidence review | Separate institution declarations, extracted fields, human corrections and bank findings |
| Review tasks | Explainable mismatch, shortfall, coverage, lien, depositor, duplicate, reuse, document-integrity, receipt-arithmetic and maturity flags; tasks reopen on new evidence and high-severity resolutions need a second officer |
| Risk | Explainable 0–100 score with history (officials only), risk-ordered queue, dashboard view, and stricter release safeguards for high and critical cases |
| Verification | Labelled simulated bank adapter and officer-recorded manual bank evidence |
| Monitoring | Maturity, validity, regulatory and renewal deadlines; reminders and overdue escalations |
| Renewals | Linked replacements that preserve the previous instrument and its documents |
| Releases | Required documents, PGRC/Vigilance clearances, maker-checker checks and final decisions |
| Administration | Users, versioned rules, second-administrator rule approval, workflow and alert settings |
| Reporting | Dashboards, charts, searchable tables, CSV exports, printable reports and audit history |
| Reliability | Persistent extraction claims, bounded retries, recovery and rejection of stale worker results |

**VLM integration is deferred.** PDF text extraction and Tesseract OCR work now. Optional provider hooks exist, but no trained model is connected, downloaded or needed to run the project. The active database stack is SQLAlchemy with SQLite/PostgreSQL; MongoDB is not used.

## Run locally without Docker

### Prerequisites

- Python **3.12** and its virtual-environment support.
- Node.js **22**, npm and Git.
- Tesseract for scanned PDFs and images. Selectable-text PDFs can be processed without it.

The commands below target macOS/Linux. On Windows, WSL provides the same shell and paths.

### Install and start

```bash
git clone https://github.com/alokkumardalei-wq/SIH_FDR.git
cd SIH_FDR
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci
python3 scripts/dev.py
```

Open:

| Service | URL |
| --- | --- |
| Portal | http://localhost:5173 |
| Interactive backend API documentation | http://127.0.0.1:8000/docs |
| API health | http://127.0.0.1:8000/api/health |

The launcher applies Alembic migrations, seeds fictional demo data idempotently and starts the API and frontend. It preserves existing accounts and records. Press **Ctrl+C** in that terminal to stop both services.

Use `http://localhost:5173` consistently. The configured origin protects write requests; opening the frontend through `127.0.0.1` instead can cause origin errors. Backend automatic reload is disabled to reduce local overhead: restart the launcher after Python changes. Frontend changes use Vite hot reload.

No `.env` file is required for this default setup. Development keys are generated locally on first use and are excluded from Git.

Install Tesseract if needed:

```bash
# macOS
brew install tesseract

# Debian / Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-eng
```

### Run the two services separately

From the repository root, prepare and run the backend:

```bash
cd backend
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m app.seed
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal, from the repository root:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

Run backend commands inside `backend/`, so the database, private key file and storage paths resolve consistently. Use either the combined launcher or the separate commands, not both at once.

## Demo accounts and roles

The sign-in page provides shortcuts for fictional demo accounts. The public, local-demo password is **`DemoFlow2026!`**. This is a fixture password, not a private deployment credential. Set `DEMO_PASSWORD` before the first seed to choose another value; reseeding does not reset existing accounts. If changed, enter the selected password manually instead of relying on the demo shortcut.

| Account | Purpose |
| --- | --- |
| `institution@demo.local` | Meridian Institute: create deposits, upload documents, answer review queries and request release |
| `institution2@demo.local` | Sahyadri College: demonstrate institution-level isolation |
| `institution3@demo.local` | Northstar School: demonstrate an unavailable simulated bank response |
| `officer@demo.local` | Claim cases, scrutinise evidence, verify instruments and resolve review tasks |
| `officer2@demo.local` | Second verification officer who confirms or rejects high-severity resolutions |
| `clearance@demo.local` | Record PGRC clearance decisions |
| `vigilance@demo.local` | Record Vigilance clearance decisions |
| `authority@demo.local` | Decide release requests and record completion references |
| `admin@demo.local` | Manage accounts, configuration, rule proposals and monitoring |
| `admin2@demo.local` | Provide the separate administrator needed to approve a rule change |
| `auditor@demo.local` | Read permitted records, audit events and reports |

There are **six application roles**: institution, verification, clearance, authority, admin and auditor. PGRC and Vigilance are separately scoped cells within the clearance role. Backend checks enforce permissions independently of which buttons are visible.

The seed includes three institutions, nine deposit obligations and ten instruments, including a preserved predecessor. PDFs in `demo-data/` are explicitly fictional demonstration documents. Personal accounts, uploaded real documents and local database records are not included in the repository.

## Typical case journey

1. **Institution:** select a programme, review the configured requirement, create a draft and upload the FDR receipt.
2. **Extraction:** the backend reads the document and stores original text, fields and confidence. The institution can record a reasoned correction without replacing the original extraction.
3. **Verification officer:** claim the case, compare the independent evidence sources, request clarification and resolve review tasks with reasons.
4. **Bank evidence:** run a clearly labelled simulated check or record authorised manual bank confirmation with a supporting document.
5. **Monitoring/renewal:** track the distinct deadlines and link any replacement instrument to the original.
6. **Release:** the institution submits the configured supporting records, including a release request, affidavit and approval letter in the demo workflow. PGRC and Vigilance record their clearance decisions.
7. **Approving authority:** review all blockers and record approval, return or rejection. A prior reviewer cannot provide the final release decision. Once authorised, record the external completion/NOC reference.

A risk flag prompts human review. It does not declare fraud or automatically authorise release. Bank maturity alone does not establish release eligibility.

## Backend architecture

The backend is a **modular monolith**: one FastAPI application owns authentication, access control, transactions and workflow decisions. It uses SQLAlchemy's synchronous ORM with Alembic migrations. Background extraction runs outside the inference-time database transaction; the local scheduler or optional Celery worker processes retained work.

```mermaid
flowchart LR
    Browser[React frontend] -->|Same-origin /api requests| API[FastAPI application]
    API --> Access[Session, CSRF, role and institution checks]
    API --> Rules[Requirement and release rules]
    API --> DB[(SQLite locally / PostgreSQL optionally)]
    API --> Vault[Encrypted private documents]
    API --> Bank[Mock adapter / manual bank evidence]
    API --> Audit[Append-only audit events and chain heads]
    DB --> Jobs[Persistent extraction queue]
    Jobs --> Worker[Local worker / Celery]
    Worker --> OCR[PyMuPDF and Tesseract]
    OCR --> DB
    Worker --> Alerts[Deadline monitoring and notifications]
```

### Backend module map

All application modules are under `backend/app/`.

| Module | Responsibility |
| --- | --- |
| `main.py` | FastAPI setup, route registration, lifespan scheduler, security headers and exception responses |
| `config.py` | Environment settings, development key generation and production configuration checks |
| `db.py`, `models.py`, `schemas.py` | Database sessions, normalised relational models and request validation |
| `auth_routes.py`, `security.py` | Login/logout, password hashing, revocable sessions, CSRF and scoped record access |
| `deposit_routes.py` | Institutions, calculations, drafts, submission, uploads, corrections and replacements |
| `rules.py` | Effective-dated requirement rules, exemptions, multipliers and calculation snapshots |
| `storage.py` | Upload validation, optional ClamAV scanning, Fernet encryption and local/S3 storage |
| `extraction.py` | PDF text extraction, Tesseract fallback and heuristic structured-field parsing |
| `extraction_engine.py` | OCR provider interface and inactive hooks for a future trained VLM |
| `jobs.py`, `worker.py` | Persistent claims, retries, recovery, local scheduling and optional Celery tasks |
| `bank.py` | Bank adapter protocol and deterministic fictional verification fixtures |
| `workflows.py` | Discrepancy detection, release prerequisites, reviewer separation and deadline reminders |
| `matching.py`, `forensics.py`, `consistency.py` | Normalised names, banks and references; document integrity indicators (metadata, incremental saves, conflicting values, text layer against OCR); receipt arithmetic |
| `risk.py` | Explainable risk score from review tasks and score-only observations; append-only score history and approved weight versions |
| `../evaluation/` | Synthetic labelled corpus, end-to-end harness and report for measuring the risk engine (`python -m evaluation`) |
| `review_routes.py` | Assignment, scrutiny, bank evidence, clearances and release decisions |
| `admin_routes.py` | Dashboard/report queries, user/rule administration, settings and monitoring |
| `presenters.py` | API response assembly, evidence details and exclusion of private internal fields |
| `audit.py` | Actor-attributed hash-chained events and transactionally updated chain heads |
| `seed.py` | Idempotent fictional institutions, accounts, instruments and documents |

`backend/migrations/` contains the initial schema, append-only audit triggers, extraction provenance and worker-claim/audit-head additions. Migrations run explicitly before the application; startup does not recreate the database schema.

### Data and evidence boundaries

- `security_deposits` stores the obligation, programme and requirement snapshot; `deposit_instruments` stores declared FDR details and replacement history.
- `documents` references private encrypted bytes and tracks upload/extraction state.
- `document_extractions` preserves original extracted evidence, provider and document checksum; `field_corrections` stores later human corrections separately.
- `verification_requests` and `verification_evidence` retain bank findings with an explicit simulation distinction.
- `release_requests` snapshot the required workflow; `release_clearances` records cell-specific decisions.
- `audit_logs` and `audit_chain_heads` retain and verify ordered event histories.

Money is stored using fixed-precision numeric columns. Foreign keys, unique references, checks and migrations are part of the relational model. See the [database diagram](docs/DATABASE.md) and [generated PostgreSQL schema](docs/schema.postgresql.sql).

### Authentication, documents and approvals

Authentication uses an **opaque, HttpOnly session cookie**, not a frontend-stored bearer JWT. Passwords use Argon2; only hashes of session tokens are stored. Mutations require CSRF protection, and institution access is scoped server-side. JWTs are used for short-lived, user-bound document access grants.

Uploaded documents are encrypted with Fernet before being written to local storage or S3/MinIO. Supported inputs are PDF, PNG and JPEG, up to 10 MB and 15 PDF pages, with content/format checks. ClamAV is optional locally and required by production settings. The private-document download path rechecks authentication and access.

Release approval rechecks required documents, permitted bank verification, the configured regulatory period, unresolved tasks, in-progress receipt extraction and required clearances. Prior reviewer identities remain disqualified after reassignment or a later role change. Rule changes also require a second administrator.

Audit update/delete triggers and hash chains provide tamper evidence. A privileged database owner can still defeat these protections; externally anchored audit storage is not implemented.

### Background work

Document states are `queued`, `processing`, `completed` and `failed`. Claims and attempt counts persist in the database. Local inference is limited to one extraction per process. Transient failures use bounded retries; expired claims can recover, and a late worker cannot overwrite a newer claim. The local scheduler checks retained work every five seconds. The optional Celery Beat configuration runs recovery/monitoring every five minutes.

Reminder stages default to 90, 60, 30, 7 and 0 days, plus overdue escalation. Notifications are deduplicated. In-app notifications and a development email-outbox representation are included; real email/SMS delivery is not connected.

### API surface

Endpoints use the **`/api`** prefix. Examples include `/api/auth/login`, `/api/deposits`, `/api/releases`, `/api/dashboard`, `/api/audit` and `/api/admin/monitor`. Follow the actual API contract in [docs/API.md](docs/API.md), [docs/openapi.json](docs/openapi.json), or the running `/docs` page. The repository does not implement the earlier proposed `/api/v1/fdr/*` contract.

## Frontend architecture

The frontend is a **React 19 + TypeScript single-page application**, built with Vite. React Router handles navigation; TanStack Query loads and refreshes server state. React Hook Form and Zod handle form state and validation. Recharts renders analytics. Tailwind CSS, shared CSS, Lucide icons and Radix-based UI primitives provide presentation and interactions.

```mermaid
flowchart TD
    Entry[main.tsx: QueryClient and BrowserRouter] --> App[App.tsx: routes, session and workspace shell]
    App --> Public[Public pages and sign-in]
    App --> Workspace[Role-aware workspace pages]
    Workspace --> Components[Forms, tables, dialogs and evidence components]
    Workspace --> Query[TanStack Query and mutations]
    Query --> Client[lib/api.ts: fetch, cookies, CSRF and errors]
    Client --> Proxy[Vite dev proxy / Nginx deployment proxy]
    Proxy --> Backend[FastAPI /api]
```

### Frontend module map

| Path under `frontend/` | Responsibility |
| --- | --- |
| `src/main.tsx` | React entry point, router and query-client providers |
| `src/App.tsx` | Route tree, current-user context, authenticated shell, role-aware navigation and mobile sidebar |
| `src/pages/public.tsx` | Landing page, workflow guide, sign-in and development registration |
| `src/pages/overview.tsx` | Dashboard, registry/queues, institutions, requirement calculator, notifications, settings, reports and audit view |
| `src/pages/case.tsx` | New deposit form and detailed case workspace, including uploads and workflow actions |
| `src/pages/admin.tsx` | Release queue/decisions and administrative screens |
| `src/components/evidence-comparison.tsx` | Submitted, extracted/corrected and bank values side by side; provenance and simulation labels |
| `src/components/case-progress.tsx` | Case stages, outstanding review status and role-specific next-action guidance |
| `src/components/common.tsx` | Shared panels, tables, badges, notices, action dialogs and private document previews |
| `src/components/ui/` | Shared button/dialog primitives |
| `src/lib/api.ts` | Same-origin requests, cookie credentials, CSRF headers, API errors and CSV downloads |
| `src/lib/utils.ts`, `src/styles.css` | Labels/formatting, visual layout and responsive styles |
| `vite.config.ts` | React/Tailwind plugins, API proxy, build chunks and Vitest setup |
| `nginx.conf` | Built-SPA serving, API reverse proxy, upload limit and browser security headers |

### Screens available

Public routes are `/`, `/information`, `/signin` and `/register`. The authenticated workspace starts at `/app` and includes:

- Dashboard with live database-derived indicators and charts.
- Deposit registry, new-deposit form and detailed case tabs.
- Verification and maturity queues.
- Evidence comparison, original extraction/correction history and private document preview.
- Review tasks, bank verification and release workflow actions.
- Release requests, institutions and requirement calculation.
- Notifications, account settings, reports and audit history.
- Administration for users, rules, workflow, alerts and system monitoring.

The interface shows actions according to role and case state, while the backend remains authoritative. Receipt screens poll while extraction is queued or processing. Human-corrected values retain the original evidence and do not inherit the parser's confidence score. Matching fields are never presented as proof of authenticity.

In development, Vite proxies `/api` to `127.0.0.1:8000`. The optional container build serves the compiled SPA through Nginx and proxies `/api` to the backend service. The browser does not need database credentials or a secret-bearing frontend environment file.

## Configuration and secret handling

**All `.env` files, including `.env.*` examples, are excluded from this repository.** Configuration is documented here instead. Do not put API keys or database passwords in frontend code.

For optional native overrides, create your own untracked `backend/.env`. Shell environment variables also work. These are the main settings:

| Setting | Local default / purpose |
| --- | --- |
| `ENVIRONMENT` | `development`; production enables stricter startup checks |
| `DATABASE_URL` | `sqlite:///./.data/depositflow.db`; can select PostgreSQL |
| `STORAGE_BACKEND`, `STORAGE_PATH` | `local`, `.data/documents` |
| `JOB_MODE` | `local`; optional `celery` deployment |
| `FRONTEND_ORIGIN` | `http://localhost:5173` |
| `COOKIE_SECURE` | `false` for loopback HTTP; required in production |
| `REQUIRE_MALWARE_SCAN`, `CLAMAV_HOST` | Optional locally; configure the scanner for production |
| `EXTRACTION_PROVIDER` | `ocr`; leave unchanged until VLM integration is requested |
| `EXTRACTION_MAX_ATTEMPTS`, `EXTRACTION_LEASE_SECONDS` | `3`, `900` |
| `SECRET_KEY`, `STORAGE_ENCRYPTION_KEY` | Generated locally in development; explicit private values required in production |
| `DEMO_PASSWORD` | Optional password override before initial seeding |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Optional private S3/MinIO configuration |
| `REDIS_URL` | Broker connection for optional Celery mode |

Development runtime files live under `backend/.data/`: the SQLite database, encrypted documents and `local-secrets.json`. They are ignored by Git, along with backups, private keys, credentials, dependency folders, builds and test artifacts. Preserve the database, encrypted objects **and their encryption key together** in a private backup; the key is required to read existing documents.

## Optional Docker deployment

Docker is not required for the default setup. The Compose stack adds PostgreSQL, MinIO, Redis, Celery, Beat and Nginx and uses more resources. Stop the native launcher first to free ports 8000 and 5173.

```bash
python3 scripts/configure.py
docker compose up --build -d
docker compose exec api python -m app.seed
```

`configure.py` creates an ignored root `.env` with fresh deployment secrets and refuses to overwrite an existing file. The Compose migration service finishes before the API starts. Open the portal at http://localhost:5173 and MinIO's local console at http://localhost:9001. MinIO credentials remain in your generated private `.env`.

To enable the optional antivirus service, set `CLAMAV_HOST=clamav` and `REQUIRE_MALWARE_SCAN=true` in that local file, then run:

```bash
docker compose --profile malware-scan up --build -d
```

Use `docker compose down` to stop services while retaining their named volumes. Avoid `down -v` if you need to retain stored data. The optional stack is included but has not been validated end to end on this development machine.

For native PostgreSQL without Docker, set a private `DATABASE_URL` using the `postgresql+psycopg://` driver in `backend/.env`, then use the normal migration and startup commands. This selects a database; it does not automatically copy existing SQLite records.

## Tests and build

From the repository root:

```bash
cd backend
../.venv/bin/python -m pytest -q
../.venv/bin/python -m alembic check
cd ../frontend
npm test
npm run build
```

`alembic check` requires an accessible database already migrated to the current revision. The backend tests use temporary databases and storage directories; they do not reset your presentation data.

For browser tests, first start the local portal, then run in another terminal:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

An existing compatible Chromium executable can be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. Browser tests use one worker, create fictional `E2E-*` records and retain ignored screenshots/traces under `frontend/test-results/`.

Latest verified results: **113 backend tests (including the risk-evaluation regression gate and an offline PostgreSQL migration check) and 6 frontend tests passed; the TypeScript/production build and migration alignment check passed.** The 4 Playwright browser tests last passed before the risk-engine work and have not been re-run since. See [docs/VERIFICATION.md](docs/VERIFICATION.md) for the tested scope and limitations. These are recorded local results, not a claim of a configured GitHub Actions pipeline.

## Troubleshooting and maintenance

| Symptom | Check |
| --- | --- |
| Browser says connection refused | Keep `python3 scripts/dev.py` running; inspect its terminal output and use port 5173 |
| Launcher reports a port is occupied | Stop the previous instance or the service using 8000/5173, then restart |
| Sign-in or mutations report an untrusted origin | Use `http://localhost:5173` or deliberately update `FRONTEND_ORIGIN` |
| Scanned document extraction fails | Install Tesseract, check it is on `PATH`, then retry the failed extraction |
| API reports missing tables/columns | Stop the backend and run `alembic upgrade head` from `backend/` |
| Python changes are not visible | Restart the backend; frontend hot reload does not reload Python |
| Docker makes the machine slow | Use the default native SQLite/local-storage mode |
| Encrypted documents cannot be read after moving data | Restore the matching encryption key together with the database and documents |

For a clean **local demo only**, stop the application first:

```bash
python3 scripts/reset_demo.py --confirm-reset
python3 scripts/dev.py
```

The reset script archives `backend/.data` before creating new demo state. Do not reset to apply an upgrade, and do not use this script against an external PostgreSQL database. For upgrades, retain a private backup and apply migrations.

## Repository layout and further documentation

```text
SIH_FDR/
├── backend/
│   ├── app/                 # API, models, security and domain services
│   ├── migrations/          # Alembic migration history
│   ├── tests/               # Backend and workflow regression tests
│   ├── requirements.lock    # Pinned Python dependencies
│   └── Dockerfile           # Optional API/worker container
├── frontend/
│   ├── src/pages/           # Public, case, overview and administration pages
│   ├── src/components/      # Shared UI and evidence/progress components
│   ├── src/lib/             # API client and formatting helpers
│   ├── e2e/                 # Playwright browser scenarios
│   ├── package-lock.json    # Locked frontend dependencies
│   └── nginx.conf           # Optional built-SPA/API reverse proxy
├── demo-data/               # Fictional PDF fixtures only
├── docs/                    # Architecture, database, API, demo and verification notes
├── scripts/                 # Native launcher, private Compose setup and demo reset
└── compose.yaml             # Optional PostgreSQL/MinIO/Redis/Celery stack
```

- [Architecture and security boundaries](docs/ARCHITECTURE.md)
- [Backend progress and deferred VLM work](docs/BACKEND_PROGRESS.md)
- [Database relationships](docs/DATABASE.md) and [PostgreSQL schema](docs/schema.postgresql.sql)
- [API guide](docs/API.md) and [OpenAPI snapshot](docs/openapi.json)
- [Six-journey demo walkthrough](docs/DEMO.md)
- [Verification results](docs/VERIFICATION.md)
- [Known limitations and remaining integrations](docs/LIMITATIONS.md)
- [Risk engine evaluation](docs/RISK_EVALUATION.md)

Live bank/AICTE connectivity, trained VLM integration, real email/SMS delivery, SSO/MFA, production deployment hardening and formal regulatory review remain future work. Existing automated checks assist officers; human decisions and independently obtained evidence remain essential.

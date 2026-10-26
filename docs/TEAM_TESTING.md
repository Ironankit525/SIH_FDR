# Team testing with the shared Colab VLM

Each teammate runs the frontend and backend on their own laptop and connects their backend to the same running Gemma 3 27B worker. No local GPU, model download, retraining, MongoDB or Docker is needed for this setup.

```text
Teammate A's browser -> A's backend/database --\
                                             -> shared ngrok HTTPS API -> Colab GPU/model
Teammate B's browser -> B's backend/database --/
```

Each laptop has independent users, deposits, documents and audit records. Changing roles on one laptop tests that laptop's cases. Teammates do not see each other's cases merely because they share the VLM. To have several people act on the same case, use one shared portal/backend deployment instead; localhost on another person's laptop is a different application instance.

## 1. Model owner: make the worker available

1. Keep the existing Colab runtime and API/ngrok serving process running. The model is already trained; teammates need its inference service, not a new training run.
2. Download the current `backend-vlm.env` from the serving cell and share that file privately with the team. They need the worker endpoint, worker API key, model name/version and timeout from this file. They do not need your ngrok account token or Drive credentials.
3. After recreating the worker, distribute the newly downloaded file again. The hostname can stay the same while the API token changes; an old token returns HTTP 401.
4. Coordinate uploads one at a time for the initial test. The worker runs one inference at a time; concurrent requests can receive 429/busy and consume the backend's bounded retries. Our local live checks took about 51 seconds per receipt, not a guaranteed latency.

If the owner is unavailable, another teammate can run their own Colab copy of [the notebook](../training/gemma3_27b/Gemma3_27B_Review_and_Serve.ipynb). They need access to the saved adapter and processor files, the correct Drive path, a suitable GPU runtime, and their own ngrok account/domain configuration. See [the model guide](../training/gemma3_27b/README.md). Sharing an `.ipynb` alone does not grant access to the model files.

## 2. Publish the code needed by a fresh checkout

Push the branch containing the current backend, frontend, `training/gemma3_27b/`, both new setup scripts, and this guide. The examples below use `llm_integerate`; substitute the branch where these changes were actually published. An older remote branch will not contain the new commands until you push them.

The setup generates the test PDFs and mock-bank records. Include `demo-data/receipt-tests/README.md` as well so teammates can see the form values. Do not rely on `.data/vlm-review/` helpers or your existing local database: those are local runtime artifacts, not a reproducible team setup.

Keep the active `backend/.env`, downloaded worker configuration, databases, uploaded private documents and local signing/encryption keys out of the new checkout. Share only the current worker configuration through the team's private channel. Each fresh installation generates its own local storage/session keys. If a secret file is already tracked, `.gitignore` alone does not untrack it; review the staged file list before pushing. Never delete a local encryption key that is still needed to read existing local documents.

## 3. Teammate: install and connect

Use Python 3.12 and Node.js 22. These commands target macOS/Linux; Windows teammates can use WSL. Run them in the same WSL environment, including the downloaded configuration path.

```bash
git clone --branch llm_integerate https://github.com/alokkumardalei-wq/SIH_FDR.git
cd SIH_FDR
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci
```

The repository owner must grant access if the repository is private. If Python 3.12 is installed as `python3`, use that executable for the virtual environment.

Save the current worker configuration received from the owner, then import it:

```bash
.venv/bin/python scripts/connect_vlm.py "$HOME/Downloads/backend-vlm.env"
```

Use the actual filename, for example `backend-vlm (2).env`, when the browser added a suffix. The helper checks the authenticated health endpoint and model identity before writing `backend/.env`. It imports only the six worker settings, preserves other configuration, and does not print the key. Failure leaves the existing file unchanged. The backend reads this file at startup; importing new settings requires a restart.

Prepare the local database and test receipts, then start the portal:

```bash
.venv/bin/python scripts/prepare_team_demo.py
python3 scripts/dev.py
```

Open **http://localhost:5173**. Use this hostname consistently for the configured request-origin checks. Backend health is http://127.0.0.1:8000/api/health. Keep the launcher terminal running. Do not start a second launcher if ports 8000/5173 are already in use.

The preparation script applies migrations, seeds the existing demo cases, creates the two PDFs, and installs two separate mock-bank records. Rerunning preserves existing cases and matching fixtures; it refuses to overwrite conflicting fixture data. It supports the default local SQLite development configuration. It does not automatically submit or approve the two test deposits.

Tesseract is only needed locally for scanned supporting documents/OCR tests. Instrument uploads use Colab in this setup. On macOS it can be installed with `brew install tesseract`; on Ubuntu/WSL use `sudo apt-get install tesseract-ocr tesseract-ocr-eng`.

## 4. Sign in and create the two cases

Default demo password: **`DemoFlow2026!`**. Sign-in shortcuts fill these demo credentials.

| Account | Test role |
| --- | --- |
| institution@demo.local | Create deposits, upload, respond, request release |
| officer@demo.local | Assign cases, review and verify |
| clearance@demo.local | PGRC clearance |
| vigilance@demo.local | Vigilance clearance |
| authority@demo.local | Final release decision and completion |
| admin@demo.local | Monitoring/configuration |
| admin2@demo.local | Separate administrator for rule approval |
| auditor@demo.local | Read audit history and reports |
| institution2@demo.local | Institution isolation test |

As Institution, select New deposit and Engineering and Technology, then use these exact values:

| Field | Correct case | Altered case |
| --- | --- | --- |
| FDR number | TEST-VALID-001 | TEST-ALTERED-001 |
| Amount entered | 3500000 | 5000000 |
| Bank | EXAMPLE LEARNING BANK | EXAMPLE LEARNING BANK |
| Branch | DEMO BRANCH | DEMO BRANCH |
| Depositor | Meridian Institute of Technology | Meridian Institute of Technology |
| Issue date | 2026-01-15 | 2026-01-15 |
| Maturity date | 2034-01-15 | 2034-01-15 |
| PDF in demo-data/receipt-tests | CORRECT-TEST-VALID-001.pdf | INCORRECT-TEST-ALTERED-001.pdf |

Leave optional regulatory-end and renewal-action dates blank for this extraction/bank-comparison test. These cases are not the prepared successful-release case. The separate regulatory security period is not derived from the bank maturity date.

1. Create two separate drafts. Do not put both PDFs in one case for this initial test.
2. In Documents, select **Instrument** before choosing each PDF. Supporting uploads use the existing supporting-document processor and do not call the VLM.
3. Upload once and wait for **Completed**. If it fails, fix the connection and use **Retry extraction** on that upload; uploading duplicates produces confusing additional records.
4. Open Evidence comparison. Confirm `Model extraction`, the Gemma 3 27B identity, and the values. The model can make mistakes; compare all six fields and record any human corrections with reasons.
5. Submit each case for review.
6. Sign out; sign in as Officer. Open each case, select **Assign to me**, then **Bank verification -> Run mock verification**.

Expected results:

| Test | What should happen |
| --- | --- |
| Correct form + correct PDF | Both show INR 3500000; mock bank also has INR 3500000, so mock confirmation |
| Altered form + altered PDF | Both show INR 5000000; mock bank has INR 3500000, so bank amount mismatch and an open review task |
| Additional form/receipt mismatch test | After the correct-case test, as its assigned officer request clarification. As Institution edit only the submitted amount to 5000000. Its receipt still extracts to 3500000, so an amount mismatch appears without another bank check. The edit resets bank verification. |

The VLM reads the document; matching form/document values alone do not establish bank authenticity. Review warnings for stamp, lien or holding claims currently appear in Evidence comparison and are not automatically converted into blocking review tasks. Open discrepancy tasks do block release. A successful test does not prove unseen-document accuracy or regulatory compliance.

## 5. Continue the full workflow

- **Clarification:** Officer requests clarification; Institution responds; Officer records an evidence-based resolution. The institution cannot resolve an officer's task itself.
- **Blocked release:** On a submitted test case create a release request. Missing documents, bank verification, regulatory-period completion, open review tasks and pending clearances must block authority approval. Do not approve fictional missing evidence merely to make this test pass.
- **Successful release:** Use seeded `RELEASE-006`. Initially PGRC is approved and Vigilance is pending. Authority approval must fail. As Vigilance record approval; as Authority approve, then separately record a fictional completion reference. Expect Release Authorised, then Released. No funds move.
- **Return/rejection:** Use separate release requests to test authority return -> institution resubmission and final rejection.
- **Maturity:** Inspect `MATURITY-004` and run the admin deadline monitor twice; the same reminder stage should not duplicate notifications.
- **Renewal:** Inspect `RENEWED-005` for retained predecessor evidence. Perform a new replacement on a submitted case without a release request; upload the new receipt and resubmit. Old bank verification must not carry over.
- **Access:** Institution 2 must not open Institution 1's case/documents. The auditor can inspect/export but cannot approve. The administrator proposing a rule cannot approve their own change.
- **Audit:** Check the actor-attributed case timeline and Admin -> System monitoring -> chain intact.

See [the longer walkthrough](DEMO.md). Seeded documents already have extraction results; they are workflow fixtures, not proof that a new Colab request succeeded.

## 6. Connection recovery and test commands

| Symptom | Action |
| --- | --- |
| 401/authentication failure | Obtain the latest worker env file, rerun connect_vlm.py, restart the local launcher |
| Offline tunnel / ERR_NGROK_3200 | Owner restarts the serving process; teammates recheck/import current settings and restart |
| Busy/retrying | Coordinate one upload at a time; retry failed jobs after the shared worker is free |
| Supporting says Completed but no model fields | Select Instrument and upload the actual receipt in that category |
| Bank verification Pending | Submit, sign in as Officer, assign the case and run verification |
| Unknown mock-bank reference | Run prepare_team_demo.py and use the exact prepared bank/reference; invented references have no fixture |
| Same-number duplicate error | Open the existing case rather than recreating the same bank/FDR number |

After changing credentials, stop the local launcher with Ctrl+C and restart `python3 scripts/dev.py`. Refresh the browser and retry the failed instrument upload. Reconnecting the Colab browser alone does not restore a stopped model/API/tunnel.

From the repository root:

```bash
.venv/bin/python -m pytest scripts/tests -q
.venv/bin/python -m pytest training/gemma3_27b/test_worker.py -q
cd backend
../.venv/bin/python -m pytest -q
../.venv/bin/python -m alembic check
cd ../frontend
npm test
npm run build
```

These software tests use temporary/stubbed services and do not measure live VLM accuracy. Complete the new receipt upload tests above separately. The existing Playwright upload test waits only 20 seconds; it needs a longer test/assertion timeout before running against the slower Colab worker. Do not reset the active demo to run unit tests; they already use temporary databases.

# Verification record

Checks completed on 26 October 2026 after integrating main's two-portal UI and cascade extraction changes (PR #5, commit `1fa537d`). The subsequently fetched main commit `8c793db` has an identical source tree. Tests ran locally without Docker.

| Check | Result |
|---|---|
| Backend (`cd backend && ../.venv/bin/python -m pytest -q`) | **162 passed**; includes extraction cascade, verification safeguards, workflows, security and migrations |
| VLM worker and setup (`.venv/bin/python -m pytest training/gemma3_27b/test_worker.py training/gemma3_27b/test_colab_setup.py scripts/tests -q`) | **31 passed** |
| Frontend (`cd frontend && npm test`) | **22 passed** across six test files |
| TypeScript / production build (`npm run build`) | **Passed**; Vite reports a nonfatal main-chunk size warning (about 506 kB before gzip) |
| SQLite (`alembic upgrade head`, `alembic check`) | **Passed** through `verification_gate`; no new upgrade operations detected |
| Browser workflows (`npm run test:e2e`) | **6 passed**, using installed Google Chrome; includes desktop/mobile rendering, uploads, mismatches, authenticated previews, blocked clearances, admin configuration, official reassignment/audit, and the complete submission → verification → clearances → authority approval → release completion lifecycle |
| Notebook generation | **Passed**; generated notebook/setup artifacts unchanged by regeneration; notebook code cells compile and contain no saved execution outputs |
| Existing live Colab worker | Authenticated health/model identity passed; correct receipt extracted in **51.0 seconds**, altered receipt in **51.4 seconds** |

Browser tests ran in an isolated source copy with a fresh database, private keys and document storage. They used the default cascade extraction provider. The full suite changes demo accounts repeatedly; the test helper now honors the API's `429 Retry-After` delay instead of weakening the real login limiter. The original presentation database was not used for browser tests.

Separate direct-VLM requests used the existing private local configuration and fictional test PDFs. The correct receipt returned ₹35,00,000, reference `TEST-VALID-001`, issue date 2026-01-15 and maturity date 2034-01-15. The altered receipt returned ₹50,00,000 and reference `TEST-ALTERED-001`; a read-only comparison against the independent **mock** bank fixture (₹35,00,000) detected the amount mismatch. Neither request created or changed case records. This demonstrates extraction and mismatch handling for these examples, not fraud detection accuracy or real bank verification.

The local environment retains its explicit `EXTRACTION_PROVIDER=vlm_http` setting. The new default `cascade` setting tries PDF text, then Tesseract, then the VLM when earlier extraction is insufficient. These are distinct tested paths.

## Limits

- The existing Colab model was already loaded. A fresh GPU runtime, adapter reload and full notebook run were not repeated during this check.
- Unseen real-receipt accuracy remains unvalidated.
- Docker/PostgreSQL/MinIO/Celery deployment integration was not run. Offline PostgreSQL migration coverage is not a live PostgreSQL deployment test.
- The installed Starlette test transport emits a deprecation warning; the executed backend tests pass.
- Compose configuration passed in earlier checks, but was not rerun in this pass.

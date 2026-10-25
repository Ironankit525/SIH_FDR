# Verification record

The implementation is tested locally without Docker. The PostgreSQL deployment remains optional and was not started because of reported system memory pressure.

| Check | Result |
|---|---|
| FastAPI / domain tests (`python -m pytest -q`) | **113 passed**; adds the risk checks, risk score and release safeguards, institution redaction, the synthetic-corpus regression gate and an offline PostgreSQL migration check to the earlier review-history, clearance, extraction, audit and OCR coverage |
| Frontend integration tests (`npm test`) | **6 passed**; includes correction provenance, zero confidence, stale receipt prevention and rejection of simulated findings in progress displays when disallowed |
| TypeScript / production build (`npm run build`) | **Passed**; dependency chunks split and no bundle-size warning in the final build |
| SQLite migrations (`alembic upgrade head`) | Applied through `extraction_provenance`; existing database backed up, record counts preserved and audit heads verified against all 86 pre-upgrade events |
| Schema/model alignment (`alembic check`) | Passed: no new upgrade operations detected |
| Browser integration suite (`npm run test:e2e`) | **4 passed**; desktop/mobile rendering, sign-in, draft creation, upload, extraction, submission, officer assignment, simulated verification, private preview, blocked release and admin alert configuration. **Not re-run after the risk-engine work**; the new screens were checked in headless Chrome against a separate scratch database instead |
| Native launcher (`python3 scripts/dev.py`) | **Passed**; applied migrations, seeded idempotently, served frontend and backend without Docker |
| Compose syntax | **Passed** previously using local example configuration; no Docker services started. Environment files are intentionally unpublished. To validate a fresh clone, run `python3 scripts/configure.py`, then `docker compose config --quiet`. |
| PostgreSQL offline migration SQL (`alembic upgrade head --sql`) | **Passed** with a placeholder URL (offline mode never connects, so no server or credentials are needed); now covered by an automated test. `docs/schema.postgresql.sql` regenerated through the `risk_engine` revision; not a live PostgreSQL runtime test |
| Optional Docker stack | **Not run**; PostgreSQL, MinIO and Celery deployment integration remains unverified in this environment |

Backend tests use temporary databases, not the presentation demo. Browser tests create `E2E-*` fictional records and retain screenshots/traces under the ignored `frontend/test-results/` directory.

One dependency emits a Starlette deprecation warning about its future test HTTP transport. The executed FastAPI tests pass using the installed `httpx`/TestClient combination. No assertion about future compatibility is made.

Final checks were completed on 25 October 2026. Browser screenshots were inspected at desktop and 390-pixel mobile widths. The table scrolls inside its container on mobile without overflowing the page. Chart animation is disabled to reduce work and make screenshots deterministic.

# API guide

Interactive documentation is served at `http://127.0.0.1:8000/docs`, with OpenAPI at `/openapi.json`. A committed snapshot is in `docs/openapi.json`.

Sign in with JSON `POST /api/auth/login` containing `email` and `password`. The response sets an HttpOnly session cookie and a readable CSRF cookie. Subsequent mutation requests must include the CSRF cookie value in `X-CSRF-Token` and send the session cookie. Browser requests must originate from `FRONTEND_ORIGIN`.

All financial-record routes require authentication. Institution scope is enforced server-side. Read-only roles cannot mutate records. Session tokens, password hashes and private object keys are never returned in ordinary record responses.

| Area | Endpoints |
|---|---|
| Authentication | `POST /api/auth/login`, `/logout`, `/register`, `/password`; `GET /api/auth/me` |
| Institutions | `GET /api/institutions`, `PUT /api/institutions/{id}`, `GET /api/institutions/{id}/profile` (officials only: case history) |
| Requirement calculation | `POST /api/requirements/calculate`, `GET /api/rules` |
| Deposits | `GET/POST /api/deposits` (officials may add `sort=risk`, `risk_level=none|low|medium|high|critical` and `escalated=true` for the Vigilance queue), `GET /api/deposits/{id}`, `PATCH /api/deposits/{id}/instrument`, `POST /api/deposits/{id}/submit` |
| Upload/extraction | `POST /api/deposits/{id}/documents` (multipart), `POST /api/documents/{id}/retry`, `POST /api/extractions/{id}/corrections` |
| Private viewing | `GET /api/documents/{id}/access`, then the returned authenticated two-minute URL |
| Officer review | `POST /api/deposits/{id}/assign`, `/observations`, `/clarification`, `/assignment` (admins reassign; an assigned officer may hand back), `/verification-complete` (the assigned officer's sign-off; `409` with `blockers` until the bank has confirmed, the receipt is checked, every review task is resolved and no escalation remains) |
| Discrepancies | `POST /api/discrepancies/{id}/respond`, `/resolve`, `/review` (a second verification officer confirms or rejects a proposed high-severity resolution). On an escalated case, suspicious tasks can be resolved only by the Vigilance cell |
| Risk | `GET /api/deposits/{id}/risk` (officials only): suspicion score (level `none` when nothing suspicious is found; missing confirmations and paperwork are requirements, not scored), explained signals and score history; `POST /api/deposits/{id}/vigilance-clearance` (Vigilance only, once every suspicious task is resolved) closes an escalation. A score of 50 or more escalates the case to Vigilance and undoes any completed verification; `GET /api/risk/evaluation` and `/risk/evaluation/details`: results of the latest synthetic-corpus evaluation |
| Verification | `POST /api/deposits/{id}/verification/mock`, `/verification/manual`; `POST /api/verifications/{id}/evidence` |
| Renewal | `POST /api/deposits/{id}/replace` |
| Release | `POST /api/deposits/{id}/release`, `GET /api/releases`, `POST /api/clearances/{id}/decision`, `POST /api/releases/{id}/decision`, `/resubmit`, `/complete` |
| Insights | `GET /api/dashboard`, `/notifications`, `/audit` (filters `action`, `actor`, `entity`, `date_from`, `date_to`; paged by `limit`/`offset`), `/reports/export?kind=` `deposits`, `audit`, `pending_verification`, `upcoming_maturity`, `missing_documents` or `intervention` (officials) |
| Read tracking | `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all` |
| Import | `POST /api/admin/import` (CSV; checks by default, `commit=true` imports rows without problems) |
| Administration | `GET/POST /api/admin/users`, `POST /api/admin/users/{id}/toggle`, `POST /api/admin/rules`, `POST /api/admin/rules/{id}/approve` |
| Configuration | `GET /api/admin/config`, `PUT /api/admin/config/workflow`, `/alerts` |
| Risk policy | `GET /api/admin/risk-weights` (admin, auditor), `POST /api/admin/risk-weights/preview` (admin, auditor; level changes a policy would cause, nothing stored), `POST /api/admin/risk-weights`, `POST /api/admin/risk-weights/{id}/approve` (a different administrator; approval rescores every case) |
| Monitoring | `GET /api/admin/monitor`, `POST /api/admin/monitor/run`, `GET /api/health` |

Deposit filters include `q`, `status`, `bank`, `programme`, `assigned=me`, `min_amount`, `max_amount`, `date_from` and `date_to` (maturity dates). The list is scoped to the caller and the UI paginates it; production-scale server pagination remains future work. CSV exports explicitly cover all authorised records rather than the current visual filter.

Common response codes: `401` unauthenticated, `403` unauthorised role/CSRF/origin, `404` inaccessible or missing record, `409` workflow/uniqueness conflict, `422` validation failure, `429` rate limit, `503` required scanner or rate-limiter unavailable. Release `409` responses include a `detail.blockers` list explaining missing prerequisites.

The mock adapter always returns `simulated: true` and `source: SIMULATED / MOCK BANK DATA`. Production disables the mock endpoint. Manual evidence requires a valid manual request, a bank-confirmation document from the same case, source/reference, verification date, finding and observations.

### Cascade extraction evidence

New extraction results include `evidence` with `status` (`complete`, `incomplete`, or `conflict`), `reasons`, `stages`, `sources`, and `conflicts`. Each source preserves its provider, parsed fields, candidate values, confidences and original text. The existing `fields` object remains the selected provider's result; it is not silently merged with or overwritten by another source. Disagreements create separate `extraction_conflict_<field>` review tasks even when the institution's declaration agrees with the selected result.

`documents.processing_status=completed` means the job finished. The UI uses extraction quality to show **Incomplete extraction** or **Conflicting extraction** and keeps the extraction milestone pending. `evidence.status=complete` only means the selected result meets the configured completeness checks and no cross-source conflict was found; it is not an authenticity verdict. Historical extractions have empty evidence because old OCR/VLM values cannot be reconstructed reliably.

Apply the `cascade_evidence` migration before starting the updated backend (`python -m alembic upgrade head` from `backend/`; the lightweight dev launcher does this automatically). No Colab worker change is required. Supporting documents retain their existing processing flow.

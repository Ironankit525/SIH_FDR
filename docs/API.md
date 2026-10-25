# API guide

Interactive documentation is served at `http://127.0.0.1:8000/docs`, with OpenAPI at `/openapi.json`. A committed snapshot is in `docs/openapi.json`.

Sign in with JSON `POST /api/auth/login` containing `email` and `password`. The response sets an HttpOnly session cookie and a readable CSRF cookie. Subsequent mutation requests must include the CSRF cookie value in `X-CSRF-Token` and send the session cookie. Browser requests must originate from `FRONTEND_ORIGIN`.

All financial-record routes require authentication. Institution scope is enforced server-side. Read-only roles cannot mutate records. Session tokens, password hashes and private object keys are never returned in ordinary record responses.

| Area | Endpoints |
|---|---|
| Authentication | `POST /api/auth/login`, `/logout`, `/register`, `/password`; `GET /api/auth/me` |
| Institutions | `GET /api/institutions`, `PUT /api/institutions/{id}` |
| Requirement calculation | `POST /api/requirements/calculate`, `GET /api/rules` |
| Deposits | `GET/POST /api/deposits`, `GET /api/deposits/{id}`, `PATCH /api/deposits/{id}/instrument`, `POST /api/deposits/{id}/submit` |
| Upload/extraction | `POST /api/deposits/{id}/documents` (multipart), `POST /api/documents/{id}/retry`, `POST /api/extractions/{id}/corrections` |
| Private viewing | `GET /api/documents/{id}/access`, then the returned authenticated two-minute URL |
| Officer review | `POST /api/deposits/{id}/assign`, `/observations`, `/clarification` |
| Discrepancies | `POST /api/discrepancies/{id}/respond`, `/resolve` |
| Verification | `POST /api/deposits/{id}/verification/mock`, `/verification/manual`; `POST /api/verifications/{id}/evidence` |
| Renewal | `POST /api/deposits/{id}/replace` |
| Release | `POST /api/deposits/{id}/release`, `GET /api/releases`, `POST /api/clearances/{id}/decision`, `POST /api/releases/{id}/decision`, `/resubmit`, `/complete` |
| Insights | `GET /api/dashboard`, `/notifications`, `/audit`, `/reports/export?kind=deposits` or `kind=audit` |
| Read tracking | `POST /api/notifications/{id}/read` |
| Administration | `GET/POST /api/admin/users`, `POST /api/admin/users/{id}/toggle`, `POST /api/admin/rules`, `POST /api/admin/rules/{id}/approve` |
| Configuration | `GET /api/admin/config`, `PUT /api/admin/config/workflow`, `/alerts` |
| Monitoring | `GET /api/admin/monitor`, `POST /api/admin/monitor/run`, `GET /api/health` |

Deposit filters include `q`, `status`, `bank`, `programme`, `assigned=me`, `min_amount`, `max_amount`, `date_from` and `date_to` (maturity dates). The list is scoped to the caller and the UI paginates it; production-scale server pagination remains future work. CSV exports explicitly cover all authorised records rather than the current visual filter.

Common response codes: `401` unauthenticated, `403` unauthorised role/CSRF/origin, `404` inaccessible or missing record, `409` workflow/uniqueness conflict, `422` validation failure, `429` rate limit, `503` required scanner or rate-limiter unavailable. Release `409` responses include a `detail.blockers` list explaining missing prerequisites.

The mock adapter always returns `simulated: true` and `source: SIMULATED / MOCK BANK DATA`. Production disables the mock endpoint. Manual evidence requires a valid manual request, a bank-confirmation document from the same case, source/reference, verification date, finding and observations.

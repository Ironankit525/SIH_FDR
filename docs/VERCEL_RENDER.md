# Deploy the prototype: Vercel frontend and Render backend

This guide deploys the fictional demo with PDF/Tesseract extraction only. It does not deploy or call a VLM. The frontend remains on Vercel, the API runs as one Docker web service on Render, and PostgreSQL plus private S3-compatible storage retain records across restarts. Supabase can provide both external services.

These files prepare deployment; they do not create hosting accounts or deploy automatically. Publish them to the GitHub branch selected by both hosts before importing the projects. Do not upload `.env`, local databases, encryption keys or real receipts to GitHub.

## 1. Create the external database and private bucket

In Supabase, create a Free project and save its database password privately. Open **Connect → Session pooler** and copy the PostgreSQL URI (session mode, generally port 5432, supports IPv4). Replace the `postgresql://` scheme with `postgresql+psycopg://`, insert the URL-encoded password, and require SSL with `sslmode=require` (append using `&` if a query already exists).

In **Storage**, create the private bucket `depositflow-private`. Obtain the S3 endpoint, signing region, access key ID and secret access key from Storage's S3 settings. Use those S3 credentials, not a Supabase public/anon key. Keep the bucket private; the backend encrypts its objects and serves authorised previews. Keep Supabase's database API inaccessible to anonymous users for the portal tables; the portal uses its own FastAPI authentication, not Supabase client access.

Do not choose SQLite or local document storage for a free Render service. The filesystem is ephemeral. Existing laptop data is not migrated by these steps; the hosted demo starts with new fictional records.

## 2. Prepare keys and choose the frontend name

Generate a Fernet key on your laptop from the repository root:

```bash
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste it only into Render's `STORAGE_ENCRYPTION_KEY`. Render generates `SECRET_KEY` through the Blueprint. Preserve both keys across deploys. Choose a private demo password of at least 12 characters before the first seed.

Choose a Vercel project name and note the actual assigned production domain when creating the project. The initial frontend deployment can wait until Render's address is known. Use that exact HTTPS origin as Render's `FRONTEND_ORIGIN`, without a trailing slash. If the assigned domain changes, update Render and redeploy it. Preview domains are not automatically authorised.

## 3. Create Render from the Blueprint

In Render choose **New → Blueprint**, connect GitHub, grant access to this repository, and select the branch containing `render.yaml`. Review the plan before creating: this Blueprint requests one **Free** Docker web service, no paid database, disk or GPU.

Fill the prompted values:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase session-pooler URI with `postgresql+psycopg://` and SSL |
| `STORAGE_ENCRYPTION_KEY` | Generated Fernet key |
| `DEMO_PASSWORD` | Your chosen private demo password, at least 12 characters |
| `FRONTEND_ORIGIN` | Exact Vercel production origin, such as `https://your-project.vercel.app` |
| `S3_ENDPOINT` | Endpoint supplied by Supabase Storage |
| `S3_REGION` | Signing region supplied by Supabase |
| `S3_ACCESS_KEY` | S3 access key ID |
| `S3_SECRET_KEY` | S3 secret access key |

The Blueprint sets `EXTRACTION_PROVIDER=ocr`, `STORAGE_BACKEND=s3`, `S3_BUCKET=depositflow-private`, `JOB_MODE=local`, and `COOKIE_SECURE=true`. Do not add VLM settings for this deployment.

It deliberately uses `ENVIRONMENT=development`, `SEED_DEMO=true`, and structural upload validation (`REQUIRE_MALWARE_SCAN=false`) for a fictional prototype. It is not a production financial service. Share credentials only with intended testers and use fictional documents. Production mode has additional key/scanner requirements and refuses demo seeding.

Render builds `backend/Dockerfile` with context `backend/` and runs `python start_render.py`. The startup script checks required environment settings, applies Alembic migrations, seeds fictional data idempotently without exporting local PDF files, and starts Uvicorn on Render's `PORT`.

Changing `DEMO_PASSWORD` later does not reset existing seeded accounts. The UI's demo shortcut still uses the public local password; type your hosted password manually instead.

Wait for a successful deploy and open:

```text
https://YOUR-RENDER-HOST/api/health
```

Expect `{"status":"ok","application":"DepositFlow","demo":true}`. This checks the API; an upload and preview are still required to verify database/storage functionality.

## 4. Deploy the frontend on Vercel

Import the GitHub repository, granting access to this repository only if desired. Use:

| Setting | Value |
| --- | --- |
| Root directory | `frontend` |
| Framework | Vite |
| Build command | `npm run build` |
| Output directory | `dist` |
| Production branch | The published branch with these deployment files |
| Environment variable | `BACKEND_ORIGIN=https://YOUR-RENDER-HOST` |

`BACKEND_ORIGIN` is only the origin: do not append `/api`, include a password, or use localhost. Configure it before deploying. `frontend/vercel.mjs` rejects a missing or malformed origin instead of silently deploying broken API routes.

The Vercel config proxies `/api/:path*` to the backend's `/api/:path*`. Non-API page routes fall back to `index.html`. Browser calls and cookies remain on the frontend origin. Do not add database, S3 or encryption credentials to Vercel or any `VITE_*` variable. No frontend secrets are needed.

The config uses Vercel's supported JavaScript configuration format; do not create a competing `vercel.json`. Redeploy after changing `BACKEND_ORIGIN`.

## 5. Verify from the deployed website

1. Open `https://YOUR-VERCEL-HOST/api/health`. It must return JSON, not frontend HTML.
2. Sign in through Institute using `institution@demo.local` and your hosted demo password.
3. Create a draft, upload a fictional receipt as **Instrument**, wait for processing, and open its preview.
4. Inspect Evidence comparison. PDF/OCR processing should run; no VLM call is configured. Missing fields should remain reviewable rather than be invented.
5. Refresh a case URL directly. It should open the app, not a Vercel 404.
6. Sign out and sign in as `officer@demo.local`; assign and review the case.
7. Test account switching in two tabs; the older tab should lock.
8. Restart the Render service, sign in again if needed, and confirm the case and encrypted document preview still exist.

## Free-tier constraints and troubleshooting

- Render Free sleeps after inactivity and has limited memory. The first request may be slow. Start with one small, single-page receipt; OCR resource usage must be checked before promising concurrent or large-document support. Deadline jobs do not run while the service is asleep; run the monitor after waking it. Persistent queued jobs resume when the application runs again, subject to retry/lease limits.
- Supabase free storage/database quotas and inactivity policies still apply. This is a limited prototype setup, not guaranteed continuous availability.
- `Untrusted request origin`: correct `FRONTEND_ORIGIN` to the actual browser origin, then redeploy Render. Do not disable the origin check.
- Missing database tables: inspect startup migration logs. Do not run the local reset script against the hosted database.
- Login rejected: enter the chosen hosted password manually; reseeding does not change passwords.
- Upload/preview failure: check bucket privacy/name, S3 endpoint/region/credentials and the unchanged encryption key. Do not make the bucket public to fix it.
- Vercel configuration error: set `BACKEND_ORIGIN` in the correct deployment environment and redeploy.

Reference documentation: [Render Blueprints](https://render.com/docs/blueprint-spec), [Render Free limits](https://render.com/docs/free), [Vercel programmatic configuration](https://vercel.com/docs/project-configuration/vercel-ts), [Supabase PostgreSQL connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [Supabase S3 authentication](https://supabase.com/docs/guides/storage/s3/authentication).

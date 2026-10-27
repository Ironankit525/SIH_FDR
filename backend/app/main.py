import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, StatementError
from .config import settings
from .auth_routes import router as auth
from .deposit_routes import router as deposits
from .review_routes import router as reviews
from .admin_routes import router as admin
from .bank_routes import router as bank_router


@asynccontextmanager
async def lifespan(app):
    task = None
    if settings.job_mode == "local":
        from .jobs import local_scheduler
        task = asyncio.create_task(local_scheduler())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AICTE DepositFlow", version="1.0.0", description="SIH26265 prototype. Fictional institutions; labelled simulated bank data. No payment execution.", lifespan=lifespan)
allowed_origins = [settings.frontend_origin]
if settings.environment != "production":
    for extra in ("http://localhost:5173", "http://127.0.0.1:5173"):
        if extra not in allowed_origins:
            allowed_origins.append(extra)

app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "PUT"], allow_headers=["Content-Type", "X-CSRF-Token"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    if settings.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={"detail": "This action conflicts with an existing record or database constraint. Refresh and review the record."})


@app.exception_handler(StatementError)
async def invalid_identifier(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Invalid record identifier or field value"})


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok", "application": "DepositFlow", "demo": settings.environment != "production"}


app.include_router(auth)
app.include_router(deposits)
app.include_router(reviews)
app.include_router(admin)
app.include_router(bank_router)

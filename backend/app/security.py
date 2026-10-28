import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from .db import get_db
from .models import AuthSession, SecurityDeposit, User

passwords = PasswordHash.recommended()
_dummy_hash = passwords.hash(secrets.token_urlsafe(32))
_attempts = defaultdict(list)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def rate_limit(key: str, limit=10, seconds=60):
    from .config import settings
    if settings.job_mode == "celery":
        from redis import Redis
        try:
            redis = Redis.from_url(settings.redis_url)
            redis_key = "rate:" + digest(key) + ":" + str(int(time.time() // seconds))
            count = redis.incr(redis_key)
            redis.expire(redis_key, seconds + 1)
        except Exception:
            raise HTTPException(503, "Rate limiter unavailable; please retry")
    else:
        now = time.monotonic()
        _attempts[key] = [t for t in _attempts[key] if now - t < seconds]
        _attempts[key].append(now)
        count = len(_attempts[key])
        if len(_attempts) > 10000:
            for old in list(_attempts):
                if not _attempts[old] or now - _attempts[old][-1] >= seconds:
                    del _attempts[old]
    if count > limit:
        raise HTTPException(429, "Too many requests. Try again shortly.", headers={"Retry-After": str(seconds)})


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("df_session", "")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(token))) if token else None
    now = datetime.now(timezone.utc)
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(401, "Sign in to continue")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account unavailable")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not hmac.compare_digest(session.csrf_token, request.headers.get("X-CSRF-Token", "")):
            raise HTTPException(403, "Invalid CSRF token; refresh and try again")
        rate_limit("write:" + user.id, 120)
    request.state.auth_session = session
    return user


def require_roles(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, "Your role does not permit this action")


def get_deposit(db, user, deposit_id, lock=False):
    query = select(SecurityDeposit).where(SecurityDeposit.id == deposit_id)
    if user.role == "institution":
        query = query.where(SecurityDeposit.institution_id == user.institution_id)
    if lock:
        query = query.with_for_update()
    try:
        deposit = db.scalar(query)
    except (ValueError, AttributeError):
        deposit = None
    if not deposit:
        raise HTTPException(404, "Deposit not found")
    if user.role == "bank":
        from .matching import normalise_bank
        from .models import VerificationRequest
        user_bank_key = normalise_bank(user.bank_name or "")
        reqs = db.scalars(select(VerificationRequest).where(VerificationRequest.deposit_id == deposit.id)).all()
        has_access = any(normalise_bank(r.bank_name or "") == user_bank_key for r in reqs if r.bank_name)
        if not has_access:
            raise HTTPException(404, "Deposit not found")
    return deposit


def require_owner(user, deposit):
    require_roles(user, "institution")
    if user.institution_id != deposit.institution_id:
        raise HTTPException(404, "Deposit not found")

import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, delete
from . import schemas
from .config import settings
from .db import get_db
from .models import User, AuthSession, Institution, Programme, utcnow
from .security import current_user, passwords, digest, rate_limit, _dummy_hash
from .presenters import record
from .audit import audit

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login")
def login(body: schemas.Login, request: Request, response: Response, db=Depends(get_db)):
    rate_limit("login:" + (request.client.host if request.client else "local"), 20, 60)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = passwords.verify(body.password, user.password_hash if user else _dummy_hash)
    if not user or not valid or not user.active:
        raise HTTPException(401, "Email or password is incorrect")
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session = AuthSession(user_id=user.id, token_hash=digest(token), csrf_token=csrf, expires_at=utcnow() + timedelta(hours=8))
    db.add(session)
    audit(db, user, "signed_in", user.id, user.institution_id)
    db.commit()
    response.set_cookie("df_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=28800)
    response.set_cookie("df_csrf", csrf, httponly=False, secure=settings.cookie_secure, samesite="lax", max_age=28800)
    return record(user)


@router.get("/me")
def me(user=Depends(current_user)):
    return record(user)


@router.post("/logout")
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie("df_session")
    response.delete_cookie("df_csrf")
    return {"message": "Signed out"}


@router.post("/register", status_code=201)
def register(body: schemas.Registration, request: Request, db=Depends(get_db)):
    rate_limit("register:" + (request.client.host if request.client else "local"), 5, 3600)
    if settings.environment == "production":
        raise HTTPException(403, "Production onboarding requires administrator provisioning")
    if db.scalar(select(User).where(User.email == body.contact_email.lower())):
        raise HTTPException(409, "This email is already registered")
    institution = Institution(**body.model_dump(exclude={"administrator_name", "password", "programme", "level"}), code="DEMO-" + secrets.token_hex(4).upper())
    db.add(institution)
    db.flush()
    db.add(Programme(institution_id=institution.id, name=body.programme, level=body.level))
    user = User(email=body.contact_email.lower(), name=body.administrator_name, password_hash=passwords.hash(body.password), role="institution", institution_id=institution.id)
    db.add(user)
    audit(db, user, "institution_registered", institution.id, institution.id, after={"fictional": True})
    db.commit()
    return {"message": "Demo institution created. Sign in with your email and password."}


@router.post("/password")
def change_password(body: schemas.PasswordInput, response: Response, user=Depends(current_user), db=Depends(get_db)):
    if not passwords.verify(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = passwords.hash(body.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, user, "password_changed", user.id, user.institution_id)
    db.commit()
    response.delete_cookie("df_session")
    response.delete_cookie("df_csrf")
    return {"message": "Password updated. Sign in again."}

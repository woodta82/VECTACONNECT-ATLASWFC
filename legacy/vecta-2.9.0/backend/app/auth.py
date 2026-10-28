"""Login, logout and password change for the single shared credential.

Phase 1 security hardening (see docs/SECURITY.md):
- The password exists only as a PBKDF2 hash in the auth_credential table —
  never plaintext in the database, config, or logs. The LOGIN_PASSWORD env
  var is used exactly once, to seed that table on first startup.
- Sessions are server-side rows; the browser holds an opaque token in an
  HttpOnly cookie it can't read from JavaScript, paired with a CSRF token
  the frontend sends as a header on mutating requests.
- 5 failed logins from one IP inside 15 minutes locks that IP out for 15
  minutes. Every success, failure, lockout, logout and password change is
  recorded in the security_events table.
"""
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuthCredential
from .security import (
    LOCKOUT_THRESHOLD,
    SESSION_COOKIE_NAME,
    account_failure_delay_seconds,
    clear_failed_logins,
    create_session,
    is_locked_out,
    log_security_event,
    record_failed_login,
    revoke_all_sessions,
    revoke_session,
    validate_password_strength,
    verify_password,
    hash_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Effective client IP for lockout tracking and the security log.

    X-Forwarded-For handling matters here: clients can send their own
    X-Forwarded-For header, and proxies APPEND the real peer address to
    it — so the FIRST entry is attacker-controlled and the LAST entry is
    the one added by the trusted proxy directly in front of this app
    (Railway's edge). Taking the last entry means an attacker cannot
    spoof their way past the IP lockout or falsify the security log by
    supplying a forged header."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    production = settings.environment == "production"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=production,
        # Frontend and backend are on different registrable domains in
        # production (both under Railway's public-suffix-listed domain),
        # so the cookie must be SameSite=None + Secure to be sent
        # cross-site. Locally (same-site localhost) Lax works over HTTP.
        samesite="none" if production else "lax",
        path="/",
        # No max_age: a browser-session cookie, consistent with the
        # "log in every time" behaviour — plus the server-side 24h expiry.
    )


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    csrf_token: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)

    if is_locked_out(ip):
        log_security_event(db, "login_lockout_rejected", ip, "basis: per-IP lockout (5 failures / 15 min)")
        raise HTTPException(
            429, f"Too many failed attempts — locked out for 15 minutes after {LOCKOUT_THRESHOLD} failures."
        )

    # Account-level escalating throttle (see security.py) — slows
    # distributed attacks that rotate IPs, without ever hard-locking the
    # single authorised account.
    delay = account_failure_delay_seconds()
    if delay > 0:
        time.sleep(delay)

    credential = db.query(AuthCredential).first()
    valid_user = body.username.strip().lower() == settings.login_username.strip().lower()
    valid_pass = bool(credential) and verify_password(body.password, credential.password_hash)

    if not (valid_user and valid_pass):
        record_failed_login(ip)
        locked_now = is_locked_out(ip)
        log_security_event(
            db,
            "login_failed",
            ip,
            "basis: per-IP lockout threshold reached" if locked_now else None,
        )
        raise HTTPException(401, "Incorrect username or password")

    clear_failed_logins(ip)
    raw_token, csrf_token = create_session(db)
    _set_session_cookie(response, raw_token)
    log_security_event(db, "login_success", ip)
    return LoginResponse(csrf_token=csrf_token)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    log_security_event(db, "logout", _client_ip(request))
    return {"ok": True}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    credential = db.query(AuthCredential).first()
    if not credential or not verify_password(body.current_password, credential.password_hash):
        log_security_event(db, "password_change_failed", ip, "current password incorrect")
        raise HTTPException(401, "Current password is incorrect")

    strength_error = validate_password_strength(body.new_password)
    if strength_error:
        raise HTTPException(400, strength_error)
    if body.new_password == body.current_password:
        raise HTTPException(400, "New password must be different from the current password.")

    credential.password_hash = hash_password(body.new_password)
    db.commit()
    revoked = revoke_all_sessions(db)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    log_security_event(db, "password_changed", ip, f"{revoked} session(s) revoked")
    return {"ok": True, "detail": "Password changed. All sessions have been logged out — please log in again."}

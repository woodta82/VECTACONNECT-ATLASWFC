"""Single shared login: service layer over the Database protocol.

One credential row; any number of concurrent sessions (one login is not
one device). Every outcome is written to `audit_events` with the session
reference, never the individual (a shared login cannot identify one).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ..domain import auth_policy as ap
from ..repo.db import Database
from .audit import RequestMeta, audit


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class LoginResult:
    raw_token: str
    csrf_token: str
    expires_at: datetime


@dataclass
class SessionInfo:
    token_hash: str
    csrf_hash: str
    session_ref: str
    created_at: datetime
    expires_at: datetime


def bootstrap_credential(db: Database, username: str, password: str) -> bool:
    """Insert-only: if a credential exists this is a no-op forever."""
    if db.one("cred_get") is not None:
        return False
    if not username or not password:
        return False
    err = ap.password_strength_error(password)
    if err:
        raise ValueError(f"bootstrap password rejected: {err}")
    db.run("cred_bootstrap", username=username.strip().lower(), hash=ap.hash_password(password))
    return True


def login(db: Database, username: str, password: str, meta: RequestMeta, *,
          now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), sleep: Callable[[float], Any] = time.sleep) -> LoginResult:
    ip_key = f"ip:{meta.ip}"
    ip_failures = [r["failed_at"] for r in db.all("throttle_recent", key=ip_key)]
    if ap.ip_locked(ip_failures, now()):
        audit(db, "login_locked_out", meta)
        raise AuthError(429, "Too many failed attempts from this address. Try again in 15 minutes.")
    delay = ap.account_delay_seconds([r["failed_at"] for r in db.all("throttle_recent", key="account")], now())
    if delay:
        sleep(delay)

    cred = db.one("cred_get")
    ok = (cred is not None and username.strip().lower() == cred["username"]
          and ap.verify_password(password, cred["password_hash"]))
    if not ok:
        db.run("throttle_add", key=ip_key)
        db.run("throttle_add", key="account")
        audit(db, "login_failed", meta)
        raise AuthError(401, "Incorrect username or password")

    db.run("throttle_clear", key=ip_key)
    raw, csrf = ap.new_session_tokens()
    expires = now() + ap.SESSION_LIFETIME
    db.run("session_insert", token_hash=ap.token_hash(raw), csrf_hash=ap.token_hash(csrf), expires_at=expires,
           ip=meta.ip, ua=(meta.user_agent or "")[:300])
    audit(db, "login_success", meta.with_session(ap.session_ref(raw)))
    return LoginResult(raw, csrf, expires)


def validate(db: Database, raw_token: str | None, *, now: datetime | None = None) -> SessionInfo | None:
    if not raw_token:
        return None
    th = ap.token_hash(raw_token)
    row = db.one("session_get", token_hash=th)
    if row is None:
        return None
    now = now or datetime.now(timezone.utc)
    ok, _why = ap.session_valid(
        ap.SessionRow(row["created_at"], row["last_used_at"], row["expires_at"], row["revoked_at"]),
        now=now, sessions_valid_after=row["sessions_valid_after"])
    if not ok:
        return None
    db.run("session_touch", token_hash=th)
    return SessionInfo(th, row["csrf_token_hash"], th[:12], row["created_at"], row["expires_at"])


def logout(db: Database, raw_token: str | None, meta: RequestMeta) -> None:
    if raw_token:
        db.run("session_revoke", token_hash=ap.token_hash(raw_token))
    audit(db, "logout", meta)


def logout_all(db: Database, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        tx.run("cred_invalidate_sessions")
        tx.run("sessions_revoke_all")
        audit(tx, "logout_all_sessions", meta)


def change_password(db: Database, current: str, new: str, meta: RequestMeta) -> None:
    cred = db.one("cred_get")
    if cred is None or not ap.verify_password(current, cred["password_hash"]):
        audit(db, "password_change_failed", meta)
        raise AuthError(401, "Current password is incorrect")
    err = ap.password_strength_error(new)
    if err:
        raise AuthError(400, err)
    if new == current:
        raise AuthError(400, "New password must differ from the current password")
    with db.transaction() as tx:
        tx.run("cred_set_password", hash=ap.hash_password(new))
        tx.run("sessions_revoke_all")
        audit(tx, "password_changed", meta, detail={"sessions_revoked": "all"})


def active_session_count(db: Database) -> int:
    return int(db.scalar("sessions_active_count") or 0)

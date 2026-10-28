"""Security middleware for ATLAS.

Two always-on layers plus the session gate below. There is deliberately
NO static shared-secret gate: a key shipped in the frontend build is
readable by anyone who can load the page, so it was never a private
security layer. The DB-backed login session is the sole application
authentication method.

1. Security headers on every response (always on, no config needed).
2. A simple in-memory rate limiter per client IP (always on, generous
   default limits — mainly to stop runaway/looped clients from burning
   through the Anthropic API budget, not a substitute for a real WAF).
"""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import timedelta

from .timeutils import as_aware, utcnow

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

# --------------------------------------------------------------------- headers

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # HSTS only matters over HTTPS (Railway terminates TLS in front of the
    # app) — harmless to send even during local HTTP development.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        return response


# --------------------------------------------------------------------- rate limiting

_WINDOW_SECONDS = 60
_buckets: dict[str, list[float]] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limiter per client IP, in-memory. Adequate for a
    single-instance internal tool; move to a shared store (Redis) if ATLAS
    is ever scaled to multiple backend replicas, since counts here don't
    sync across processes."""

    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.limit = requests_per_minute

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - _WINDOW_SECONDS
        bucket = _buckets[client_ip]
        # Drop timestamps outside the current window
        while bucket and bucket[0] < window_start:
            bucket.pop(0)

        if len(bucket) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded — too many requests. Try again shortly."},
            )

        bucket.append(now)
        return await call_next(request)


PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/auth/login"}


# --------------------------------------------------------------------- password hashing

# PBKDF2-HMAC-SHA256 from the standard library, 600k iterations, per-hash
# random salt. Chosen over bcrypt/argon2 deliberately: it's NIST-approved
# and needs no native-code dependency, and this project's deploy pipeline
# has repeatedly proven fragile enough that adding a compiled wheel to
# requirements.txt for marginal KDF gains is the wrong trade. Format:
# pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex> — iterations stored
# per-hash so they can be raised later without breaking old hashes.

_PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations_s, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_s)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> str | None:
    """Returns an error message, or None if acceptable. Minimum 12 chars
    and at least three of four character classes."""
    if len(password) < 12:
        return "Password must be at least 12 characters."
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        return "Password must include at least three of: lowercase, uppercase, digits, symbols."
    return None


# --------------------------------------------------------------------- sessions (DB-backed)

SESSION_COOKIE_NAME = "atlas_session"
SESSION_LIFETIME_HOURS = 24  # absolute expiry
SESSION_IDLE_MINUTES = 60  # idle expiry — session dies after an hour unused


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db) -> tuple[str, str]:
    """Creates a session row and returns (raw_token, csrf_token). Only the
    SHA-256 of the token is stored, so a DB leak doesn't yield usable
    sessions. Every login mints a brand-new token — there is no
    pre-authentication session that could be fixated, and tokens are
    never reused across logins."""
    from .models import AuthSession  # local import to avoid a models<->security cycle

    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_hash_token(raw_token),
            csrf_token=csrf_token,
            expires_at=utcnow() + timedelta(hours=SESSION_LIFETIME_HOURS),
        )
    )
    db.commit()
    return raw_token, csrf_token


def get_session(db, raw_token: str | None):
    """Returns the live AuthSession row for a raw cookie token, or None.
    Enforces both the absolute expiry and the idle expiry, lazily
    deleting dead rows. Refreshes last_used_at, throttled to one write
    per minute so an active user doesn't generate a DB write on every
    single request."""
    from .models import AuthSession

    if not raw_token:
        return None
    session = db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(raw_token)).first()
    if session is None:
        return None
    now = utcnow()
    expires_at = as_aware(session.expires_at)
    last_used_at = as_aware(session.last_used_at)
    if expires_at < now or (now - last_used_at) > timedelta(minutes=SESSION_IDLE_MINUTES):
        db.delete(session)
        db.commit()
        return None
    if (now - last_used_at) > timedelta(minutes=1):
        session.last_used_at = now
        db.commit()
    return session


def revoke_session(db, raw_token: str | None) -> None:
    from .models import AuthSession

    if not raw_token:
        return
    db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(raw_token)).delete()
    db.commit()


def revoke_all_sessions(db) -> int:
    """Deletes every session — used after a password change so old logins
    can't continue on the previous password's sessions."""
    from .models import AuthSession

    count = db.query(AuthSession).delete()
    db.commit()
    return count


def log_security_event(db, event_type: str, ip: str | None, detail: str | None = None) -> None:
    from .models import SecurityEvent

    db.add(SecurityEvent(event_type=event_type, ip_address=ip, detail=detail))
    db.commit()


# --------------------------------------------------------------------- login lockout

# In-memory failed-attempt tracking per source IP: 5 failures inside 15
# minutes locks that IP out of /auth/login for 15 minutes. In-memory is
# the honest scope for a single backend instance (counts reset on
# restart); the durable record is the security_events table, which logs
# every failure and lockout regardless.

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60
_failed_logins: dict[str, list[float]] = defaultdict(list)

# Account-level escalating delay, complementing the per-IP lockout above.
# The IP lockout alone can be evaded by rotating source IPs, but a hard
# account lockout would let an attacker permanently deny the owner access
# by deliberately tripping it. The compromise: failures against the (one)
# account from ANY IP accumulate here, and each login attempt is delayed
# by 0.5s per recent failure, capped at 5s. That caps a distributed
# brute-force at well under one guess per second globally while the worst
# case for the legitimate owner is a one-off 5-second wait — throttled,
# never locked out.
_account_failures: list[float] = []


def record_account_failure() -> None:
    _account_failures.append(time.time())


def account_failure_delay_seconds() -> float:
    cutoff = time.time() - LOCKOUT_WINDOW_SECONDS
    recent = [t for t in _account_failures if t > cutoff]
    _account_failures[:] = recent
    return min(len(recent) * 0.5, 5.0)


def record_failed_login(ip: str) -> None:
    _failed_logins[ip].append(time.time())
    record_account_failure()


def clear_failed_logins(ip: str) -> None:
    _failed_logins.pop(ip, None)


def is_locked_out(ip: str) -> bool:
    cutoff = time.time() - LOCKOUT_WINDOW_SECONDS
    attempts = [t for t in _failed_logins.get(ip, []) if t > cutoff]
    _failed_logins[ip] = attempts
    return len(attempts) >= LOCKOUT_THRESHOLD


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Always on — enforces the login gate server-side so the login screen
    isn't decorative. Auth comes from the HttpOnly `atlas_session` cookie
    (never readable by page JavaScript), validated against the DB-backed
    session table. Mutating requests (POST/PATCH/PUT/DELETE) additionally
    require an X-CSRF-Token header matching the token issued with the
    session — the standard cookie+CSRF pairing, since HttpOnly cookies are
    sent automatically by browsers and therefore need forgery protection
    that headers-only auth didn't."""

    # Only /auth/login is exempt, and only because no session (and
    # therefore no CSRF token) exists yet at that point — it's also in
    # PUBLIC_PATHS so it never reaches this check. Every other
    # state-changing endpoint, logout included, requires a valid CSRF
    # token: forced logout is a genuine (if low-impact) CSRF target, and
    # the spec requires blanket coverage rather than case-by-case
    # exemptions.
    CSRF_EXEMPT: set[str] = {"/auth/login"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        from .database import SessionLocal  # local import to avoid import cycle at module load

        db = SessionLocal()
        try:
            session = get_session(db, request.cookies.get(SESSION_COOKIE_NAME))
            if session is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not logged in or session expired — please log in again."},
                )
            if (
                request.method in {"POST", "PATCH", "PUT", "DELETE"}
                and request.url.path not in self.CSRF_EXEMPT
            ):
                provided = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(provided, session.csrf_token):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Missing or invalid CSRF token — please log in again."},
                    )
        finally:
            db.close()
        return await call_next(request)

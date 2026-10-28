"""Single shared login: hashing, session validity, throttling (build spec §10).

Carried from the VECTA 2.9.0 baseline (PBKDF2-HMAC-SHA256, per-hash salt,
iterations stored per hash, strength rule), then hardened: session
validity also checks `revoked_at` and the credential's
`sessions_valid_after` (logout-all and password change), and throttling
decisions are computed from durable failure timestamps so replicas agree.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

PBKDF2_ITERATIONS = 600_000
SESSION_LIFETIME = timedelta(hours=12)
SESSION_IDLE = timedelta(minutes=60)
IP_LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW = timedelta(minutes=15)
ACCOUNT_DELAY_PER_FAILURE = 0.5
ACCOUNT_DELAY_CAP = 5.0


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations_s, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_s))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def password_strength_error(password: str) -> str | None:
    if len(password) < 12:
        return "Password must be at least 12 characters."
    classes = sum([any(c.islower() for c in password), any(c.isupper() for c in password),
                   any(c.isdigit() for c in password), any(not c.isalnum() for c in password)])
    if classes < 3:
        return "Password must include at least three of: lowercase, uppercase, digits, symbols."
    return None


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def session_ref(raw_or_hash: str, *, is_hash: bool = False) -> str:
    """Short, non-reversible reference for audit logs."""
    return (raw_or_hash if is_hash else token_hash(raw_or_hash))[:12]


def new_session_tokens() -> tuple[str, str]:
    """Return (raw session token, CSRF token derived from it)."""
    raw = secrets.token_urlsafe(32)
    return raw, derive_csrf(raw)


@dataclass(frozen=True)
class SessionRow:
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


def session_valid(s: SessionRow, *, now: datetime, sessions_valid_after: datetime) -> tuple[bool, str]:
    if s.revoked_at is not None:
        return False, "revoked"
    if s.created_at < sessions_valid_after:
        return False, "invalidated by password change or logout-all"
    if s.expires_at <= now:
        return False, "expired"
    if now - s.last_used_at > SESSION_IDLE:
        return False, "idle timeout"
    return True, "ok"


def derive_csrf(raw_session_token: str) -> str:
    """CSRF token bound to the session: HMAC of a fixed label keyed by the raw
    session token. The page never sees the session token (HttpOnly cookie), so
    a cross-site attacker cannot compute this value. Deterministic per session,
    so every open tab holds the same token and nothing needs rotating."""
    return hmac.new(raw_session_token.encode("utf-8"), b"atlas-csrf-v1", hashlib.sha256).hexdigest()


def csrf_ok(provided: str | None, raw_session_token: str | None) -> bool:
    if not provided or not raw_session_token:
        return False
    return hmac.compare_digest(provided, derive_csrf(raw_session_token))


def ip_locked(failures: Sequence[datetime], now: datetime) -> bool:
    return sum(1 for t in failures if now - t < LOCKOUT_WINDOW) >= IP_LOCKOUT_THRESHOLD


def account_delay_seconds(failures: Sequence[datetime], now: datetime) -> float:
    recent = sum(1 for t in failures if now - t < LOCKOUT_WINDOW)
    return min(recent * ACCOUNT_DELAY_PER_FAILURE, ACCOUNT_DELAY_CAP)


def client_ip(peer: str | None, forwarded_for: str | None, trusted_proxy_hops: int) -> str:
    """One definition used everywhere. With N trusted proxies in front, the
    client is the Nth address from the right of X-Forwarded-For. Entries
    further left are client-controlled and ignored."""
    if trusted_proxy_hops > 0 and forwarded_for:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if len(parts) >= trusted_proxy_hops:
            return parts[-trusted_proxy_hops]
    return peer or "unknown"


def proxy_signature_ok(token: str | None, secret: str, now_epoch: float, *, issuer: str = "netlify") -> bool:
    """Verify a signed-proxy header (Netlify `x-nf-sign`: a compact JWS, HMAC SHA-256, with `iss` and `exp`).

    Used only when PROXY_SIGNATURE_SECRET is set, so that an API reachable from the internet answers only requests that
    came through the web front end's signed proxy rule. Rejects any other algorithm, a bad signature, a wrong issuer
    and an expired token."""
    import base64
    import json

    if not token or not secret or token.count(".") != 2:
        return False

    def b64(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    head_b64, body_b64, sig_b64 = token.split(".")
    try:
        header, claims, sig = json.loads(b64(head_b64)), json.loads(b64(body_b64)), b64(sig_b64)
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(header, dict) or header.get("alg") != "HS256" or not isinstance(claims, dict):
        return False
    expected = hmac.new(secret.encode(), f"{head_b64}.{body_b64}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return False
    exp = claims.get("exp")
    return claims.get("iss") == issuer and isinstance(exp, (int, float)) and exp > now_epoch

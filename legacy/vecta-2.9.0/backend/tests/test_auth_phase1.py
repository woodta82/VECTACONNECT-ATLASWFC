"""Phase 1 security test suite (rebuild spec §16 auth items, §17 item:
"must run without a live Anthropic API key and without importing
unnecessary live AI dependencies").

DECOUPLED BY DESIGN: these tests build a minimal FastAPI app containing
only the auth router, the session middleware and two dummy protected
routes. They never import `app.main`, so they never pull in the routers
-> scanner -> anthropic chain. No test makes a network call, and the
production password appears nowhere — safe test credentials only.

Run from backend/:  pytest tests/ -v
(conftest.py sets DATABASE_URL to SQLite and safe credentials.)
"""
import time as time_module
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.database import Base, SessionLocal, engine
from app.timeutils import utcnow
from app.models import AuthCredential, AuthSession, SecurityEvent, User
from app.security import (
    SESSION_COOKIE_NAME,
    SessionAuthMiddleware,
    _account_failures,
    _failed_logins,
    account_failure_delay_seconds,
    clear_failed_logins,
    hash_password,
    is_locked_out,
    record_failed_login,
    validate_password_strength,
    verify_password,
)


def seed_auth_credential() -> None:
    """Local copy of the production bootstrap (app/main.py) with identical
    insert-only semantics — duplicated here solely to avoid importing
    app.main, which would drag in the AI stack."""
    from app.config import settings

    db = SessionLocal()
    try:
        if db.query(AuthCredential).first() is not None:
            return
        if not settings.login_password:
            return
        db.add(AuthCredential(password_hash=hash_password(settings.login_password)))
        db.commit()
    finally:
        db.close()


def build_test_app() -> FastAPI:
    """Minimal app: auth endpoints + session/CSRF middleware + two dummy
    protected routes standing in for real GET/PATCH endpoints."""
    test_app = FastAPI()
    test_app.add_middleware(SessionAuthMiddleware)
    test_app.include_router(auth_module.router)

    @test_app.get("/protected-read")
    def protected_read():
        return {"ok": True}

    @test_app.patch("/protected-write")
    def protected_write():
        return {"ok": True}

    return test_app


TEST_PW = "TestBootstrap-Pw-1!"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_auth_credential()
    _failed_logins.clear()
    _account_failures.clear()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(build_test_app()) as c:
        yield c


def login(client, password=TEST_PW, username="tom@vectasports"):
    return client.post("/auth/login", json={"username": username, "password": password})


# ------------------------------------------------------------ password hashing

def test_password_hash_format_and_roundtrip():
    h = hash_password("SomePassword123!")
    scheme, iterations, salt, digest = h.split("$")
    assert scheme == "pbkdf2_sha256"          # algorithm identifier stored
    assert int(iterations) == 600_000          # iteration count stored per-hash
    assert len(bytes.fromhex(salt)) == 16      # random salt stored per-hash
    assert verify_password("SomePassword123!", h)
    assert not verify_password("WrongPassword123!", h)


def test_password_hashes_are_salted_uniquely():
    assert hash_password("same-input-Aa1!") != hash_password("same-input-Aa1!")


def test_password_strength_rules():
    assert validate_password_strength("short1!A") is not None          # too short
    assert validate_password_strength("alllowercaseonly") is not None  # one class
    assert validate_password_strength("GoodPassw0rd-Longer") is None   # acceptable


def test_credential_row_contains_no_plaintext():
    db = SessionLocal()
    try:
        row = db.query(AuthCredential).first()
        assert row is not None
        assert TEST_PW not in row.password_hash
        assert row.password_hash.startswith("pbkdf2_sha256$")
    finally:
        db.close()


# ------------------------------------------------------------ bootstrap seeding

def test_seed_is_insert_only_and_cannot_overwrite():
    db = SessionLocal()
    try:
        original = db.query(AuthCredential).first().password_hash
    finally:
        db.close()
    seed_auth_credential()  # second call must be a no-op
    seed_auth_credential()
    db = SessionLocal()
    try:
        rows = db.query(AuthCredential).all()
        assert len(rows) == 1                     # never duplicated
        assert rows[0].password_hash == original  # never overwritten
    finally:
        db.close()


def test_env_var_is_not_a_fallback_after_password_change(client):
    r = login(client)
    csrf = r.json()["csrf_token"]
    r2 = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PW, "new_password": "BrandNew-Passw0rd-22!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r2.status_code == 200
    # Old (env/bootstrap) password must no longer authenticate:
    assert login(client).status_code == 401
    assert login(client, password="BrandNew-Passw0rd-22!").status_code == 200


# ------------------------------------------------------------ login + sessions

def test_login_success_sets_httponly_cookie_and_returns_csrf(client):
    r = login(client)
    assert r.status_code == 200
    assert "csrf_token" in r.json()
    set_cookie = r.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    # Session identifier appears nowhere in the JSON body:
    assert set_cookie.split(f"{SESSION_COOKIE_NAME}=")[1].split(";")[0] not in r.text


def test_login_rejects_wrong_password_and_wrong_username(client):
    assert login(client, password="Wrong-Passw0rd-1!").status_code == 401
    assert login(client, username="intruder@example.com").status_code == 401
    # Error message is generic — doesn't reveal which field was wrong:
    r = login(client, username="intruder@example.com")
    assert "username or password" in r.json()["detail"].lower()


def test_username_is_normalised_case_and_whitespace(client):
    assert login(client, username="  TOM@VECTASPORTS  ").status_code == 200


def test_protected_endpoint_requires_session(client):
    assert client.get("/protected-read").status_code == 401


def test_session_token_stored_hashed_not_raw(client):
    r = login(client)
    raw = r.headers["set-cookie"].split(f"{SESSION_COOKIE_NAME}=")[1].split(";")[0]
    db = SessionLocal()
    try:
        rows = db.query(AuthSession).all()
        assert len(rows) == 1
        assert rows[0].token_hash != raw          # only a hash is stored
        assert len(rows[0].token_hash) == 64      # sha256 hex
        assert rows[0].created_at is not None
        assert rows[0].last_used_at is not None
        assert rows[0].expires_at is not None
    finally:
        db.close()


def test_each_login_mints_a_new_session_token(client):
    t1 = login(client).headers["set-cookie"].split(f"{SESSION_COOKIE_NAME}=")[1].split(";")[0]
    t2 = login(client).headers["set-cookie"].split(f"{SESSION_COOKIE_NAME}=")[1].split(";")[0]
    assert t1 != t2


def test_logout_invalidates_immediately(client):
    r = login(client)
    csrf = r.json()["csrf_token"]
    assert client.get("/protected-read").status_code == 200
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.get("/protected-read").status_code == 401
    db = SessionLocal()
    try:
        assert db.query(AuthSession).count() == 0
    finally:
        db.close()


def test_absolute_expiry_enforced(client):
    login(client)
    db = SessionLocal()
    try:
        s = db.query(AuthSession).first()
        s.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert client.get("/protected-read").status_code == 401


def test_idle_expiry_enforced(client):
    login(client)
    db = SessionLocal()
    try:
        s = db.query(AuthSession).first()
        s.last_used_at = utcnow() - timedelta(minutes=61)
        db.commit()
    finally:
        db.close()
    assert client.get("/protected-read").status_code == 401


# ------------------------------------------------------------ timezone handling

def test_utcnow_is_timezone_aware():
        assert utcnow().tzinfo is not None


def test_as_aware_coerces_naive_and_preserves_aware():
    from datetime import timezone as _tz
    from app.timeutils import as_aware

    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=_tz.utc)
    assert as_aware(naive) == aware      # naive assumed UTC
    assert as_aware(aware) == aware      # already aware, unchanged
    assert as_aware(None) is None


def test_naive_aware_comparison_would_raise_without_coercion():
    """Documents why as_aware() is load-bearing rather than cosmetic:
    SQLite returns naive datetimes, and comparing those to an aware now()
    raises. Without coercion the auth path would crash on every request."""
    from app.timeutils import as_aware, utcnow

    naive = datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(TypeError):
        _ = utcnow() - naive
    assert (utcnow() - as_aware(naive)).days >= 0  # coerced form works


def test_session_expiry_still_correct_after_timezone_change(client):
    """Absolute and idle expiry must both still work now that stored
    timestamps round-trip through SQLite as naive values."""
    login(client)
    assert client.get("/protected-read").status_code == 200

    db = SessionLocal()
    try:
        s = db.query(AuthSession).first()
        s.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert client.get("/protected-read").status_code == 401


def test_idle_expiry_still_correct_after_timezone_change(client):
    login(client)
    db = SessionLocal()
    try:
        s = db.query(AuthSession).first()
        s.last_used_at = utcnow() - timedelta(minutes=61)
        db.commit()
    finally:
        db.close()
    assert client.get("/protected-read").status_code == 401


# ------------------------------------------------------------ CSRF

def test_mutating_request_without_csrf_rejected(client):
    login(client)
    r = client.patch("/protected-write")
    assert r.status_code == 403


def test_mutating_request_with_wrong_csrf_rejected(client):
    login(client)
    r = client.patch("/protected-write", headers={"X-CSRF-Token": "forged-token"})
    assert r.status_code == 403


def test_mutating_request_with_valid_csrf_accepted(client):
    csrf = login(client).json()["csrf_token"]
    r = client.patch("/protected-write", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200


def test_get_requests_do_not_require_csrf(client):
    login(client)
    assert client.get("/protected-read").status_code == 200


def test_logout_requires_csrf(client):
    """Logout is state-changing, so it is NOT CSRF-exempt — only
    /auth/login is, and only because no session exists yet at that point."""
    login(client)
    assert client.post("/auth/logout").status_code == 403
    assert client.get("/protected-read").status_code == 200  # still logged in


# ------------------------------------------------------------ password change

def test_password_change_requires_correct_current(client):
    csrf = login(client).json()["csrf_token"]
    r = client.post(
        "/auth/change-password",
        json={"current_password": "Wrong-Current-1!", "new_password": "Another-Passw0rd-9!"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 401


def test_password_change_rejects_weak_and_reused(client):
    csrf = login(client).json()["csrf_token"]
    weak = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PW, "new_password": "short"},
        headers={"X-CSRF-Token": csrf},
    )
    assert weak.status_code == 400
    reused = client.post(
        "/auth/change-password",
        json={"current_password": TEST_PW, "new_password": TEST_PW},
        headers={"X-CSRF-Token": csrf},
    )
    assert reused.status_code == 400


def test_password_change_uses_fresh_salt_and_revokes_all_sessions(client):
    """Two independent sessions (two browsers), password changed from the
    first — both must be revoked.

    NOTE ON THE PREVIOUS FAILURE: an earlier version of this test called
    login() twice on the SAME TestClient. That client keeps one cookie
    jar, so the second login overwrote the first session's cookie while
    the test still sent the FIRST session's CSRF token. The 403 was
    correct behaviour — a CSRF token only validates against the session
    that issued it — but the test was simulating something that cannot
    happen in a real browser. A second session means a second client.
    """
    csrf_a = login(client).json()["csrf_token"]
    db = SessionLocal()
    try:
        old_hash = db.query(AuthCredential).first().password_hash
    finally:
        db.close()

    # Second, genuinely independent session (separate cookie jar).
    with TestClient(build_test_app()) as client_b:
        login(client_b)
        db = SessionLocal()
        try:
            assert db.query(AuthSession).count() == 2  # both sessions coexist
        finally:
            db.close()
        assert client_b.get("/protected-read").status_code == 200

        # Change the password from session A, using session A's own CSRF.
        r = client.post(
            "/auth/change-password",
            json={"current_password": TEST_PW, "new_password": "Rotated-Passw0rd-77!"},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert r.status_code == 200

        db = SessionLocal()
        try:
            new_hash = db.query(AuthCredential).first().password_hash
            assert new_hash != old_hash
            assert new_hash.split("$")[2] != old_hash.split("$")[2]  # fresh salt
            assert new_hash.split("$")[1] == old_hash.split("$")[1]  # same iteration count
            assert db.query(AuthSession).count() == 0                # EVERY session revoked
        finally:
            db.close()

        # Both sessions are dead, including the one that didn't make the change.
        assert client.get("/protected-read").status_code == 401
        assert client_b.get("/protected-read").status_code == 401


def test_concurrent_sessions_are_independent(client):
    """Documented behaviour: the single authorised account may hold several
    concurrent sessions. Logging in from a second browser does NOT
    invalidate the first."""
    login(client)
    with TestClient(build_test_app()) as client_b:
        login(client_b)
        db = SessionLocal()
        try:
            sessions = db.query(AuthSession).all()
            assert len(sessions) == 2
            assert sessions[0].token_hash != sessions[1].token_hash
            assert sessions[0].csrf_token != sessions[1].csrf_token  # own CSRF each
        finally:
            db.close()
        # Both remain usable — no silent invalidation.
        assert client.get("/protected-read").status_code == 200
        assert client_b.get("/protected-read").status_code == 200


def test_csrf_token_is_bound_to_its_own_session(client):
    """A CSRF token from session A must not authorise a request carrying
    session B's cookie — this is what the earlier failing test actually
    (correctly) demonstrated."""
    csrf_a = login(client).json()["csrf_token"]
    with TestClient(build_test_app()) as client_b:
        csrf_b = login(client_b).json()["csrf_token"]
        assert csrf_a != csrf_b
        # Session B's cookie + session A's CSRF -> rejected.
        assert client_b.patch("/protected-write", headers={"X-CSRF-Token": csrf_a}).status_code == 403
        # Session B's cookie + session B's CSRF -> accepted.
        assert client_b.patch("/protected-write", headers={"X-CSRF-Token": csrf_b}).status_code == 200


def test_logout_of_one_session_leaves_the_other_active(client):
    csrf_a = login(client).json()["csrf_token"]
    with TestClient(build_test_app()) as client_b:
        login(client_b)
        client.post("/auth/logout", headers={"X-CSRF-Token": csrf_a})
        assert client.get("/protected-read").status_code == 401    # A logged out
        assert client_b.get("/protected-read").status_code == 200  # B unaffected


# ------------------------------------------------------------ lockout + throttling

def test_ip_lockout_after_five_failures(client):
    for _ in range(5):
        assert login(client, password="Wrong-Passw0rd-1!").status_code == 401
    r = login(client)  # correct password, but IP is now locked out
    assert r.status_code == 429


def test_lockout_recovers_after_window():
    ip = "203.0.113.9"
    for _ in range(5):
        record_failed_login(ip)
    assert is_locked_out(ip)
    _failed_logins[ip] = [t - (16 * 60) for t in _failed_logins[ip]]  # age past the window
    assert not is_locked_out(ip)


def test_clear_failed_logins_on_success():
    ip = "203.0.113.10"
    for _ in range(4):
        record_failed_login(ip)
    clear_failed_logins(ip)
    assert not is_locked_out(ip)


def test_account_level_delay_escalates_and_caps():
    _account_failures.clear()
    assert account_failure_delay_seconds() == 0
    for _ in range(4):
        _account_failures.append(time_module.time())
    assert account_failure_delay_seconds() == 2.0
    for _ in range(20):
        _account_failures.append(time_module.time())
    assert account_failure_delay_seconds() == 5.0  # capped — never a hard account lock


# ------------------------------------------------------------ security log

def test_security_events_recorded_without_secrets(client):
    login(client, password="Wrong-Passw0rd-1!")
    csrf = login(client).json()["csrf_token"]
    client.post(
        "/auth/change-password",
        json={"current_password": TEST_PW, "new_password": "Logged-Passw0rd-31!"},
        headers={"X-CSRF-Token": csrf},
    )
    db = SessionLocal()
    try:
        events = db.query(SecurityEvent).all()
        types = {e.event_type for e in events}
        assert "login_failed" in types
        assert "login_success" in types
        assert "password_changed" in types
        blob = " ".join(f"{e.event_type} {e.detail or ''}" for e in events)
        for secret in (TEST_PW, "Logged-Passw0rd-31!", "pbkdf2_sha256"):
            assert secret not in blob  # no passwords, hashes or tokens in the log
        assert all(e.ip_address for e in events)  # effective client IP recorded
    finally:
        db.close()


# ------------------------------------------------------------ single-login mandate

def test_no_registration_or_invite_endpoints_on_auth_router(client):
    """The auth router exposes login, logout and change-password only —
    no registration, signup or invitation endpoints exist."""
    paths = {r.path for r in client.app.routes}
    assert paths & {"/auth/login", "/auth/logout", "/auth/change-password"}
    for forbidden in ("/auth/register", "/auth/signup", "/auth/invite", "/auth/users"):
        assert forbidden not in paths
        assert client.post(forbidden, json={}).status_code in (401, 403, 404, 405)


def test_users_router_module_no_longer_exists():
    """The users API router was deleted in v2.8 — importing it must fail,
    which is a stronger guarantee than a 404 on one particular app."""
    with pytest.raises(ModuleNotFoundError):
        __import__("app.routers.users")


def test_username_not_changeable_via_any_auth_endpoint(client):
    csrf = login(client).json()["csrf_token"]
    # change-password accepts only current/new password fields; extra
    # fields are ignored by pydantic and the fixed username is untouched.
    client.post(
        "/auth/change-password",
        json={
            "current_password": TEST_PW,
            "new_password": "Renamed-Passw0rd-88!",
            "username": "attacker@evil.com",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert login(client, username="attacker@evil.com", password="Renamed-Passw0rd-88!").status_code == 401
    assert login(client, username="tom@vectasports", password="Renamed-Passw0rd-88!").status_code == 200


def test_user_table_retained_but_inert():
    """The users table still exists (FK integrity for historical owner_id
    data) but nothing can authenticate against it and no endpoint serves it."""
    db = SessionLocal()
    try:
        db.add(User(name="Ghost", email="ghost@example.com"))
        db.commit()
    finally:
        db.close()
    with TestClient(build_test_app()) as c:
        assert login(c, username="ghost@example.com", password=TEST_PW).status_code == 401

"""Verification matrix #7 over HTTP: the real middleware and auth endpoints on a
Starlette app (FastAPI's foundation) backed by real PostgreSQL. Business
routes are stand-ins for every protected surface (direct ID, search,
export, report, AI, import)."""
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app import config
from app.http import auth_routes, middleware
from app.services import auth_service
from tests.sql.pg import drop_db, fresh_db
from tests.sql.psql_db import PsqlDatabase

PROTECTED = [("GET", "/opportunities/00000000-0000-0000-0000-000000000001"), ("GET", "/search?q=x"),
             ("GET", "/reports/pipeline.csv"), ("POST", "/ai/extract"), ("POST", "/imports/bookings/commit"),
             ("GET", "/organisations?kind=airline")]


@pytest.fixture(scope="module")
def env():
    pg = fresh_db()
    db = PsqlDatabase(pg)
    auth_service.bootstrap_credential(db, "ops@wfc.example", "Bootstrap-Pass-2026!")
    settings = config.load({"ENVIRONMENT": "test"})

    async def ok(request):
        return JSONResponse({"ok": True, "path": request.url.path})

    async def live(request):
        return PlainTextResponse("ok")

    routes = [Route(p, e, methods=m) for p, e, m in auth_routes.build(settings, lambda: db)]
    routes += [Route("/health/live", live), Route("/opportunities/{id}", ok), Route("/search", ok),
               Route("/reports/pipeline.csv", ok), Route("/ai/extract", ok, methods=["POST"]),
               Route("/imports/bookings/commit", ok, methods=["POST"]), Route("/organisations", ok)]
    app = Starlette(routes=routes)
    middleware.install(app, settings, lambda: db)
    yield app, db
    drop_db(pg)


def login(client):
    r = client.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def test_unauthenticated_cannot_read_or_mutate_anything(env):
    app, _ = env
    c = TestClient(app)
    for method, path in PROTECTED:
        r = c.request(method, path)
        assert r.status_code == 401, (method, path)
        assert r.headers["cache-control"] == "no-store"
        assert r.json()["error"]["code"] == "unauthenticated" and r.json()["error"]["request_id"]
    assert c.get("/health/live").status_code == 200


def test_login_cookie_flags_session_and_csrf(env):
    app, _ = env
    c = TestClient(app)
    csrf = login(c)
    raw = c.cookies.get("atlas_session")
    assert raw
    set_cookie = c.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"}).headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie and "Path=/" in set_cookie
    for method, path in PROTECTED:
        if method == "GET":
            assert c.get(path).status_code == 200
    assert c.post("/ai/extract").status_code == 403                          # no CSRF header
    assert c.post("/ai/extract", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    # each login gets its own CSRF token; the latest login's token works for that session
    csrf2 = c.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"}).json()["csrf_token"]
    assert c.post("/ai/extract", headers={"X-CSRF-Token": csrf2}).status_code == 200
    # reload / second tab: /auth/session returns the SAME token, so open tabs keep working (review finding 7)
    s = c.get("/auth/session").json()
    assert s["authenticated"] and s["active_sessions"] >= 1 and s["csrf_token"] == csrf2
    assert c.get("/auth/session").json()["csrf_token"] == csrf2
    assert c.post("/imports/bookings/commit", headers={"X-CSRF-Token": csrf2}).status_code == 200
    # a token from a different session is useless here
    other = TestClient(app)
    assert c.post("/imports/bookings/commit", headers={"X-CSRF-Token": login(other)}).status_code == 403
    del csrf


def test_concurrent_sessions_logout_and_logout_all(env):
    app, _ = env
    a, b = TestClient(app), TestClient(app)
    login(a)
    tb = login(b)
    assert a.get("/search").status_code == 200 and b.get("/search").status_code == 200
    ta = a.get("/auth/session").json()["csrf_token"]
    assert a.post("/auth/logout", headers={"X-CSRF-Token": ta}).status_code == 200
    assert a.get("/search").status_code == 401 and b.get("/search").status_code == 200
    login(a)
    assert b.post("/auth/logout-all", headers={"X-CSRF-Token": tb}).status_code == 200
    assert a.get("/search").status_code == 401 and b.get("/search").status_code == 401


def test_password_change_revokes_and_new_password_works(env):
    app, _ = env
    a, b = TestClient(app), TestClient(app)
    ta = login(a)
    login(b)
    r = a.post("/auth/change-password", headers={"X-CSRF-Token": ta},
               json={"current_password": "Bootstrap-Pass-2026!", "new_password": "Changed-Pass-2026!"})
    assert r.status_code == 200
    assert a.get("/search").status_code == 401 and b.get("/search").status_code == 401
    assert a.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"}).status_code == 401
    r = a.post("/auth/login", json={"username": "ops@wfc.example", "password": "Changed-Pass-2026!"})
    assert r.status_code == 200
    # restore for the remaining tests
    assert a.post("/auth/change-password", headers={"X-CSRF-Token": r.json()["csrf_token"]},
                  json={"current_password": "Changed-Pass-2026!", "new_password": "Bootstrap-Pass-2026!"}).status_code == 200


def test_forged_and_expired_cookies_rejected(env):
    app, db = env
    c = TestClient(app)
    c.cookies.set("atlas_session", "forged")
    assert c.get("/search").status_code == 401
    login(c)
    db.pg.run("UPDATE auth_sessions SET expires_at = now() - interval '1 second'")
    assert c.get("/search").status_code == 401


def test_production_config_requires_secrets_and_https():
    with pytest.raises(config.ConfigError):
        config.load({"ENVIRONMENT": "production"})
    with pytest.raises(config.ConfigError):
        config.load({"ENVIRONMENT": "production", "DATABASE_URL": "postgresql://atlas:atlas@db/x", "LOGIN_USERNAME": "a",
                     "PUBLIC_ORIGIN": "https://atlas.example"})
    with pytest.raises(config.ConfigError):
        config.load({"ENVIRONMENT": "production", "DATABASE_URL": "postgresql://atlas:dev-only@db/x", "LOGIN_USERNAME": "a",
                     "PUBLIC_ORIGIN": "https://atlas.example"})
    s = config.load({"ENVIRONMENT": "production", "DATABASE_URL": "postgresql://wfc:" + "Prod-Secret-Value-9" + "@db/wfc", "LOGIN_USERNAME": "a",
                     "PUBLIC_ORIGIN": "https://atlas.example"})
    assert not s.docs_enabled and middleware.cookie_name(s) == "__Host-atlas_session"
    assert "Prod-Secret-Value-9" in " ".join(s.secret_values)   # used for log/error redaction


# ------------------------------------------------------------------ optional signed-proxy requirement (Netlify front end)
def _jws(secret: str, claims: dict, alg: str = "HS256") -> str:
    import base64
    import hashlib
    import hmac
    import json

    def enc(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    h, c = enc(json.dumps({"alg": alg, "typ": "JWT"}).encode()), enc(json.dumps(claims).encode())
    return f"{h}.{c}." + enc(hmac.new(secret.encode(), f"{h}.{c}".encode(), hashlib.sha256).digest())


def test_signed_proxy_requirement(env):
    import time

    from app.domain import auth_policy as ap

    _, db = env
    secret = "s" * 40
    settings = config.load({"ENVIRONMENT": "test", "PROXY_SIGNATURE_SECRET": secret})

    async def live(request):
        return PlainTextResponse("ok")

    routes = [Route(p, e, methods=m) for p, e, m in auth_routes.build(settings, lambda: db)] + [Route("/health/live", live)]
    app = Starlette(routes=routes)
    middleware.install(app, settings, lambda: db)
    c = TestClient(app)
    good = _jws(secret, {"iss": "netlify", "exp": time.time() + 60, "deploy_context": "production"})
    assert c.get("/health/live").status_code == 200                                     # host health check needs no signature
    assert c.post("/auth/login", json={"username": "ops@wfc.example", "password": "x"}).status_code == 403
    for bad in (_jws("w" * 40, {"iss": "netlify", "exp": time.time() + 60}), _jws(secret, {"iss": "netlify", "exp": time.time() - 1}),
                _jws(secret, {"iss": "someone", "exp": time.time() + 60}), _jws(secret, {"iss": "netlify", "exp": time.time() + 60}, alg="none"),
                "not.a.token", ""):
        assert c.post("/auth/login", json={"username": "ops@wfc.example", "password": "x"}, headers={"x-nf-sign": bad}).status_code == 403
    r = c.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"}, headers={"x-nf-sign": good})
    assert r.status_code == 200
    assert ap.proxy_signature_ok(good, secret, time.time()) and not ap.proxy_signature_ok(good, secret, time.time() + 120)
    with pytest.raises(config.ConfigError):
        config.load({"ENVIRONMENT": "test", "PROXY_SIGNATURE_SECRET": "short"})
    assert secret in settings.secret_values and secret not in repr(settings)

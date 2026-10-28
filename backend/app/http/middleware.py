"""HTTP security layer (pure Starlette, so it runs under FastAPI unchanged).

Order (outermost first): RequestContext -> SecurityHeaders -> ProxySignature (optional) -> RateLimit -> AuthGate.

- Every response carries `Cache-Control: no-store` and a strict CSP: no
  authenticated data is cacheable by browsers, proxies or service workers.
- AuthGate: everything except liveness/readiness and login requires a valid
  server-side session, including the API docs when they are enabled. That covers direct IDs,
  search, exports, reports, AI endpoints and imports. Mutating requests also
  need the CSRF header.
- One client-IP rule (`auth_policy.client_ip`) is used for rate limiting,
  throttling and audit.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import Settings
from ..domain import auth_policy as ap
from ..repo.db import Database
from ..services import auth_service
from ..services.audit import RequestMeta

PUBLIC_PATHS = {"/health/live", "/health/ready", "/auth/login"}
CSRF_EXEMPT = {"/auth/login"}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def cookie_name(settings: Settings) -> str:
    # __Host- prefix: browser enforces Secure, Path=/ and no Domain attribute.
    return "__Host-atlas_session" if settings.production or settings.environment == "staging" else "atlas_session"


def error(status: int, code: str, detail: str, request_id: str | None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "detail": detail, "request_id": request_id}}, status_code=status)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id", "")
        if not (8 <= len(rid) <= 64 and rid.replace("-", "").isalnum()):
            rid = uuid.uuid4().hex
        peer = request.client.host if request.client else None
        request.state.request_id = rid
        request.state.meta = RequestMeta(ip=ap.client_ip(peer, request.headers.get("x-forwarded-for"), self.settings.trusted_proxy_hops),
                                         user_agent=request.headers.get("user-agent"), request_id=rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.hsts = settings.production or settings.environment == "staging"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        if self.hsts:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-instance sliding window: protects against runaway clients. Login
    brute force is handled by the durable, cross-instance throttle in
    auth_service, not by this limiter."""

    def __init__(self, app, per_minute: int = 300):
        super().__init__(app)
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/health/"):
            return await call_next(request)
        ip = request.state.meta.ip
        now = time.monotonic()
        q = self.hits[ip]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return error(429, "rate_limited", "Too many requests. Try again shortly.", request.state.request_id)
        q.append(now)
        return await call_next(request)


class ProxySignatureMiddleware(BaseHTTPMiddleware):
    """When PROXY_SIGNATURE_SECRET is set, only requests signed by the front end's proxy are answered (liveness excepted,
    so the host's health check still works). Off when the secret is unset (same-host deployments behind `web`)."""

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.secret = settings.proxy_signature_secret

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.secret and request.url.path != "/health/live" and \
                not ap.proxy_signature_ok(request.headers.get("x-nf-sign"), self.secret, time.time()):
            return error(403, "proxy_signature", "Requests must come through the ATLAS web front end.", request.state.request_id)
        return await call_next(request)


class AuthGateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings, db_factory: Callable[[], Database]):
        super().__init__(app)
        self.settings = settings
        self.db_factory = db_factory
        self.cookie = cookie_name(settings)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        # API docs, when enabled at all, are served only to an authenticated session.
        if request.method == "OPTIONS" or path in PUBLIC_PATHS:
            return await call_next(request)
        db = self.db_factory()
        session = auth_service.validate(db, request.cookies.get(self.cookie))
        if session is None:
            return error(401, "unauthenticated", "Not signed in or session expired.", request.state.request_id)
        if request.method in MUTATING and path not in CSRF_EXEMPT:
            if not ap.csrf_ok(request.headers.get("x-csrf-token"), request.cookies.get(self.cookie)):
                return error(403, "csrf", "Missing or invalid CSRF token.", request.state.request_id)
        request.state.session = session
        request.state.meta = request.state.meta.with_session(session.session_ref)
        return await call_next(request)


def install(app, settings: Settings, db_factory: Callable[[], Database]) -> None:
    """Starlette adds middleware outermost-last."""
    app.add_middleware(AuthGateMiddleware, settings=settings, db_factory=db_factory)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ProxySignatureMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware, settings=settings)

"""Authentication endpoints, written against Starlette's Request/Response so
they run identically under FastAPI (registered with `add_api_route`) and
under the plain-Starlette test app.

POST /auth/login           {username, password} -> sets HttpOnly cookie, returns {csrf_token}
GET  /auth/session         -> {authenticated, csrf_token (rotated), expires_at, active_sessions}
POST /auth/logout          -> revokes this session
POST /auth/logout-all      -> revokes every session for the shared account
POST /auth/change-password {current_password, new_password} -> revokes every session
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import RELEASE, Settings
from ..domain import auth_policy as ap
from ..repo.db import Database
from ..services import auth_service
from .middleware import cookie_name, error


async def _json(request: Request) -> dict:
    try:
        body = await request.body()
        data = json.loads(body or b"{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def build(settings: Settings, db_factory: Callable[[], Database]):
    cname = cookie_name(settings)
    secure = settings.production or settings.environment == "staging"

    def set_cookie(resp: Response, token: str) -> None:
        resp.set_cookie(cname, token, httponly=True, secure=secure, samesite="lax", path="/",
                        max_age=int(ap.SESSION_LIFETIME.total_seconds()))

    def clear_cookie(resp: Response) -> None:
        resp.delete_cookie(cname, path="/", secure=secure, httponly=True, samesite="lax")

    async def login(request: Request) -> Response:
        data = await _json(request)
        username, password = str(data.get("username", "")), str(data.get("password", ""))
        if not username or not password or len(password) > 512:
            return error(400, "invalid_request", "Username and password are required.", request.state.request_id)
        try:
            result = await asyncio.to_thread(auth_service.login, db_factory(), username, password, request.state.meta)
        except auth_service.AuthError as exc:
            return error(exc.status, "login_failed" if exc.status == 401 else "locked_out", exc.detail, request.state.request_id)
        resp = JSONResponse({"csrf_token": result.csrf_token, "expires_at": result.expires_at.isoformat()})
        set_cookie(resp, result.raw_token)
        return resp

    async def session(request: Request) -> Response:
        db = db_factory()
        s = request.state.session
        csrf = ap.derive_csrf(request.cookies.get(cname) or "")  # same token in every tab; no rotation
        return JSONResponse({"authenticated": True, "csrf_token": csrf, "expires_at": s.expires_at.isoformat(),
                             "active_sessions": auth_service.active_session_count(db),
                             "customer": settings.customer_name, "release": RELEASE,
                             "reporting_timezone": settings.reporting_timezone})

    async def logout(request: Request) -> Response:
        auth_service.logout(db_factory(), request.cookies.get(cname), request.state.meta)
        resp = JSONResponse({"ok": True})
        clear_cookie(resp)
        return resp

    async def logout_all(request: Request) -> Response:
        auth_service.logout_all(db_factory(), request.state.meta)
        resp = JSONResponse({"ok": True, "detail": "All sessions for the shared account have been signed out."})
        clear_cookie(resp)
        return resp

    async def change_password(request: Request) -> Response:
        data = await _json(request)
        try:
            await asyncio.to_thread(auth_service.change_password, db_factory(), str(data.get("current_password", "")),
                                    str(data.get("new_password", "")), request.state.meta)
        except auth_service.AuthError as exc:
            return error(exc.status, "password_change_failed", exc.detail, request.state.request_id)
        resp = JSONResponse({"ok": True, "detail": "Password changed. Every session has been signed out."})
        clear_cookie(resp)
        return resp

    return [
        ("/auth/login", login, ["POST"]),
        ("/auth/session", session, ["GET"]),
        ("/auth/logout", logout, ["POST"]),
        ("/auth/logout-all", logout_all, ["POST"]),
        ("/auth/change-password", change_password, ["POST"]),
    ]

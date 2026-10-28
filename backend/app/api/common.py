"""Shared helpers for API routers: pagination, insight metadata, errors."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Query, Request

from ..repo.db import Database

MAX_LIMIT = 200


def db_of(request: Request) -> Database:
    return request.app.state.db_factory()


def meta_of(request: Request):
    return request.state.meta


class Paging:
    def __init__(self, limit: int = Query(50, ge=1, le=MAX_LIMIT), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset


def page(rows: list[dict[str, Any]], paging: Paging, insight: dict[str, Any] | None = None) -> dict[str, Any]:
    total = int(rows[0].pop("total")) if rows and "total" in rows[0] else 0
    for r in rows[1:]:
        r.pop("total", None)
    return {"items": rows, "total": total, "limit": paging.limit, "offset": paging.offset, "insight": insight}


def insight(db: Database, *, scope: str, period: str | None, datasets: list[str], gaps: list[str] | None = None) -> dict[str, Any]:
    """Every insight states its period, scope, last refresh, evidence sources
    and gaps. A dataset whose source has never been loaded is `not_connected`,
    never shown as zero."""
    health = {r["name"]: r for r in db.all("source_health")}
    sources = []
    for d in datasets:
        r = health.get(f"Import: {d}")
        if r is None:
            sources.append({"dataset": d, "status": "not_connected", "last_success_at": None})
        else:
            stale = False
            if r["last_success_at"] and r["freshness_sla_hours"]:
                age_h = (datetime.now(timezone.utc) - r["last_success_at"]).total_seconds() / 3600
                stale = age_h > r["freshness_sla_hours"]
            sources.append({"dataset": d, "status": "stale" if stale else "loaded", "last_success_at": r["last_success_at"]})
    all_gaps = list(gaps or [])
    all_gaps += [f"{s['dataset']}: not connected" for s in sources if s["status"] == "not_connected"]
    return {"scope": scope, "period": period, "generated_at": datetime.now(timezone.utc).isoformat(), "sources": sources, "gaps": all_gaps}


def not_found(what: str) -> HTTPException:
    return HTTPException(404, f"{what} not found")


# ---------------------------------------------------------------- exact JSON
# FastAPI's default encoder turns Decimal into a binary float. Money and
# weights must stay exact, so every business route returns through `exact`:
# Decimal -> string, dates/datetimes -> ISO 8601.
import functools  # noqa: E402
import inspect  # noqa: E402
import json as _json  # noqa: E402
from dataclasses import asdict, is_dataclass  # noqa: E402
from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

from fastapi.responses import JSONResponse, Response  # noqa: E402


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


class ExactJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return _json.dumps(content, default=_default, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def exact(fn):
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def awrapper(*a, **k):
            r = await fn(*a, **k)
            return r if isinstance(r, Response) else ExactJSONResponse(r)
        return awrapper

    @functools.wraps(fn)
    def wrapper(*a, **k):
        r = fn(*a, **k)
        return r if isinstance(r, Response) else ExactJSONResponse(r)
    return wrapper

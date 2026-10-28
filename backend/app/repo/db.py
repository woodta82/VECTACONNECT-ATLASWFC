"""Database access by named statement.

Services depend on the small `Database` protocol, not on a driver. The
production implementation (`SQLAlchemyDatabase`) runs the statements in
`queries.Q` through SQLAlchemy Core on psycopg 3. Rows are returned as
plain dicts with UUIDs as strings, so service code is driver-independent.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator, Protocol

from .queries import Q


class Database(Protocol):
    def all(self, name: str, /, **params: Any) -> list[dict[str, Any]]: ...
    def one(self, name: str, /, **params: Any) -> dict[str, Any] | None: ...
    def scalar(self, name: str, /, **params: Any) -> Any: ...
    def run(self, name: str, /, **params: Any) -> int: ...
    def transaction(self) -> Any: ...


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    raise TypeError(f"not JSON serialisable: {type(v).__name__}")


def to_json(v: Any) -> str:
    return json.dumps(v, default=_jsonable, sort_keys=True)


def _norm_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in row.items()}


class SQLAlchemyDatabase:
    """Production implementation. A `transaction()` block shares one
    connection; outside a block each call runs in its own transaction."""

    def __init__(self, url: str, *, _conn: Any = None, _engine: Any = None):
        if _engine is None:
            from sqlalchemy import create_engine

            # Sessions run in UTC so every timestamp the application sees is UTC;
            # the reporting time zone is applied only for display.
            _engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=5, future=True,
                                    connect_args={"options": "-c timezone=UTC"})
        self._engine = _engine
        self._conn = _conn

    def _exec(self, name: str, params: dict[str, Any]):
        from sqlalchemy import text

        stmt = text(Q[name])
        params = {k: (to_json(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
        if self._conn is not None:
            return self._conn.execute(stmt, params)
        with self._engine.begin() as conn:
            res = conn.execute(stmt, params)
            rows = [dict(r._mapping) for r in res] if res.returns_rows else None
            return _Buffered(rows, res.rowcount)

    def all(self, name: str, /, **params: Any) -> list[dict[str, Any]]:
        res = self._exec(name, params)
        if isinstance(res, _Buffered):
            return [_norm_row(r) for r in (res.rows or [])]
        if not res.returns_rows:
            return []
        return [_norm_row(dict(r._mapping)) for r in res]

    def one(self, name: str, /, **params: Any) -> dict[str, Any] | None:
        rows = self.all(name, **params)
        return rows[0] if rows else None

    def scalar(self, name: str, /, **params: Any) -> Any:
        row = self.one(name, **params)
        return None if row is None else next(iter(row.values()))

    def run(self, name: str, /, **params: Any) -> int:
        res = self._exec(name, params)
        return res.rowcount if res.rowcount is not None else 0

    @contextmanager
    def transaction(self) -> Iterator["SQLAlchemyDatabase"]:
        if self._conn is not None:  # nested: reuse the outer transaction
            yield self
            return
        with self._engine.begin() as conn:
            yield SQLAlchemyDatabase("", _conn=conn, _engine=self._engine)

    def ping(self) -> bool:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            return conn.execute(text("SELECT 1")).scalar() == 1


class _Buffered:
    def __init__(self, rows: list[dict[str, Any]] | None, rowcount: int):
        self.rows = rows
        self.rowcount = rowcount

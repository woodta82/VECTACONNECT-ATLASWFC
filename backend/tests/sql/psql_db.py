"""Test implementation of `app.repo.db.Database` over the psql client.

TEST USE ONLY: parameters are rendered as quoted literals (the production
adapter uses bound parameters). Each call is its own transaction;
`transaction()` is a no-op grouping here, so atomicity is NOT exercised by
these tests (it is covered by the PostgreSQL concurrency tests and by the
SQLAlchemy adapter's design).
"""
from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.repo.db import to_json
from app.repo.queries import Q
from tests.sql.pg import PG
from tests.sql.test_pg_queries import PARAM

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def literal(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, float):
        raise TypeError("floats are not allowed in parameters; use Decimal")
    if isinstance(v, (datetime, date)):
        v = v.isoformat()
    if isinstance(v, uuid.UUID):
        v = str(v)
    if isinstance(v, (dict, list)):
        v = to_json(v)
    if isinstance(v, (list, tuple)):
        raise TypeError("arrays must be passed as PostgreSQL array literal strings")
    s = str(v).replace("'", "''")
    return f"'{s}'"


def _convert(v: Any) -> Any:
    if isinstance(v, str):
        if _TS.match(v):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        if _DATE.match(v):
            return date.fromisoformat(v)
    return v


class PsqlDatabase:
    def __init__(self, pg: PG):
        self.pg = pg

    def _sql(self, name: str, params: dict[str, Any]) -> str:
        sql = Q[name]

        def repl(m):
            key = m.group(1)
            if key not in params:
                raise KeyError(f"{name}: missing parameter {key}")
            return literal(params[key])
        return PARAM.sub(repl, sql)

    def all(self, name: str, /, **params: Any) -> list[dict[str, Any]]:
        inner = self._sql(name, params)
        wrapped = f"WITH t AS ({inner}) SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM t"
        res = self.pg.run(wrapped, check=False)
        if res.returncode != 0:
            # statements without rows (UPDATE ... without RETURNING) cannot be wrapped
            if "does not have a RETURNING clause" in res.stderr or "syntax error" in res.stderr:
                self.pg.run(inner)
                return []
            raise RuntimeError(f"{name}: {res.stderr.strip()}")
        rows = json.loads(res.stdout.strip() or "[]", parse_float=Decimal)
        return [{k: _convert(v) for k, v in r.items()} for r in rows]

    def one(self, name: str, /, **params: Any) -> dict[str, Any] | None:
        rows = self.all(name, **params)
        return rows[0] if rows else None

    def scalar(self, name: str, /, **params: Any) -> Any:
        row = self.one(name, **params)
        return None if row is None else next(iter(row.values()))

    def run(self, name: str, /, **params: Any) -> int:
        inner = self._sql(name, params)
        res = self.pg.run(inner, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"{name}: {res.stderr.strip()}")
        return 1

    @contextmanager
    def transaction(self):
        yield self

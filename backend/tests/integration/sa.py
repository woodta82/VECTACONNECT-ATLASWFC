"""Real PostgreSQL through the PRODUCTION adapter (SQLAlchemy Core + psycopg 3).

Each fixture database is built from every migration SQL file in order
(tests/sql/pg.py) on a real PostgreSQL 16 server. Skipped, and reported as
skipped, when WFC_TEST_PG is unset.
"""
from __future__ import annotations

import pytest

from tests.sql.pg import CONN, PG, drop_db, fresh_db


def url_for(pg: PG) -> str:
    parts = dict(p.split("=", 1) for p in CONN.split())  # type: ignore[union-attr]
    return f"postgresql+psycopg://{parts.get('user', 'atlas')}@{parts.get('host', '127.0.0.1')}:{parts.get('port', '5432')}/{pg.dbname}"


@pytest.fixture()
def sadb():
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg")
    from app.repo.db import SQLAlchemyDatabase

    pg = fresh_db()
    db = SQLAlchemyDatabase(url_for(pg))
    db.pg = pg  # type: ignore[attr-defined]
    try:
        yield db
    finally:
        db._engine.dispose()
        drop_db(pg)

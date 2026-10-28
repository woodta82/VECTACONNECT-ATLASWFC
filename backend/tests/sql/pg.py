"""Minimal PostgreSQL test harness using the `psql` client.

Used so that schema, constraint and concurrency guarantees are tested on a
REAL PostgreSQL server, independently of the Python driver. Configure with
WFC_TEST_PG="host=127.0.0.1 port=5433 user=atlas"; tests are skipped (and
reported as skipped, not passed) when it is unset.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

_SQL_DIR = Path(__file__).resolve().parents[2] / "migrations" / "sql"
SCHEMA = _SQL_DIR / "wfc_0001_schema.sql"
# Every revision in order: the clean-server schema the application expects.
SCHEMA_FILES = [SCHEMA, _SQL_DIR / "wfc_0002_directive.sql", _SQL_DIR / "wfc_0002_geography_seed.sql", _SQL_DIR / "wfc_0003_review.sql", _SQL_DIR / "wfc_0004_amendments.sql",
                _SQL_DIR / "wfc_0004_legacy_deadlines.sql", _SQL_DIR / "wfc_0005_validation_version.sql", _SQL_DIR / "wfc_0006_revalidation_v3.sql", _SQL_DIR / "wfc_0007_relevance_v4.sql", _SQL_DIR / "wfc_0008_meaning_relevance_v5.sql",
                _SQL_DIR / "wfc_0009_status_freshness_v6.sql",
                _SQL_DIR / "wfc_0010_status_chronology_v7.sql"]
CONN = os.environ.get("WFC_TEST_PG")


def require_pg():
    if not CONN or not shutil.which("psql"):
        pytest.skip("WFC_TEST_PG not set or psql missing: PostgreSQL tests not run")


def _base_args(dbname: str) -> list[str]:
    parts = dict(p.split("=", 1) for p in CONN.split())  # type: ignore[union-attr]
    args = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-d", dbname]
    if "host" in parts:
        args += ["-h", parts["host"]]
    if "port" in parts:
        args += ["-p", parts["port"]]
    if "user" in parts:
        args += ["-U", parts["user"]]
    return args


class PG:
    def __init__(self, dbname: str):
        self.dbname = dbname

    def run(self, sql: str, check: bool = True) -> subprocess.CompletedProcess:
        res = subprocess.run(_base_args(self.dbname) + ["-c", sql], capture_output=True, text=True)
        if check and res.returncode != 0:
            raise AssertionError(f"psql failed: {res.stderr.strip()}")
        return res

    def val(self, sql: str) -> str:
        return self.run(sql).stdout.strip()

    def rows(self, sql: str) -> list[list[str]]:
        out = self.run(sql).stdout.strip()
        return [line.split("|") for line in out.splitlines()] if out else []

    def fails(self, sql: str) -> str:
        res = self.run(sql, check=False)
        assert res.returncode != 0, f"expected failure but succeeded: {sql}"
        return res.stderr

    def parallel(self, sqls: list[str]) -> list[subprocess.CompletedProcess]:
        procs = [subprocess.Popen(_base_args(self.dbname) + ["-c", s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for s in sqls]
        out = []
        for p in procs:
            stdout, stderr = p.communicate(timeout=120)
            out.append(subprocess.CompletedProcess(p.args, p.returncode, stdout, stderr))
        return out


def fresh_db() -> PG:
    require_pg()
    name = f"wfc_test_{uuid.uuid4().hex[:10]}"
    admin = PG("postgres")
    admin.run(f"CREATE DATABASE {name}")
    db = PG(name)
    for f in SCHEMA_FILES:
        res = subprocess.run(_base_args(name) + ["-1", "-f", str(f)], capture_output=True, text=True)
        if res.returncode != 0:
            raise AssertionError(f"{f.name} failed to apply: {res.stderr}")
    return db


def drop_db(db: PG) -> None:
    PG("postgres").run(f"DROP DATABASE IF EXISTS {db.dbname} WITH (FORCE)", check=False)

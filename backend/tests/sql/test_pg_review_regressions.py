"""Database-level regression tests for the independent review findings that
concern the durable job queue (r6, r13). Real PostgreSQL via the psql adapter.

The evidence/qualification and import regressions (r1-r5, r8, r10, writers)
run through the production adapter in tests/integration/test_evidence_regressions.py."""
import pytest

from tests.sql.pg import drop_db, fresh_db
from tests.sql.psql_db import PsqlDatabase


@pytest.fixture()
def db():
    pg = fresh_db()
    yield PsqlDatabase(pg)
    drop_db(pg)


def test_r6_cancelled_job_is_not_resurrected(db):
    db.pg.run("DELETE FROM schedules; INSERT INTO jobs (job_type, execution_key) VALUES ('import','c1')")
    job = db.one("job_claim", worker="w1", lease=300)
    db.run("job_cancel", job=job["id"])
    assert db.scalar("job_fail", job=job["id"], worker="w1", backoff=30, error="boom", checkpoint=None) is None
    assert db.scalar("job_succeed", job=job["id"], worker="w1", checkpoint=None) is None
    assert db.pg.val("SELECT status FROM jobs WHERE execution_key='c1'") == "cancelled"


def test_r13_job_crashing_its_worker_is_dead_lettered(db):
    db.pg.run("DELETE FROM schedules; INSERT INTO jobs (job_type, execution_key, max_attempts) VALUES ('import','crash', 2)")
    for _ in range(2):
        db.one("job_claim", worker="dies", lease=300)
        db.pg.run("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE execution_key='crash'")
    assert db.one("job_claim", worker="w", lease=300) is None
    assert db.pg.val("SELECT status FROM jobs WHERE execution_key='crash'") == "dead"

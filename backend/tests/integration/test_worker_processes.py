"""Directive §13: worker-restart and concurrent-budget tests at PROCESS level.

Real worker processes (`python -m app.worker_main`) and real reservation calls
from separate OS processes against PostgreSQL 16. The fixture site and the
SIMULATED AI provider run in this test process; the workers reach them over
HTTP exactly as they would a real source and provider.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import discovery as dsc
from tests.fixtures.servers import FakeAIProvider, FixtureSite
from tests.integration.sa import url_for
from tests.integration.test_discovery_pipeline import add_sources

BACKEND = Path(__file__).resolve().parents[2]


def _env(db, site, ai, lease: int) -> dict[str, str]:
    return dict(os.environ, DATABASE_URL=url_for(db.pg), ENVIRONMENT="test", ANTHROPIC_API_KEY="test-key-not-real",
                AI_MODEL="fixture-model", AI_PRICE_INPUT_PER_MTOK="3", AI_PRICE_OUTPUT_PER_MTOK="15", AI_API_BASE_URL=ai.base,
                RETRIEVAL_ALLOW_PRIVATE_HOSTS=f"127.0.0.1:{site.port}", WORKER_LEASE_SECONDS=str(lease), PYTHONPATH=str(BACKEND))


def _worker(env: dict[str, str], log: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "app.worker_main"], cwd=BACKEND, env=env, stdout=open(log, "w"),  # noqa: SIM115
                            stderr=subprocess.STDOUT, start_new_session=True)


def _wait(pred, timeout: float, what: str):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {what}")


def test_worker_killed_mid_run_is_reclaimed_without_duplicates_or_lost_spend(sadb, tmp_path):
    db = sadb
    with FixtureSite() as site, FakeAIProvider(delay=1.0) as ai:
        db.run("flag_set", key="ai_kill_switch", value="false")
        db.run("budget_set", cap="10.00", warn="8.00", per_run="1.00")
        add_sources(db, site)
        sid = dsc.create_search(db, dsc.SearchSpec(geo_mode="country", countries=["KE"], regions=[], modules=[]))
        from app import config
        settings = config.load(_env(db, site, ai, 4))
        run = dsc.start_run(db, settings, search_id=sid)
        job = db.pg.val(f"SELECT job_id FROM discovery_runs WHERE id='{run['run_id']}'")

        w1 = _worker(_env(db, site, ai, 4), tmp_path / "worker1.log")
        try:
            # Stop the worker the moment an AI call is in flight (a reservation is open).
            _wait(lambda: db.pg.val(f"SELECT count(*) FROM budget_reservations WHERE job_id='{job}' AND status='reserved'") != "0",
                  60, "an open reservation")
        finally:
            os.killpg(w1.pid, signal.SIGKILL)
            w1.wait(10)
        assert db.pg.val(f"SELECT status FROM jobs WHERE id='{job}'") == "running"
        open_before = db.pg.rows(f"SELECT id, reserved_usd FROM budget_reservations WHERE job_id='{job}' AND status='reserved'")
        assert open_before

        w2 = _worker(_env(db, site, ai, 4), tmp_path / "worker2.log")
        try:
            _wait(lambda: db.pg.val(f"SELECT status FROM discovery_runs WHERE id='{run['run_id']}'") not in ("queued", "running"),
                  120, "the reclaimed run to finish")
        finally:
            os.killpg(w2.pid, signal.SIGTERM)
            w2.wait(20)

        assert db.pg.val(f"SELECT status FROM jobs WHERE id='{job}'") == "succeeded"
        assert db.pg.rows(f"SELECT attempt, outcome FROM job_attempts WHERE job_id='{job}' ORDER BY attempt") == [
            ["1", "lease_expired"], ["2", "succeeded"]]
        # The crashed attempt's reservation is booked at the reserved amount (the provider may have charged), never lost.
        for rid, amount in open_before:
            assert db.pg.rows(f"SELECT status, actual_usd FROM budget_reservations WHERE id='{rid}'") == [["settled", amount]]
        assert db.pg.val(f"SELECT count(*) FROM budget_reservations WHERE job_id='{job}' AND status='reserved'") == "0"
        # Idempotent re-run: no duplicated documents, signals or opportunities.
        assert db.pg.val("SELECT count(*) - count(DISTINCT canonical_url) FROM source_documents") == "0"
        assert db.pg.val("SELECT count(*) FROM opportunities WHERE module='airline_representation'") == "3"
        assert db.pg.val("SELECT count(*) - count(DISTINCT signal_key) FROM signals") == "0"
        assert db.pg.val(f"SELECT outcome FROM discovery_runs WHERE id='{run['run_id']}'") == "results"
        assert "settled at the reserved amount" in (tmp_path / "worker2.log").read_text()


RESERVER = """
import sys
from decimal import Decimal
from app.repo.db import SQLAlchemyDatabase
db = SQLAlchemyDatabase(sys.argv[1])
ok = 0
for _ in range(int(sys.argv[2])):
    if db.scalar("budget_reserve", job=None, amount=Decimal(sys.argv[3])) is not None:
        ok += 1
print(ok)
"""


def _reserve_in_processes(db, n_procs: int, each: int, amount: str) -> list[int]:
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    procs = [subprocess.Popen([sys.executable, "-c", RESERVER, url_for(db.pg), str(each), amount], cwd=BACKEND, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(n_procs)]
    out = []
    for p in procs:
        so, se = p.communicate(timeout=120)
        assert p.returncode == 0, se
        out.append(int(so.strip()))
    return out


def test_concurrent_reservations_from_many_processes_never_exceed_the_cap(sadb):
    db = sadb
    db.run("flag_set", key="ai_kill_switch", value="false")
    db.run("budget_set", cap="10.00", warn="8.00", per_run="1.00")
    # 8 processes x 10 attempts x 0.40 USD = 32 USD requested against a 10 USD cap.
    granted = _reserve_in_processes(db, 8, 10, "0.40")
    assert sum(granted) == 25, granted                                     # exactly floor(10 / 0.40), no overshoot
    assert Decimal(db.pg.val("SELECT sum(reserved_usd) FROM budget_reservations WHERE status='reserved'")) == Decimal("10.00")
    # Over the per-run cap: refused regardless of headroom.
    db.pg.run("UPDATE budget_reservations SET status='released'")
    assert sum(_reserve_in_processes(db, 4, 3, "1.50")) == 0
    # Kill switch: every concurrent reservation refused.
    db.run("flag_set", key="ai_kill_switch", value="true")
    assert sum(_reserve_in_processes(db, 6, 5, "0.10")) == 0
    assert db.pg.val("SELECT count(*) FROM budget_reservations WHERE status='reserved'") == "0"


@pytest.mark.parametrize("workers", [3])
def test_several_worker_processes_run_each_scheduled_slot_once(sadb, tmp_path, workers):
    db = sadb
    with FixtureSite() as site, FakeAIProvider() as ai:
        db.run("flag_set", key="ai_kill_switch", value="false")
        db.run("budget_set", cap="10.00", warn="8.00", per_run="1.00")
        add_sources(db, site)
        sid = dsc.create_search(db, dsc.SearchSpec(geo_mode="country", countries=["KE"], regions=[], modules=[]))
        db.pg.run("INSERT INTO schedules (job_type, scope_search_id, interval_minutes, timezone, enabled, next_run_at, name) "
                  f"VALUES ('discovery_search', '{sid}', 60, 'Asia/Dubai', true, now() - interval '1 minute', 'every hour')")
        procs = [_worker(_env(db, site, ai, 30), tmp_path / f"w{i}.log") for i in range(workers)]
        try:
            try:
                _wait(lambda: db.pg.val("SELECT count(*) FROM jobs WHERE status='succeeded' AND job_type='discovery_search'") == "1", 90, "the scheduled job")
            except AssertionError:
                logs = "\n".join((tmp_path / f"w{i}.log").read_text()[-1500:] for i in range(workers))
                raise AssertionError(f"{db.pg.rows('SELECT job_type, status, last_error FROM jobs')}\n"
                                     f"{db.pg.rows('SELECT enabled, next_run_at FROM schedules')}\n{logs}") from None
            time.sleep(3)                                                   # give the other workers a chance to double-run
        finally:
            for p in procs:
                os.killpg(p.pid, signal.SIGTERM)
            for p in procs:
                p.wait(20)
        # Every schedule (the saved search plus the installation's default ones) ran its due slot exactly once,
        # each job exactly once, across three competing worker processes.
        assert db.pg.val("SELECT count(*) FROM (SELECT schedule_id FROM jobs GROUP BY 1 HAVING count(*) > 1) d") == "0"
        assert db.pg.val("SELECT count(*) FROM jobs WHERE job_type='discovery_search'") == "1"
        assert db.pg.val("SELECT count(*) FROM (SELECT job_id FROM job_attempts GROUP BY 1 HAVING count(*) > 1) d") == "0"
        assert db.pg.val("SELECT count(*) FROM discovery_runs") == "1"
        assert len({ln.split('"msg":"worker ')[1].split()[0] for i in range(workers)
                    for ln in (tmp_path / f"w{i}.log").read_text().splitlines() if '"msg":"worker ' in ln}) == workers

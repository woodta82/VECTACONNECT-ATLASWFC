"""Service-layer workflows executed against real PostgreSQL through the
psql-backed Database (see psql_db.py for what this does and does not cover):
auth service rules, durable automation, the kill switch flag.

The evidence pipeline and import workflows moved to tests/integration (production
SQLAlchemy adapter): test_evidence_regressions.py, test_setup_imports.py."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services import auth_service as auth
from app.services import worker as wk
from app.services.audit import RequestMeta
from tests.sql.pg import drop_db, fresh_db
from tests.sql.psql_db import PsqlDatabase

UTC = timezone.utc
META = RequestMeta(ip="203.0.113.10", user_agent="pytest", request_id="req-1")


@pytest.fixture(scope="module")
def pg():
    d = fresh_db()
    yield d
    drop_db(d)


@pytest.fixture(scope="module")
def db(pg):
    pg.run("""
      INSERT INTO organisations (id, canonical_name, kind, country) VALUES
        ('00000000-0000-0000-0000-0000000000a1', 'Example Air', 'airline', 'AE');
      INSERT INTO airlines (organisation_id, iata_code) VALUES ('00000000-0000-0000-0000-0000000000a1', 'XA');
      INSERT INTO territories (id, code, name, kind) VALUES
        ('00000000-0000-0000-0000-0000000000b1', 'KE', 'Kenya', 'country'),
        ('00000000-0000-0000-0000-0000000000b2', 'UG', 'Uganda', 'country');
      INSERT INTO airports (iata_code, name, country, timezone) VALUES
        ('DXB','Dubai International','AE','Asia/Dubai'), ('NBO','Jomo Kenyatta International','KE','Africa/Nairobi');
      INSERT INTO operating_companies (name) VALUES ('WFC-UAE');
      INSERT INTO sources (id, name, family, base_url, authority, enabled) VALUES
        ('00000000-0000-0000-0000-0000000000c1', 'Example Air newsroom', 'example-air-newsroom', 'https://example-air.example', 'company_release', true),
        ('00000000-0000-0000-0000-0000000000c2', 'Cargo trade wire', 'trade-wire', 'https://tradewire.example', 'trade_press', true),
        ('00000000-0000-0000-0000-0000000000c3', 'Example Air procurement portal', 'example-air-portal', 'https://tenders.example-air.example', 'official_portal', true),
        ('00000000-0000-0000-0000-0000000000c4', 'Another newsletter', 'another-newsletter', 'https://newsletter.example', 'trade_press', true);
    """)
    return PsqlDatabase(pg)


def test_auth_service_full_cycle(db):
    no_sleep = lambda s: None  # noqa: E731
    assert auth.bootstrap_credential(db, "ops@wfc.example", "Bootstrap-Pass-2026!")
    assert not auth.bootstrap_credential(db, "ops@wfc.example", "Another-Pass-2026!")   # insert-only
    other = fresh_db()
    try:
        with pytest.raises(ValueError):
            auth.bootstrap_credential(PsqlDatabase(other), "x@y", "weak")   # weak bootstrap password refused
    finally:
        drop_db(other)
    s1 = auth.login(db, "OPS@wfc.example", "Bootstrap-Pass-2026!", META, sleep=no_sleep)
    s2 = auth.login(db, "ops@wfc.example", "Bootstrap-Pass-2026!", RequestMeta(ip="198.51.100.7"), sleep=no_sleep)
    assert auth.validate(db, s1.raw_token) and auth.validate(db, s2.raw_token)          # concurrent sessions
    assert auth.active_session_count(db) == 2
    assert auth.validate(db, "forged-token") is None
    auth.logout(db, s1.raw_token, META)
    assert auth.validate(db, s1.raw_token) is None and auth.validate(db, s2.raw_token)
    auth.logout_all(db, META)
    assert auth.validate(db, s2.raw_token) is None
    s3 = auth.login(db, "ops@wfc.example", "Bootstrap-Pass-2026!", META, sleep=no_sleep)
    with pytest.raises(auth.AuthError):
        auth.change_password(db, "wrong-current", "New-Password-2026!", META)
    auth.change_password(db, "Bootstrap-Pass-2026!", "New-Password-2026!", META)
    assert auth.validate(db, s3.raw_token) is None                                       # password change revokes
    with pytest.raises(auth.AuthError):
        auth.login(db, "ops@wfc.example", "Bootstrap-Pass-2026!", META, sleep=no_sleep)
    # IP lockout after 5 failures; another IP is only delayed.
    bad = RequestMeta(ip="192.0.2.99")
    for _ in range(4):
        with pytest.raises(auth.AuthError):
            auth.login(db, "ops@wfc.example", "nope", bad, sleep=no_sleep)
    with pytest.raises(auth.AuthError) as e:
        auth.login(db, "ops@wfc.example", "nope", bad, sleep=no_sleep)
    with pytest.raises(auth.AuthError) as e:
        auth.login(db, "ops@wfc.example", "New-Password-2026!", bad, sleep=no_sleep)
    assert e.value.status == 429
    delays = []
    assert auth.login(db, "ops@wfc.example", "New-Password-2026!", RequestMeta(ip="203.0.113.50"), sleep=delays.append)
    assert delays and delays[0] > 0
    events = [r[0] for r in db.pg.rows("SELECT event_type FROM audit_events ORDER BY id")]
    for ev in ("login_success", "logout", "logout_all_sessions", "password_change_failed", "password_changed", "login_failed", "login_locked_out"):
        assert ev in events
    assert db.pg.val("SELECT count(*) FROM audit_events WHERE detail::text ILIKE '%Pass-2026%'") == "0"   # no secrets logged
    assert db.pg.val("SELECT count(*) FROM audit_events WHERE event_type='login_success' AND session_ref IS NULL") == "0"


def test_worker_retries_backoff_dead_letter_and_budget(db):
    pg = db.pg
    pg.run("DELETE FROM jobs; UPDATE system_flags SET value='false'::jsonb WHERE key='ai_kill_switch';"
           "INSERT INTO budget_periods VALUES (date_trunc('month', now() AT TIME ZONE 'UTC')::date, 1.00, 0.80, 0.50) ON CONFLICT DO NOTHING;")
    # housekeeping schedules are seeded and enabled (deadline expiry, connector health)
    assert pg.rows("SELECT job_type, enabled FROM schedules ORDER BY job_type") == [["briefing", "t"], ["connector_health", "t"]]
    pg.run("UPDATE schedules SET enabled = false")
    pg.run("INSERT INTO schedules (id, job_type, interval_minutes, enabled) VALUES ('00000000-0000-0000-0000-0000000000d1','discovery',60,true)")
    t = datetime(2026, 10, 26, 5, 10, tzinfo=UTC)
    first = wk.scheduler_tick(db, t)
    pg.run("UPDATE schedules SET next_run_at = NULL")
    second = wk.scheduler_tick(db, t + timedelta(minutes=5))      # same slot from another scheduler
    assert len(first) == 1 and second == []
    calls = {"n": 0}

    def flaky(db_, payload, ctx):
        calls["n"] += 1
        raise RuntimeError("source timed out sk-secret-value-123")

    def spender(db_, payload, ctx):
        rid = ctx.reserve(Decimal("0.40"))
        ctx.settle(rid, Decimal("0.10"))
        return {"ok": True}

    handlers = {"discovery": flaky, "briefing": spender}
    assert wk.run_one(db, handlers, "w1", secrets=["sk-secret-value-123"]) == "queued"   # retry scheduled
    assert pg.val("SELECT run_after > now() FROM jobs") == "t"                         # backoff applied
    assert "sk-secret" not in pg.val("SELECT last_error FROM jobs")                     # secrets redacted
    pg.run("UPDATE jobs SET run_after = now(), max_attempts = 2")
    assert wk.run_one(db, handlers, "w1") == "dead"                                    # inspectable failed job
    assert pg.val("SELECT count(*) FROM job_attempts") == "2"
    for i in range(4):
        pg.run(f"INSERT INTO jobs (job_type, execution_key) VALUES ('briefing', 'b{i}')")
    results = [wk.run_one(db, handlers, "w2") for _ in range(4)]
    # cap 1.00: reservations 0.40 each, settled at 0.10 actual => all four fit (0.10*3 + 0.40 <= 1.00)
    assert results.count("succeeded") == 4
    pg.run("UPDATE system_flags SET value='true'::jsonb WHERE key='ai_kill_switch'")
    pg.run("INSERT INTO jobs (job_type, execution_key) VALUES ('briefing', 'b-kill')")
    assert wk.run_one(db, handlers, "w2") == "queued"
    assert "BudgetRefused" in pg.val("SELECT last_error FROM jobs WHERE execution_key='b-kill'")


def test_kill_switch_flag_roundtrip(db):
    """Regression: the settings route passes JSON text (not a bool) to flag_set."""
    db.run("flag_set", key="ai_kill_switch", value="false")
    assert db.scalar("flag_get", key="ai_kill_switch") is False
    db.run("flag_set", key="ai_kill_switch", value="true")
    assert db.scalar("flag_get", key="ai_kill_switch") is True
    with pytest.raises(RuntimeError):
        db.run("flag_set", key="ai_kill_switch", value=True)   # the original bug: bool -> jsonb cast is rejected

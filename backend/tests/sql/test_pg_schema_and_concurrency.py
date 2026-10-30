"""Real-PostgreSQL tests: clean install (matrix #12), constraints that encode
business rules (#4, #6, #10), durable jobs and budgets under concurrency (#9),
and the single-credential rule (#7)."""
import pytest

from tests.sql.pg import drop_db, fresh_db


@pytest.fixture(scope="module")
def db():
    d = fresh_db()
    yield d
    drop_db(d)


def seed_basic(db):
    db.run("""
        INSERT INTO airports (iata_code, name, country, timezone) VALUES
          ('DXB','Dubai International','AE','Asia/Dubai'), ('NBO','Jomo Kenyatta International','KE','Africa/Nairobi')
        ON CONFLICT DO NOTHING;
        INSERT INTO sources (name, family, authority, enabled) SELECT 'Fixture import','fixture','internal_record',true
          WHERE NOT EXISTS (SELECT 1 FROM sources WHERE name='Fixture import');
    """)


def test_clean_install_creates_everything(db):
    assert db.val("SELECT value FROM schema_meta WHERE key='revision'") == "wfc_0019"
    n = int(db.val("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))
    assert n >= 60
    assert db.val("SELECT value::text FROM system_flags WHERE key='ai_kill_switch'") == "true"
    # no sports-era tables exist in the WFC lineage
    assert db.val("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('stakeholders','users','commercial_profile')") == "0"


def test_money_columns_are_numeric_never_float(db):
    floats = db.rows("""SELECT table_name||'.'||column_name FROM information_schema.columns
                        WHERE table_schema='public' AND data_type IN ('real','double precision')""")
    assert floats == []


def test_single_shared_credential(db):
    db.run("INSERT INTO auth_credential (username, password_hash) VALUES ('ops@wfc.example', 'pbkdf2_sha256$1$aa$bb')")
    err = db.fails("INSERT INTO auth_credential (username, password_hash) VALUES ('second@wfc.example', 'pbkdf2_sha256$1$aa$bb')")
    assert "duplicate key" in err
    assert "check" in db.fails("UPDATE auth_credential SET password_hash='plaintext'").lower()


def test_directional_lanes(db):
    seed_basic(db)
    db.run("""INSERT INTO trade_lanes (origin_airport_id, destination_airport_id)
              SELECT o.id, d.id FROM airports o, airports d WHERE o.iata_code='DXB' AND d.iata_code='NBO'""")
    db.run("""INSERT INTO trade_lanes (origin_airport_id, destination_airport_id)
              SELECT o.id, d.id FROM airports o, airports d WHERE o.iata_code='NBO' AND d.iata_code='DXB'""")
    assert db.val("SELECT count(*) FROM trade_lanes") == "2"
    db.fails("""INSERT INTO trade_lanes (origin_airport_id, destination_airport_id)
                SELECT o.id, d.id FROM airports o, airports d WHERE o.iata_code='DXB' AND d.iata_code='NBO'""")
    db.fails("""INSERT INTO trade_lanes (origin_airport_id, destination_airport_id)
                SELECT id, id FROM airports WHERE iata_code='DXB'""")


def test_booking_upsert_is_idempotent_on_external_id(db):
    seed_basic(db)
    ins = """INSERT INTO bookings (source_id, external_id, booked_at, status, chargeable_weight_kg, revenue, currency)
             SELECT id, 'BK-1', now(), 'confirmed', 1000, 2500.10, 'USD' FROM sources WHERE name='Fixture import'
             ON CONFLICT (source_id, external_id) DO UPDATE SET status=EXCLUDED.status, revenue=EXCLUDED.revenue"""
    db.run(ins)
    db.run(ins)
    assert db.val("SELECT count(*) FROM bookings WHERE external_id='BK-1'") == "1"
    assert db.val("SELECT revenue FROM bookings WHERE external_id='BK-1'") == "2500.1000"
    db.fails("""INSERT INTO bookings (source_id, external_id, booked_at, status, revenue)
                SELECT id, 'BK-2', now(), 'confirmed', 10 FROM sources WHERE name='Fixture import'""")  # revenue w/o currency


def test_one_active_exception_per_key_history_preserved(db):
    db.run("INSERT INTO operational_exceptions (dedup_key, exception_type, severity, description) VALUES ('K1','reservation','high','late')")
    db.fails("INSERT INTO operational_exceptions (dedup_key, exception_type, severity, description) VALUES ('K1','reservation','high','late again')")
    db.run("UPDATE operational_exceptions SET status='resolved', resolved_at=now() WHERE dedup_key='K1'")
    db.run("INSERT INTO operational_exceptions (dedup_key, exception_type, severity, description) VALUES ('K1','reservation','low','new occurrence')")
    assert db.rows("SELECT status FROM operational_exceptions WHERE dedup_key='K1' ORDER BY opened_at") == [["resolved"], ["open"]]


def test_business_rule_constraints(db):
    # acquisition research may not enter the sales pipeline
    db.fails("INSERT INTO opportunities (module, dedup_key, title, is_acquisition_research) VALUES ('network_development','x','y',true)")
    # money without currency rejected
    db.run("INSERT INTO opportunities (module, dedup_key, title) VALUES ('airline_representation','opp-1','Tender')")
    db.fails("INSERT INTO commercial_values (opportunity_id, airline_revenue) SELECT id, 100 FROM opportunities WHERE dedup_key='opp-1'")
    # an override needs a real reason
    db.fails("""INSERT INTO qualification_overrides (opportunity_id, check_code, override_result, reason, session_ref)
                SELECT id, 'eligibility', 'pass', 'ok', 'abc' FROM opportunities WHERE dedup_key='opp-1'""")
    # one opportunity per module + dedup key
    db.fails("INSERT INTO opportunities (module, dedup_key, title) VALUES ('airline_representation','opp-1','Dup')")
    # contract exclusivity defaults to unknown, never assumed
    assert db.val("SELECT column_default FROM information_schema.columns WHERE table_name='representation_agreements' AND column_name='exclusivity'") == "'unknown'::text"


def test_duplicate_schedulers_enqueue_a_slot_once(db):
    sql = """INSERT INTO jobs (job_type, execution_key) VALUES ('discovery','schedule:S1:20261026T0500Z')
             ON CONFLICT (execution_key) DO NOTHING"""
    results = db.parallel([sql] * 12)
    assert all(r.returncode == 0 for r in results)
    assert db.val("SELECT count(*) FROM jobs WHERE execution_key='schedule:S1:20261026T0500Z'") == "1"


def test_concurrent_workers_never_claim_the_same_job(db):
    db.run("DELETE FROM jobs")
    db.run("INSERT INTO jobs (job_type, execution_key) SELECT 'import', 'k-'||g FROM generate_series(1,30) g")
    claim = "SELECT execution_key FROM claim_next_job('{w}', 300)"
    # 10 workers each try to claim 5 jobs in their own session
    scripts = ["; ".join([claim.format(w=f"w{i}")] * 5) for i in range(10)]
    results = db.parallel(scripts)
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    claimed = [line for r in results for line in r.stdout.split() if line]
    assert len(claimed) == 30 and len(set(claimed)) == 30          # every job once, none twice
    assert db.val("SELECT count(*) FROM jobs WHERE status='running'") == "30"


def test_crashed_worker_lease_is_reclaimed(db):
    db.run("DELETE FROM jobs")
    db.run("INSERT INTO jobs (job_type, execution_key) VALUES ('import','crash-1')")
    assert db.val("SELECT lease_owner FROM claim_next_job('dead-worker', 300)") == "dead-worker"
    assert db.val("SELECT count(*) FROM claim_next_job('w2', 300)") == "0"           # lease still held
    db.run("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE execution_key='crash-1'")  # simulate crash
    row = db.rows("SELECT lease_owner, attempts FROM claim_next_job('w2', 300)")
    assert row == [["w2", "2"]]


def test_budget_reservations_hold_under_concurrency(db):
    db.run("UPDATE system_flags SET value='false'::jsonb WHERE key='ai_kill_switch'")
    db.run("INSERT INTO budget_periods VALUES (date_trunc('month', now() AT TIME ZONE 'UTC')::date, 100, 80, 15) ON CONFLICT DO NOTHING")
    results = db.parallel(["SELECT reserve_budget(NULL, 10)"] * 25)
    granted = [r.stdout.strip() for r in results if r.stdout.strip()]
    assert all(r.returncode == 0 for r in results)
    assert len(granted) == 10                                    # exactly cap / amount
    assert db.val("SELECT sum(reserved_usd) FROM budget_reservations") == "100.0000"
    assert db.val("SELECT reserve_budget(NULL, 20)") == ""       # over per-run cap
    # settle one under estimate, release capacity
    db.run("UPDATE budget_reservations SET status='settled', actual_usd=4 WHERE id=(SELECT id FROM budget_reservations LIMIT 1)")
    assert db.val("SELECT reserve_budget(NULL, 6)") != ""
    assert db.val("SELECT reserve_budget(NULL, 1)") == ""        # cap reached again (90+4+6 = 100)


def test_kill_switch_blocks_all_spend(db):
    db.run("UPDATE system_flags SET value='true'::jsonb WHERE key='ai_kill_switch'")
    assert db.val("SELECT reserve_budget(NULL, 0.01)") == ""


def test_updated_at_trigger(db):
    db.run("INSERT INTO operating_companies (name) VALUES ('Group Co A')")
    before = db.val("SELECT updated_at FROM operating_companies WHERE name='Group Co A'")
    db.run("SELECT pg_sleep(0.01); UPDATE operating_companies SET country='AE' WHERE name='Group Co A'")
    assert db.val("SELECT updated_at FROM operating_companies WHERE name='Group Co A'") > before

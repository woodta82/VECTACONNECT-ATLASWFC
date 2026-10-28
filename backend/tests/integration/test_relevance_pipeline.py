"""27 Oct 2026 (second instruction), items 1-3 and 6 through the real pipeline on PostgreSQL:

- a passenger-only GSA RFP (the SpiceJet 2022 shape) is validated, ingested, kept as EXCLUDED evidence with its reason, and never
  becomes an opportunity, a country match, a briefing figure or an export row;
- an old cargo notice with an unsupported 'open' field never becomes open downstream: opportunity creation gives 'historical' with
  its basis, the briefing does not count it as live, the export states the status and basis, the run result carries it;
- the Air India Qatar shape: the defined territory is supported, the disclaimer's country is a flagged conflict, never a
  delivery geography on the record;
- the v4 re-check: records assessed under earlier rules are re-checked; withdrawn facts leave the record, the signal geography,
  stored country matches and the export; freight scope is added; originals, decisions and audit history are kept; opportunities
  are flagged; a second run changes nothing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.services import discovery as dsc
from app.services import eligibility_revalidation as er
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401
from tests.sql.pg import CONN

UTC = timezone.utc
NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)

# --- the SpiceJet shape: passenger-only, four years old, no territory, no deadline, procedural wording proposed as "open"
SJ_T = "REQUEST FOR PROPOSAL (RFP) FOR APPOINTMENT OF ONLINE/ OFFLINE PASSENGER GENERAL SALES AGENTS"
SJ_A = "SpiceJet Limited. Request for Proposal for Appointment of Offline GSAs dated September 15, 2022."
SJ_B = "Applicants shall submit a separate application for each territory they apply for."
# --- an old CARGO notice with the same status gap (no supported status, no deadline)
OLD_T = "Request for proposal for the appointment of a cargo general sales and service agent in Mozambique"
OLD_A = "Sample Airways. Reference SAW-GSSA-2022-9. Request for proposal for the appointment of a cargo GSSA in Mozambique."
OLD_B = "Applicants shall submit a separate application for each territory they apply for."
# --- the Air India Qatar shape with cargo wording so the record enters the pipeline
AI_T = "REQUEST FOR PROPOSAL FOR APPOINTMENT OF CARGO GENERAL SALES AND SERVICE AGENT (GSSA) OF EXAMPLE AIR IN QATAR"
AI_A = "Date of Issue: 15-10-2026. Reference EXA-GSSA-QA-2026-7."
AI_B = '"Territory" shall mean the geographical limits of the country i.e., Qatar.'
AI_C = "Disclaimer: this request for proposal is issued for cargo sales in Kingdom of Saudi Arabia."
AI_D = "Last date for submission of proposal 06-11-2026."


def _claims(doc: str) -> dict:
    out: list[dict] = []
    if SJ_B in doc:
        out += [{"claim_type": "gssa_tender", "stance": "supports", "quote": SJ_T,
                 "fields": {"airline": {"value": "SpiceJet", "quote": SJ_A}, "service": {"value": "GSSA", "quote": SJ_T}, "status": {"value": "open", "quote": SJ_B}}}]
    if OLD_B in doc and "SAW-GSSA-2022-9" in doc:
        out += [{"claim_type": "gssa_tender", "stance": "supports", "quote": OLD_A,
                 "fields": {"airline": {"value": "Sample Airways", "quote": OLD_A}, "country": {"value": "Mozambique", "quote": OLD_A},
                            "service": {"value": "GSSA", "quote": OLD_A}, "status": {"value": "open", "quote": OLD_B}, "tender_ref": {"value": "SAW-GSSA-2022-9", "quote": OLD_A}}}]
    if AI_B in doc:
        out += [{"claim_type": "gssa_tender", "stance": "supports", "quote": AI_T,
                 "fields": {"airline": {"value": "Example Air", "quote": AI_T}, "country": {"value": "Qatar", "quote": AI_B}, "service": {"value": "GSSA", "quote": AI_T},
                            "tender_ref": {"value": "EXA-GSSA-QA-2026-7", "quote": AI_A}, "status": {"value": "open", "quote": AI_D}, "deadline": {"value": "2026-11-06", "quote": AI_D}}},
                {"claim_type": "gssa_tender", "stance": "supports", "quote": AI_T,
                 "fields": {"airline": {"value": "Example Air", "quote": AI_T}, "country": {"value": "Saudi Arabia", "quote": AI_C}, "service": {"value": "GSSA", "quote": AI_T},
                            "tender_ref": {"value": "EXA-GSSA-QA-2026-7", "quote": AI_A}, "status": {"value": "open", "quote": AI_D}}}]
    return {"language": "en", "claims": out}


def _run(rdb, mode="countries", countries=("IN", "MZ", "QA", "SA")):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=list(countries), global_coverage=True)
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/sj", BASE + "/rfp/old", BASE + "/rfp/ai"]),
               BASE + "/rfp/sj": _page(SJ_T, f"{SJ_A} {SJ_B}", published="2022-09-15T08:00:00Z"),
               BASE + "/rfp/old": _page(OLD_T, f"{OLD_A} {OLD_B}", published="2022-11-02T08:00:00Z"),
               BASE + "/rfp/ai": _page(AI_T, f"{AI_A} {AI_B} {AI_C} {AI_D}", published="2026-10-15T08:00:00Z")})
    sid = dsc.create_search(rdb, dsc.SearchSpec(mode, list(countries), [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_claims), now=NOW)
    return started["run_id"]


def _client(rdb):  # noqa: F811
    parts = dict(p.split("=", 1) for p in CONN.split())  # type: ignore[union-attr]
    url = f"postgresql+psycopg://{parts.get('user', 'atlas')}@{parts.get('host', '127.0.0.1')}:{parts.get('port', '5432')}/{rdb.pg.dbname}"
    settings = config.load({"ENVIRONMENT": "test", "DATABASE_URL": url, "LOGIN_USERNAME": "ops@wfc.example",
                            "LOGIN_BOOTSTRAP_PASSWORD": "Bootstrap-Pass-2026!", "BUILD_ID": "pytest"})
    app = create_app(settings, lambda: rdb)
    c = TestClient(app)
    c.__enter__()
    r = c.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"})
    assert r.status_code == 200, r.text
    return c


def test_passenger_only_rfp_is_excluded_evidence_never_an_opportunity(rdb):  # noqa: F811
    run_id = _run(rdb)
    sig = rdb.pg.rows("SELECT classification, freight_scope, freight_scope_reason FROM signals WHERE title LIKE 'SpiceJet%'")
    assert sig and sig[0][0] == "excluded" and sig[0][1] == "passenger" and "passenger" in sig[0][2]
    assert rdb.pg.val("SELECT count(*) FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.title LIKE 'SpiceJet%'") == "0"
    # the exclusion is visible in the review workflow with its reason and passage
    fields = [r for r in rdb.all("review_fields", limit=100) if r["field"] == "freight_scope" and r["subject_label"] == "SpiceJet"]
    assert fields and fields[0]["support"] == "unsupported" and "excluded" in fields[0]["reason"] and fields[0]["quote"] == SJ_T
    # the unsupported 'open' field is there too, with its reason
    st = [r for r in rdb.all("review_fields", limit=100) if r["field"] == "status" and r["subject_label"] == "SpiceJet"]
    assert st and "does not state that the tender is open" in st[0]["reason"]
    # not a country match of the run (no opportunity, no supported geography) and not in the export
    results = rdb.all("run_results", run=run_id)
    assert all("SpiceJet" not in (r["title"] or "") or r["classification"] == "excluded" for r in results)
    c = _client(rdb)
    try:
        csv = c.get("/reports/opportunities.csv").text
        assert "SpiceJet" not in csv
        b = c.get("/briefing").json()
        assert not any(s["title"].startswith("SpiceJet") and s["classification"] != "excluded" for s in b["signals"])
    finally:
        c.__exit__(None, None, None)


def test_old_cargo_notice_with_unsupported_open_is_historical_everywhere_downstream(rdb):  # noqa: F811
    run_id = _run(rdb)
    opp = rdb.pg.rows("SELECT o.id, o.tender_status, o.tender_status_basis, o.freight_scope, o.deadline_utc::text FROM opportunities o "
                      "JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'SAW-GSSA-2022-9'")
    assert opp, "a supported cargo tender is still a record"
    oid, status, basis, scope, deadline = opp[0]
    assert status == "historical" and scope == "cargo" and deadline == "" and "historical" in basis and "no supported status wording" in basis
    # validation: the 'open' field is unsupported; nothing downstream turned it into open
    assert rdb.pg.val(f"SELECT support FROM claim_fields cf JOIN signal_claims sc ON sc.claim_id = cf.claim_id JOIN opportunities o ON o.signal_id = sc.signal_id "
                      f"WHERE o.id = '{oid}' AND cf.field = 'status' AND cf.superseded_at IS NULL") == "unsupported"
    checks = {r["check_code"]: r for r in rdb.all("opportunity_checks", id=str(oid))}
    assert checks["live_status"]["result"] == "review_required" and "historical" in checks["live_status"]["rationale"]
    assert checks["not_expired"]["result"] == "unknown"           # no closing date was invented
    assert checks["freight_relevance"]["result"] == "pass"
    # run result and briefing and export all carry the status, never 'open'
    res = [r for r in rdb.all("run_results", run=run_id) if r["opportunity_id"] == str(oid)]
    assert res and res[0]["tender_status"] == "historical" and res[0]["match"]["tender_status"] == "historical"
    c = _client(rdb)
    try:
        b = c.get("/briefing").json()
        rows = [p for p in b["pipeline"] if p["tender_status"] == "historical"]
        assert rows and sum(int(p["n"]) for p in rows) == 1
        # the only record counted as live is the Qatar tender whose open status and deadline ARE stated
        assert sum(int(p["n"]) for p in b["pipeline"] if p["tender_status"] in ("open", "revised")) == 1
        csv = c.get("/reports/opportunities.csv").text
        line = next(x for x in csv.splitlines() if "SAW-GSSA-2022-9" in x or "Sample Airways" in x)
        assert "historical" in line and "no supported status wording" in line and ",open," not in line
    finally:
        c.__exit__(None, None, None)


def test_air_india_shape_conflict_is_flagged_and_never_a_delivery_geography(rdb):  # noqa: F811
    run_id = _run(rdb)
    rows = rdb.pg.rows("SELECT o.id, o.tender_status FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-QA-2026-7'")
    assert len(rows) == 1, rows                                     # one record, not one per country reading
    oid = rows[0][0]
    geo = rdb.pg.rows(f"SELECT country_code, role, support FROM opportunity_geography WHERE opportunity_id = '{oid}' ORDER BY 1")
    assert ["QA", "delivery", "supported"] in geo and not any(g[0] == "SA" and g[2] == "supported" for g in geo)
    assert rdb.pg.val("SELECT geography_conflict FROM source_documents WHERE title LIKE 'REQUEST FOR PROPOSAL FOR APPOINTMENT OF CARGO%'").startswith("the notice's title")
    checks = {r["check_code"]: r for r in rdb.all("opportunity_checks", id=str(oid))}
    assert checks["geography_consistent"]["result"] == "review_required" and "Saudi Arabia" in checks["geography_consistent"]["rationale"]
    conflict = [r for r in rdb.all("review_fields", limit=100) if r["field"] == "country" and r["support"] == "review_required"]
    assert conflict and "geography conflict" in conflict[0]["reason"] and conflict[0]["quote"] == AI_C
    # the deadline read day-first as the notice's own dating establishes
    assert rdb.pg.val(f"SELECT deadline_info->>'day' FROM opportunities WHERE id = '{oid}'") == "2026-11-06"
    # the Saudi Arabia reading is not a country match of the run
    res = [r for r in rdb.all("run_results", run=run_id) if r["opportunity_id"] == str(oid)]
    assert res and all(g["country"] != "SA" for g in res[0]["match"]["geography"])


def test_v4_recheck_withdraws_facts_everywhere_and_keeps_history(rdb):  # noqa: F811
    run_id = _run(rdb)
    oid = rdb.pg.val("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-QA-2026-7'")
    sig = rdb.pg.val(f"SELECT signal_id FROM opportunities WHERE id = '{oid}'")
    # Put the record into the shape earlier rules left: Saudi Arabia 'supported' as delivery country (v3), a country match stored,
    # the SpiceJet record never scope-assessed, the old notice 'open' with status 'unknown'.
    sa_field = rdb.pg.val("SELECT id FROM claim_fields WHERE field = 'country' AND value = 'Saudi Arabia' AND superseded_at IS NULL")
    rdb.pg.run(f"UPDATE claim_fields SET support = 'supported', validation_version = 3, reason = 'Saudi Arabia stated as the place of delivery' WHERE id = '{sa_field}'")
    rdb.pg.run(f"INSERT INTO signal_geography (signal_id, country_code, role, support) VALUES ('{sig}', 'SA', 'delivery', 'supported') "
               f"ON CONFLICT (signal_id, country_code, role) DO UPDATE SET support = 'supported'")
    rdb.pg.run(f"INSERT INTO opportunity_geography (opportunity_id, country_code, role, support) VALUES ('{oid}', 'SA', 'delivery', 'supported') "
               f"ON CONFLICT (opportunity_id, country_code, role) DO UPDATE SET support = 'supported'")
    rdb.pg.run(f"UPDATE discovery_results SET match = jsonb_set(match, '{{geography}}', '[{{\"country\": \"SA\", \"name\": \"Saudi Arabia\", \"role\": \"delivery\"}}]') "
               f"WHERE signal_id = '{sig}'")
    rdb.pg.run("DELETE FROM claim_fields WHERE field = 'freight_scope'")
    rdb.pg.run("UPDATE signals SET freight_scope = NULL, classification = 'qualified_opportunity' WHERE title LIKE 'SpiceJet%'")
    rdb.pg.run("UPDATE opportunities SET tender_status = 'unknown', tender_status_basis = NULL, freight_scope = NULL")
    rdb.pg.run("UPDATE claim_fields SET validation_version = 3 WHERE field IN ('country', 'status', 'deadline')")
    # the migration queues one job
    rdb.pg.run((__import__("pathlib").Path(__file__).resolve().parents[2] / "migrations" / "sql" / "wfc_0007_relevance_v4.sql").read_text())
    assert rdb.pg.val("SELECT payload->>'to_version' FROM jobs WHERE execution_key = 'field-revalidation:wfc_0007'") == "4"
    report = er.revalidate(rdb, now=NOW, to_version=4)
    assert report["freight_scope_added"] >= 3 and report["withdrawn"] >= 1 and report["run_matches_changed"] >= 1
    # the withdrawn Saudi Arabia fact: original kept and linked, audit event with the previous verdict, no longer a record geography
    rows = rdb.pg.rows(f"SELECT support, validation_version, superseded_at IS NOT NULL, recheck_of IS NOT NULL FROM claim_fields "
                       f"WHERE claim_id = (SELECT claim_id FROM claim_fields WHERE id = '{sa_field}') AND field = 'country' AND value = 'Saudi Arabia' ORDER BY created_at")
    assert rows[0] == ["supported", "3", "t", "f"] and rows[1][0] == "review_required" and rows[1][1:] == ["4", "f", "t"]
    assert rdb.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'country_revalidated'") == "1"
    assert rdb.pg.val(f"SELECT support FROM signal_geography WHERE signal_id = '{sig}' AND country_code = 'SA'") == "unverified"
    assert rdb.pg.val(f"SELECT count(*) FROM opportunity_geography WHERE opportunity_id = '{oid}' AND country_code = 'SA' AND support = 'supported'") == "0"
    # the stored country match of the past run no longer shows Saudi Arabia; the match is re-stated from the live geography
    m = rdb.pg.val(f"SELECT match FROM discovery_results WHERE signal_id = '{sig}'")
    assert all(g["country"] != "SA" for g in json.loads(m)["geography"])
    # the opportunity is flagged and its history records the withdrawal; the reviewer decision is kept in the audit detail
    flags = json.loads(rdb.pg.val(f"SELECT review_flags::text FROM opportunities WHERE id = '{oid}'"))
    assert any(f["flag"] == "country_revalidated" and f["from"] == "supported" for f in flags)
    assert rdb.pg.val(f"SELECT count(*) FROM opportunity_status_history WHERE opportunity_id = '{oid}' AND field = 'evidence'") == "1"
    # the SpiceJet record is now excluded with a reason; the old notice is historical with a flag
    assert rdb.pg.rows("SELECT classification, freight_scope FROM signals WHERE title LIKE 'SpiceJet%'")[0] == ["excluded", "passenger"]
    old = rdb.pg.rows("SELECT o.tender_status, o.review_flags::text FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'SAW-GSSA-2022-9'")[0]
    assert old[0] == "historical" and "status_revalidated" in old[1]
    # exports and country-filtered lists follow: nothing lists Saudi Arabia as a delivery country any more
    assert rdb.pg.val("SELECT count(*) FROM opportunities o WHERE EXISTS (SELECT 1 FROM opportunity_geography g WHERE g.opportunity_id = o.id AND g.country_code = 'SA' AND g.support = 'supported')") == "0"
    # a second run changes nothing
    again = er.revalidate(rdb, now=NOW, to_version=4)
    assert again["checked"] == 0 and again["freight_scope_added"] == 0 and again["withdrawn"] == 0 and again["run_matches_changed"] == 0
    assert run_id

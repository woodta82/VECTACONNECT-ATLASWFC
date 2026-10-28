"""27 Oct 2026, third instruction, items 1, 2, 3 and 5 through the real pipeline on PostgreSQL: classification, ingestion,
qualification, briefing, country results and export, and the v5 re-check of records made under earlier rules."""
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

EXCL = "Example Air invites proposals from general sales agents for representation in Kenya. Cargo sales are excluded from this mandate."
EXCL_R = "Tender reference EXA-GSA-2027-40. Proposals are due on 12 March 2027."
RAMP = "Example Air invites tenders for ramp lighting maintenance at Mombasa airport, Kenya. Tender reference EXA-ENG-2027-3. Bids are due on 30 March 2027."
TITLE_ONLY = "Request for proposal for the appointment of a cargo GSSA in Kenya. Example Air. Reference EXA-CGO-2027-17."
CONFL = "Sample Airways invites proposals for cargo sales representation in Kenya. Reference SAW-GSA-2027-14."
CONFL_B = "Cargo sales are not part of this appointment. Proposals are due on 25 March 2027."
CARGO = "Example Air invites proposals from cargo GSSA providers in Kenya. Tender reference EXA-CGO-2027-15. Proposals must be submitted by 2 April 2027."


def _claims(doc: str) -> dict:
    out: list[dict] = []
    if "Cargo sales are excluded" in doc:
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": EXCL, "fields": {
            "airline": {"value": "Example Air", "quote": EXCL}, "country": {"value": "Kenya", "quote": EXCL}, "service": {"value": "GSSA", "quote": EXCL},
            "status": {"value": "open", "quote": EXCL_R}, "tender_ref": {"value": "EXA-GSA-2027-40", "quote": EXCL_R}, "deadline": {"value": "2027-03-12", "quote": EXCL_R}}})
    if "ramp lighting" in doc:
        out.append({"claim_type": "service_tender", "stance": "supports", "quote": RAMP, "fields": {
            "airline": {"value": "Example Air", "quote": RAMP}, "country": {"value": "Kenya", "quote": RAMP}, "service": {"value": "HANDLING", "quote": RAMP},
            "status": {"value": "open", "quote": RAMP}, "tender_ref": {"value": "EXA-ENG-2027-3", "quote": RAMP}, "deadline": {"value": "2027-03-30", "quote": RAMP}}})
    if "EXA-CGO-2027-17" in doc:
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": TITLE_ONLY, "fields": {
            "airline": {"value": "Example Air", "quote": TITLE_ONLY}, "country": {"value": "Kenya", "quote": TITLE_ONLY}, "service": {"value": "GSSA", "quote": TITLE_ONLY},
            "status": {"value": "open", "quote": TITLE_ONLY}, "tender_ref": {"value": "EXA-CGO-2027-17", "quote": TITLE_ONLY}}})
    if "not part of this appointment" in doc:
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": CONFL, "fields": {
            "airline": {"value": "Sample Airways", "quote": CONFL}, "country": {"value": "Kenya", "quote": CONFL}, "service": {"value": "GSSA", "quote": CONFL},
            "status": {"value": "open", "quote": CONFL_B}, "tender_ref": {"value": "SAW-GSA-2027-14", "quote": CONFL}, "deadline": {"value": "2027-03-25", "quote": CONFL_B}}})
    if "EXA-CGO-2027-15" in doc:
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": CARGO, "fields": {
            "airline": {"value": "Example Air", "quote": CARGO}, "country": {"value": "Kenya", "quote": CARGO}, "service": {"value": "GSSA", "quote": CARGO},
            "status": {"value": "open", "quote": CARGO}, "tender_ref": {"value": "EXA-CGO-2027-15", "quote": CARGO}, "deadline": {"value": "2027-04-02", "quote": CARGO}}})
    return {"language": "en", "claims": out}


def _run(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    pages = {"excl": ("RFP EXA-GSA-2027-40", f"{EXCL} {EXCL_R}"), "ramp": ("Tender EXA-ENG-2027-3", RAMP),
             "title": ("Request for proposal for the appointment of a cargo GSSA in Kenya", TITLE_ONLY),
             "confl": ("RFP SAW-GSA-2027-14", f"{CONFL} {CONFL_B}"), "cargo": ("RFP EXA-CGO-2027-15", CARGO)}
    web = Web({BASE + "/rfp/": _listing([BASE + f"/rfp/{k}" for k in pages])} |
              {BASE + f"/rfp/{k}": _page(t, b, published="2026-10-20T08:00:00Z") for k, (t, b) in pages.items()})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_claims), now=NOW)
    return started["run_id"]


def _client(rdb):  # noqa: F811
    parts = dict(p.split("=", 1) for p in CONN.split())  # type: ignore[union-attr]
    url = f"postgresql+psycopg://{parts.get('user', 'atlas')}@{parts.get('host', '127.0.0.1')}:{parts.get('port', '5432')}/{rdb.pg.dbname}"
    settings = config.load({"ENVIRONMENT": "test", "DATABASE_URL": url, "LOGIN_USERNAME": "ops@wfc.example",
                            "LOGIN_BOOTSTRAP_PASSWORD": "Bootstrap-Pass-2026!", "BUILD_ID": "pytest"})
    c = TestClient(create_app(settings, lambda: rdb))
    c.__enter__()
    assert c.post("/auth/login", json={"username": "ops@wfc.example", "password": "Bootstrap-Pass-2026!"}).status_code == 200
    return c


def _sig(rdb, ref):  # noqa: F811
    return rdb.pg.rows(f"SELECT classification, freight_scope, tender_state->>'status', id FROM signals WHERE tender_ref = '{ref}'")[0]


def test_classification_ingestion_and_qualification(rdb):  # noqa: F811
    _run(rdb)
    # item 1: cargo explicitly excluded -> excluded evidence, never an opportunity
    assert _sig(rdb, "EXA-GSA-2027-40")[:2] == ["excluded", "not_freight"]
    # item 2: ramp lighting -> excluded, not a freight opportunity
    assert _sig(rdb, "EXA-ENG-2027-3")[:2] == ["excluded", "not_freight"]
    assert rdb.pg.val("SELECT count(*) FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref IN ('EXA-GSA-2027-40','EXA-ENG-2027-3')") == "0"
    # conflicting cargo -> a reviewable candidate, not a qualified freight opportunity
    cls, sc, _st, sid = _sig(rdb, "SAW-GSA-2027-14")
    assert (cls, sc) == ("freight_candidate", "conflicting")
    opp = rdb.pg.val(f"SELECT id FROM opportunities WHERE signal_id = '{sid}'")
    checks = {r["check_code"]: r for r in rdb.all("opportunity_checks", id=opp)}
    assert checks["freight_relevance"]["result"] == "review_required" and rdb.pg.val(f"SELECT qualification_status FROM opportunities WHERE id = '{opp}'") == "incomplete"
    # item 3: title-only RFP -> announced, not open; not actionable, live status for review, no deadline invented
    cls, sc, st, sid = _sig(rdb, "EXA-CGO-2027-17")
    assert (cls, sc, st) == ("qualified_opportunity", "cargo", "announced")
    o = rdb.pg.rows(f"SELECT id, tender_status, tender_status_basis, deadline_utc::text FROM opportunities WHERE signal_id = '{sid}'")[0]
    assert o[1] == "announced" and o[2].startswith("announced — current status unverified") and o[3] == ""
    checks = {r["check_code"]: r for r in rdb.all("opportunity_checks", id=o[0])}
    assert checks["live_status"]["result"] == "review_required" and checks["not_expired"]["result"] == "unknown"
    # the genuine cargo tender with a stated submission instruction stays open and qualifies on freight relevance
    assert _sig(rdb, "EXA-CGO-2027-15")[:3] == ["qualified_opportunity", "cargo", "open"]


def test_briefing_country_results_lists_details_and_export_agree(rdb):  # noqa: F811
    run_id = _run(rdb)
    results = {r["title"]: r for r in rdb.all("run_results", run=run_id)}
    by_ref = {k: next(r for t, r in results.items() if k in t) for k in ("EXA-GSA-2027-40", "EXA-ENG-2027-3", "SAW-GSA-2027-14", "EXA-CGO-2027-17", "EXA-CGO-2027-15")}
    assert by_ref["EXA-GSA-2027-40"]["classification"] == "excluded" and by_ref["EXA-GSA-2027-40"]["opportunity_id"] is None
    assert by_ref["EXA-ENG-2027-3"]["classification"] == "excluded"
    assert by_ref["SAW-GSA-2027-14"]["classification"] == "freight_candidate"
    assert by_ref["EXA-CGO-2027-17"]["tender_status"] == "announced" and by_ref["EXA-CGO-2027-17"]["match"]["tender_status"] == "announced"
    c = _client(rdb)
    try:
        b = c.get("/briefing").json()
        live = sum(int(p["n"]) for p in b["pipeline"] if p["tender_status"] in ("open", "revised") and p["freight_scope"] == "cargo")
        assert live == 1                                                   # only EXA-CGO-2027-15
        assert any(p["tender_status"] == "announced" for p in b["pipeline"])
        assert not any(p["freight_scope"] in ("passenger", "not_freight") for p in b["pipeline"])
        lst = c.get("/opportunities").json()["items"]
        statuses = {o["title"]: (o["tender_status"], o["freight_scope"]) for o in lst}
        assert any(v == ("announced", "cargo") for v in statuses.values()) and any(v == ("open", "conflicting") for v in statuses.values())
        csv = c.get("/reports/opportunities.csv").text
        rows = csv.splitlines()
        assert "tender_status,tender_status_basis,freight_scope" in rows[4]
        assert any("announced" in r and "announced — current status unverified" in r for r in rows)
        assert any("freight_candidate" in r and "conflicting" in r for r in rows)
        assert not any("EXA-GSA-2027-40" in r or "ramp lighting" in r.lower() for r in rows)
        run_csv = c.get(f"/discovery/runs/{run_id}/results.csv").text
        assert "not_freight" in run_csv and "announced" in run_csv
    finally:
        c.__exit__(None, None, None)


def test_v5_recheck_of_records_made_under_earlier_rules(rdb):  # noqa: F811
    _run(rdb)
    # Put two records into the shape v4 left: the excluded-cargo mandate read as 'cargo' (an opportunity, qualified on freight),
    # the title-only RFP with a supported 'open' status and an open opportunity.
    ex_sig = _sig(rdb, "EXA-GSA-2027-40")[3]
    ex_claim = rdb.pg.val(f"SELECT claim_id FROM signal_claims WHERE signal_id = '{ex_sig}' LIMIT 1")
    rdb.pg.run(f"UPDATE claim_fields SET normalised = 'cargo', value = 'cargo', support = 'supported', reason = 'cargo relevance stated (cargo)', "
               f"validation_version = 4 WHERE claim_id = '{ex_claim}' AND field = 'freight_scope'")
    rdb.pg.run(f"UPDATE claims SET review_status = 'confirmed' WHERE id = '{ex_claim}'")
    rdb.pg.run(f"UPDATE signals SET classification = 'qualified_opportunity', freight_scope = 'cargo' WHERE id = '{ex_sig}'")
    rdb.pg.run(f"INSERT INTO opportunities (module, signal_id, dedup_key, title, freight_scope, tender_status) "
               f"SELECT module, id, signal_key, title, 'cargo', 'open' FROM signals WHERE id = '{ex_sig}'")
    t_sig = _sig(rdb, "EXA-CGO-2027-17")[3]
    t_claim = rdb.pg.val(f"SELECT claim_id FROM signal_claims WHERE signal_id = '{t_sig}' LIMIT 1")
    rdb.pg.run(f"UPDATE claim_fields SET support = 'supported', reason = '''open'' status stated in the quote', validation_version = 4 "
               f"WHERE claim_id = '{t_claim}' AND field = 'status'")
    rdb.pg.run(f"UPDATE claims SET value = value || '{{\"status\": \"open\"}}'::jsonb WHERE id = '{t_claim}'")
    rdb.pg.run(f"UPDATE opportunities SET tender_status = 'open', tender_status_basis = 'stated open' WHERE signal_id = '{t_sig}'")
    rdb.pg.run("UPDATE claim_fields SET validation_version = 4")
    rdb.pg.run((__import__("pathlib").Path(__file__).resolve().parents[2] / "migrations" / "sql" / "wfc_0008_meaning_relevance_v5.sql").read_text())
    assert rdb.pg.val("SELECT payload->>'to_version' FROM jobs WHERE execution_key = 'field-revalidation:wfc_0008'") == "5"
    report = er.revalidate(rdb, now=NOW, to_version=5)
    assert report["freight_scope_changed"] >= 1 and report["withdrawn"] >= 1 and report["excluded"] >= 1
    # excluded-cargo record: the cargo reading is superseded, linked and audited; the claim is reopened with the decision kept
    rows = rdb.pg.rows(f"SELECT normalised, validation_version, superseded_at IS NOT NULL, recheck_of IS NOT NULL FROM claim_fields "
                       f"WHERE claim_id = '{ex_claim}' AND field = 'freight_scope' ORDER BY created_at")
    assert rows[0] == ["cargo", "4", "t", "f"] and rows[-1] == ["not_freight", "5", "f", "t"]
    assert json.loads(rdb.pg.val("SELECT detail::text FROM audit_events WHERE event_type = 'freight_scope_revalidated' LIMIT 1"))["previous_review_status"] == "confirmed"
    assert rdb.pg.val(f"SELECT review_status FROM claims WHERE id = '{ex_claim}'") == "proposed"
    assert _sig(rdb, "EXA-GSA-2027-40")[:2] == ["excluded", "not_freight"]
    eo = rdb.pg.rows(f"SELECT freight_scope, qualification_status, review_flags::text FROM opportunities WHERE signal_id = '{ex_sig}'")[0]
    assert eo[0] == "not_freight" and eo[1] == "blocked" and "freight_scope_excluded" in eo[2]
    # title-only record: 'open' withdrawn (history kept), status announced, flagged
    st = rdb.pg.rows(f"SELECT support, superseded_at IS NOT NULL FROM claim_fields WHERE claim_id = '{t_claim}' AND field = 'status' ORDER BY created_at")
    assert st[0] == ["supported", "t"] and st[-1] == ["unsupported", "f"]
    to = rdb.pg.rows(f"SELECT tender_status, review_flags::text FROM opportunities WHERE signal_id = '{t_sig}'")[0]
    assert to[0] == "announced" and "status_revalidated" in to[1]
    # the briefing and export now agree: no excluded record and no announced record counted live
    c = _client(rdb)
    try:
        b = c.get("/briefing").json()
        assert sum(int(p["n"]) for p in b["pipeline"] if p["tender_status"] in ("open", "revised") and p["freight_scope"] == "cargo") == 1
        assert not any(p["freight_scope"] == "not_freight" and p["tender_status"] in ("open", "revised") for p in b["deadlines"] if "freight_scope" in p)
    finally:
        c.__exit__(None, None, None)
    again = er.revalidate(rdb, now=NOW, to_version=5)
    assert again["checked"] == 0 and again["freight_scope_changed"] == 0 and again["withdrawn"] == 0 and again["areas_changed"] == 0


def test_road_feeder_signal_area_is_rechecked(rdb):  # noqa: F811
    from app.services import ingestion as ing
    _source(rdb, "News", "listing", BASE + "/news/", country_coverage=["OM"])
    a = "Sample Airways has appointed Desert Road Logistics as its road feeder service provider for cargo between Muscat and Sohar in Oman."

    def reply(doc):
        return {"language": "en", "claims": [{"claim_type": "representation_change", "stance": "supports", "quote": a, "fields": {
            "airline": {"value": "Sample Airways", "quote": a}, "organisation": {"value": "Desert Road Logistics", "quote": a}, "country": {"value": "Oman", "quote": a}}}]}
    web = Web({BASE + "/news/": _listing([BASE + "/news/1"]), BASE + "/news/1": _page("RFS appointment", a, published="2026-10-20T08:00:00Z")})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["OM"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply), now=NOW)
    assert rdb.pg.val("SELECT module FROM signals WHERE signal_key LIKE 'rep|%'") == "trucking_gateways"
    # a record made under v4 sits in airline_representation; the v5 re-check moves it, with an audit event
    rdb.pg.run("UPDATE signals SET module = 'airline_representation' WHERE signal_key LIKE 'rep|%'")
    report = er.revalidate(rdb, now=NOW, to_version=5)
    assert report["areas_changed"] == 1 and rdb.pg.val("SELECT module FROM signals WHERE signal_key LIKE 'rep|%'") == "trucking_gateways"
    assert rdb.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'capability_area_revalidated'") == "1"
    assert ing  # imported for the stated-trucking helper used by the re-check

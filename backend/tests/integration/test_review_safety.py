"""27 Oct 2026, item 4: every unresolved material field reaches the review workflow with its reason and source
passage, and an unsupported eligibility criterion, an ambiguous geography and an uncertain deadline never become
facts in the opportunity record, its summary, exports, scores or the briefing. Real PostgreSQL, scripted extractor."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services import discovery as dsc
from app.services import eligibility_revalidation as er
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401

UTC = timezone.utc
A = "Carga Andina S.A. invites proposals for cargo handling services in Santiago. Tender reference CAN-HDL-2026-5."
B = "Proposals must be received no later than 22 December 2026 at 15:00 SCT."          # SCT: no country in the notice establishes it
C = "Bidders will be expected to show a strong track record in the region."            # no recognised requirement wording
DOC = f"{A} {B} {C}"


def _run(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["CL"])
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/5"]), BASE + "/rfp/5": _page("RFP", DOC)})

    def reply(doc: str) -> dict:
        return {"language": "en", "claims": [
            {"claim_type": "service_tender", "stance": "supports", "quote": A,
             "fields": {"organisation": {"value": "Carga Andina S.A.", "quote": A}, "country": {"value": "Chile", "quote": A},
                        "service": {"value": "HANDLING", "quote": A}, "status": {"value": "open", "quote": A}, "tender_ref": {"value": "CAN-HDL-2026-5", "quote": A},
                        "deadline": {"value": "2026-12-22T15:00:00", "quote": B}}},
            {"claim_type": "eligibility", "stance": "supports", "quote": C,
             "fields": {"organisation": {"value": "Carga Andina S.A.", "quote": A}, "tender_ref": {"value": "CAN-HDL-2026-5", "quote": A},
                        "eligibility": {"value": "a strong track record in the region", "quote": C}}}]}

    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["CL"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply), now=datetime(2026, 10, 27, tzinfo=UTC))
    return started["run_id"]


def test_unresolved_material_fields_reach_the_review_queue_with_reason_and_passage(rdb):  # noqa: F811
    _run(rdb)
    rows = rdb.all("review_fields", limit=100)
    by = {(r["field"], r["support"]): r for r in rows}
    assert ("eligibility", "review_required") in by and "could not be interpreted" in by[("eligibility", "review_required")]["reason"]
    assert ("country", "review_required") in by and "Santiago" in by[("country", "review_required")]["reason"]
    assert all(r["quote"] and r["document_id"] and r["location"] for r in rows), rows        # reason + source passage + where
    assert by[("eligibility", "review_required")]["quote"] == C and by[("country", "review_required")]["quote"] == A
    # the uncertain deadline is SUPPORTED as a local time (never an instant) and says why; it is not an unresolved field
    dl = rdb.pg.rows("SELECT support, reason FROM claim_fields WHERE field = 'deadline' AND superseded_at IS NULL")
    assert dl[0][0] == "supported" and "not established by the source" in dl[0][1]


def test_unresolved_fields_never_become_facts_in_records_exports_scores_or_briefing(rdb):  # noqa: F811
    run_id = _run(rdb)
    opp = rdb.pg.val("SELECT id FROM opportunities")
    assert opp                                                                         # the tender itself is supported
    o = rdb.one("opportunity_get", id=opp)
    # ambiguous geography: no delivery country on the record, a gap instead
    assert rdb.pg.val(f"SELECT count(*) FROM opportunity_geography WHERE opportunity_id = '{opp}' AND support = 'supported'") == "0"
    assert any("Delivery country not established" in g for g in o["gaps"])
    # uncertain deadline: local time, never an exact instant, with the zone uncertainty in the record
    assert o["deadline_utc"] is None and o["deadline_info"]["precision"] == "local_time" and o["deadline_info"]["local_time"] == "15:00"
    assert any("not established" in n for n in o["deadline_info"].get("notes", []))
    # unsupported/uninterpreted eligibility: never "established"
    checks = {r["check_code"]: r for r in rdb.all("opportunity_checks", id=opp)}
    assert checks["eligibility"]["result"] == "unknown" and "await review" in checks["eligibility"]["rationale"]
    # exports carry the stated precision, never a fabricated UTC instant
    row = rdb.one("opportunity_list2", module=None, stage=None, qual=None, company=None, q=None, geo=None, limit=10, offset=0)
    assert row["deadline_utc"] is None and (row["deadline_info"] or {}).get("precision") == "local_time"
    # the country search does not list it as a Chile match (the delivery country is not established), so the run results carry
    # no silent geography; the record is reachable through the opportunity list and the review queue instead
    assert rdb.all("run_results", run=run_id) == []
    assert rdb.pg.val("SELECT count(*) FROM opportunities") == "1"
    sig = rdb.one("signal_get", id=o["signal_id"])
    assert any("not established" in g for g in sig["gaps"])
    # scores: evidence confidence counts independent sources, not unresolved fields; nothing scores eligibility as met
    assert rdb.pg.val(f"SELECT count(*) FROM qualification_checks WHERE opportunity_id = '{opp}' AND check_code = 'eligibility' AND result = 'pass'") == "0"


def test_v3_recheck_withdraws_a_zone_fact_and_a_status_and_keeps_history(rdb):  # noqa: F811
    _run(rdb)
    opp = rdb.pg.val("SELECT id FROM opportunities")
    claim = rdb.pg.val("SELECT id FROM claims WHERE claim_type = 'service_tender'")
    # Put the record into the shape rules v2 left: SCT taken as an exact instant (+4), the status 'open' confirmed, version 2.
    rdb.pg.run(f"UPDATE claim_fields SET validation_version = 2, reason = 'date stated in the quote; time and zone stated', "
               f"normalised = '2026-12-22T11:00:00+00:00' WHERE claim_id = '{claim}' AND field = 'deadline'")
    rdb.pg.run(f"UPDATE claims SET deadline_utc = '2026-12-22 11:00:00+00', deadline_source_tz = 'SCT', review_status = 'confirmed', "
               f"deadline_info = jsonb_set(deadline_info, '{{precision}}', '\"instant\"') WHERE id = '{claim}'")
    rdb.pg.run(f"UPDATE claim_fields SET validation_version = 2 WHERE claim_id = '{claim}' AND field = 'status'")
    rdb.pg.run((__import__('pathlib').Path(__file__).resolve().parents[2] / "migrations" / "sql" / "wfc_0006_revalidation_v3.sql").read_text())
    assert rdb.pg.val("SELECT payload->>'to_version' FROM jobs WHERE job_type = 'eligibility_revalidation'") == "3"
    report = er.revalidate(rdb, now=datetime(2026, 10, 27, tzinfo=UTC), to_version=3)
    assert report["by_field"]["deadline"]["checked"] == 1 and report["by_field"]["deadline"]["changed"] == 1
    # the deadline is still supported but no longer an exact instant: the claim's record followed the re-check
    assert rdb.pg.val(f"SELECT deadline_utc::text FROM claims WHERE id = '{claim}'") == ""
    assert rdb.pg.val(f"SELECT deadline_info->>'precision' FROM claims WHERE id = '{claim}'") == "local_time"
    rows = rdb.pg.rows(f"SELECT support, validation_version, superseded_at IS NOT NULL, recheck_of IS NOT NULL FROM claim_fields "
                       f"WHERE claim_id = '{claim}' AND field = 'deadline' ORDER BY created_at")
    assert rows[0][1:] == ["2", "t", "f"] and rows[1][1:] == ["3", "f", "t"]                 # original kept and linked
    assert rdb.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'deadline_revalidated'") == "1"
    assert rdb.pg.val(f"SELECT validation_version FROM claim_fields WHERE claim_id = '{claim}' AND field = 'status' AND superseded_at IS NULL") == "3"
    o = rdb.one("opportunity_get", id=opp)
    assert o["deadline_utc"] is None and o["deadline_info"]["precision"] == "local_time"
    assert er.revalidate(rdb, to_version=3)["checked"] == 0                                    # idempotent

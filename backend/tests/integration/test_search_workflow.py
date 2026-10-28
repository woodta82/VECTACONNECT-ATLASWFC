"""27 Oct 2026, item 7: the complete country-search workflow — retrieval, extraction, filtering and opportunity creation
in every geography mode — and the proof that queued work resumes without duplicating opportunities or losing
amendments. Real PostgreSQL, synthetic pages, scripted extractor."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import discovery as dsc
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401

UTC = timezone.utc
NOW = datetime(2026, 10, 27, 9, tzinfo=UTC)
T1 = "Example Air invites proposals from GSSA providers for cargo sales representation in Kenya. Tender reference EXA-GSSA-2026-201. Proposals are due on 20 January 2027."
T2 = "Example Air invites proposals from GSSA providers for cargo sales representation in Uganda. Tender reference EXA-GSSA-2026-202. Proposals are due on 27 January 2027."
T3 = "Sample Airways invites bids for cargo handling at Mombasa in Kenya. Tender reference SAW-HDL-2026-203. Bids are due on 3 February 2027."
AMEND = "Corrigendum to tender EXA-GSSA-2026-201: the deadline for proposals is extended from 20 January 2027 to 10 February 2027."
NEWS = "Example Air opened a new cargo office in Nairobi, Kenya, this week."


def reply(doc: str) -> dict:
    claims = []
    for text, ref, country, service, day, ct in ((T1, "EXA-GSSA-2026-201", "Kenya", "GSSA", "2027-01-20", "gssa_tender"),
                                                 (T2, "EXA-GSSA-2026-202", "Uganda", "GSSA", "2027-01-27", "gssa_tender"),
                                                 (T3, "SAW-HDL-2026-203", "Kenya", "HANDLING", "2027-02-03", "service_tender")):
        if text in doc:
            airline = "Example Air" if "Example Air" in text else "Sample Airways"
            claims.append({"claim_type": ct, "stance": "supports", "quote": text,
                           "fields": {"airline": {"value": airline, "quote": text}, "country": {"value": country, "quote": text},
                                      "service": {"value": service, "quote": text}, "status": {"value": "open", "quote": text},
                                      "tender_ref": {"value": ref, "quote": text}, "deadline": {"value": day, "quote": text}}})
    if AMEND in doc:
        claims.append({"claim_type": "tender_status", "stance": "supports", "quote": AMEND,
                       "fields": {"airline": {"value": "Example Air", "quote": AMEND}, "tender_ref": {"value": "EXA-GSSA-2026-201", "quote": AMEND},
                                  "status": {"value": "revised", "quote": AMEND}, "deadline": {"value": "2027-02-10", "quote": AMEND}}})
    return {"language": "en", "claims": claims}


def _site(rdb, max_items):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/n/", country_coverage=["KE", "UG"], max_items=max_items)
    links = [f"{BASE}/n/1", f"{BASE}/n/2", f"{BASE}/n/3", f"{BASE}/n/amend", f"{BASE}/n/news"]
    return Web({BASE + "/n/": _listing(links), links[0]: _page("RFP 201", T1), links[1]: _page("RFP 202", T2), links[2]: _page("RFP 203", T3),
                links[3]: _page("Corrigendum 201", AMEND), links[4]: _page("News", NEWS)})


def _run(rdb, sid, web):  # noqa: F811
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply), now=NOW)
    return rdb.one("run_get", id=started["run_id"])


def _opps(rdb):  # noqa: F811
    return rdb.pg.rows("SELECT s.tender_ref, o.tender_status, o.deadline_info->>'day' FROM opportunities o JOIN signals s ON s.id = o.signal_id "
                       "WHERE o.merged_into_id IS NULL ORDER BY s.tender_ref")


@pytest.mark.parametrize("mode,countries,regions,expected_refs", [
    ("country", ["KE"], [], ["EXA-GSSA-2026-201", "SAW-HDL-2026-203"]),
    ("countries", ["KE", "UG"], [], ["EXA-GSSA-2026-201", "EXA-GSSA-2026-202", "SAW-HDL-2026-203"]),
    ("region", [], ["EAC"], ["EXA-GSSA-2026-201", "EXA-GSSA-2026-202", "SAW-HDL-2026-203"]),
    ("worldwide", [], [], ["EXA-GSSA-2026-201", "EXA-GSSA-2026-202", "SAW-HDL-2026-203"]),
])
def test_every_mode_runs_retrieval_extraction_filtering_and_creation_and_reports_what_it_searched(rdb, mode, countries, regions, expected_refs):  # noqa: F811
    web = _site(rdb, max_items=10)
    sid = dsc.create_search(rdb, dsc.SearchSpec(mode, countries, regions, []))
    run = _run(rdb, sid, web)
    assert run["status"] == "completed", run["counts"]
    results = rdb.all("run_results", run=run["id"])
    refs = sorted(r["title"].split("(")[-1].rstrip(")") for r in results if r.get("opportunity_id"))
    assert refs == expected_refs, (refs, run["counts"])                      # filtering by geography: Uganda only outside "Kenya"
    cov = run["counts"]["coverage"]
    assert cov["attempted"] and cov["extracted"] and run["counts"]["documents"] == 5   # what was searched, by stage
    assert run["counts"]["queue"]["pending"] == 0 and run["counts"]["queue"]["gave_up"] == 0
    plan = run["plan"]
    if mode == "worldwide":
        assert plan["countries"] == "worldwide" and "source coverage" in (plan.get("coverage_note") or "").lower() or plan["countries"] == "worldwide"
    else:
        assert set(plan["countries"]) >= set(expected_refs and (countries or ["KE", "UG"]))


def test_queued_work_resumes_without_duplicating_opportunities_or_losing_amendments(rdb):  # noqa: F811
    web = _site(rdb, max_items=2)                                # 5 relevant links, 2 per run: the rest is queued
    sid = dsc.create_search(rdb, dsc.SearchSpec("countries", ["KE", "UG"], [], []))
    r1 = _run(rdb, sid, web)
    assert r1["status"] == "partial" and r1["counts"]["queue"]["pending"] == 3
    assert _opps(rdb) == [["EXA-GSSA-2026-201", "open", "2027-01-20"], ["EXA-GSSA-2026-202", "open", "2027-01-27"]]
    r2 = _run(rdb, sid, web)                                     # reads notice 3 and the corrigendum from the queue
    assert r2["counts"]["queue"]["pending"] == 1 and r2["counts"]["queue"]["resumed"] >= 1
    opps = _opps(rdb)
    assert len(opps) == 3 and [o[0] for o in opps] == ["EXA-GSSA-2026-201", "EXA-GSSA-2026-202", "SAW-HDL-2026-203"]   # no duplicate of 201
    assert opps[0][1:] == ["revised", "2027-02-10"], opps                     # the amendment reached the existing record
    r3 = _run(rdb, sid, web)                                     # the news item, then nothing waits
    assert r3["status"] == "completed" and r3["counts"]["queue"]["pending"] == 0
    assert len(_opps(rdb)) == 3 and rdb.pg.val("SELECT count(*) FROM opportunities") == "3"
    # Running again changes nothing: idempotent on already-read documents, and the amendment is not lost or re-applied
    r4 = _run(rdb, sid, web)
    assert r4["status"] == "completed" and _opps(rdb)[0][1:] == ["revised", "2027-02-10"]
    assert rdb.pg.val("SELECT count(*) FROM opportunities") == "3" and rdb.pg.val("SELECT count(*) FROM signals WHERE merged_into_id IS NULL") >= "3"
    hist = rdb.pg.rows("SELECT to_value FROM opportunity_status_history WHERE field = 'deadline' ORDER BY changed_at")
    assert any("2027-02-10" in h[0] for h in hist)


def test_worldwide_never_implies_complete_coverage(rdb):  # noqa: F811
    web = _site(rdb, max_items=10)
    sid = dsc.create_search(rdb, dsc.SearchSpec("worldwide", [], [], []))
    run = _run(rdb, sid, web)
    note = (run["plan"].get("coverage_note") or "")
    assert run["plan"]["countries"] == "worldwide"
    assert "not a complete worldwide view" in note and "limited to these sources" in note, note
    assert run["counts"]["coverage"]["planned"] == ["KE", "UG"]           # exactly the configured sources' coverage, nothing more

"""Open-web discovery as the default, on PostgreSQL (29 Oct 2026): a country, region or worldwide search for a capability area
finds public sources through the authorised web search WITHOUT any registered website, reads the accessible originals, creates
sourced opportunities and market signals, labels registration-restricted results and looks for a public original, and keeps
"nothing relevant found" apart from "search not configured", "search failed", "inaccessible" and "incomplete".

SIMULATED: synthetic pages (Web), a scripted search transport and a scripted extractor. No real site or provider is used.
"""
from __future__ import annotations

from app import config
from app.connectors.search import SearchFailed, SearchResult
from app.domain import retrieval
from app.services import discovery as dsc
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_relationship_journey import KE, ROUTE, PUBLISHED, reply
from tests.integration.test_review3_regressions import SETTINGS, Web, _page, model, rdb  # noqa: F401

PORTAL = "https://tenders.go.ke/notices/exa-gssa-2026-301"
COPY = "https://www.example-air.example/press/gssa-tender-kenya"
PRESS = "https://www.aircargonews.net/example-air-777f-nairobi"
GATED = "https://premium-tenders.example/notice/exa-gssa-2026-301"          # answers 401
WALL = "https://tenderwall.example/notice/kenya-cargo-gssa"                 # answers 200 with a login gate only
SEARCH = config.load({"ENVIRONMENT": "test", "SEARCH_PROVIDER": "brave", "SEARCH_API_KEY": "search-key-not-real", "SEARCH_MAX_QUERIES": "6",
                      "ANTHROPIC_API_KEY": "key-not-real", "AI_MODEL": "fixture", "AI_PRICE_INPUT_PER_MTOK": "3", "AI_PRICE_OUTPUT_PER_MTOK": "15"})


def site() -> Web:
    return Web({
        PORTAL: _page("Tender EXA-GSSA-2026-301: GSSA representation Kenya", KE, published=PUBLISHED),
        COPY: _page("Example Air invites GSSA proposals for Kenya", KE, published=PUBLISHED),
        PRESS: _page("Example Air adds 777F Nairobi service", ROUTE, published=PUBLISHED),
        GATED: retrieval.RetrievalFailed("HTTP 401"),
        WALL: _page("Members area", "Please log in or register to view this tender notice. Subscribe for full access. Password:"),
    })


def _search(log: list[tuple[str, str | None]]):
    def search(_s, query, country, count):
        log.append((query, country))
        if query.startswith('"Tender EXA-GSSA-2026-301'):                       # corroboration of the gated notice
            return [SearchResult(COPY, "Example Air invites GSSA proposals for Kenya", "")]
        if "GSSA" in query and "tender" in query and country == "KE":
            return [SearchResult(PORTAL, "Tender EXA-GSSA-2026-301: GSSA representation Kenya", ""),
                    SearchResult(GATED, "Tender EXA-GSSA-2026-301: GSSA representation Kenya (member download)", ""),
                    SearchResult(WALL, "Kenya cargo GSSA notice", "")]
        if "new route" in query and country == "KE":
            return [SearchResult(PRESS, "Example Air adds 777F Nairobi service", "")]
        return []
    return search


def _run(db, spec: dsc.SearchSpec, settings, web, search):
    sid = dsc.create_search(db, spec)
    started = dsc.start_run(db, settings, search_id=sid)
    dsc.execute_run(db, settings, started["run_id"], None, fetch=web, transport=model(reply), search_transport=search)
    return started["plan"], db.one("run_get", id=started["run_id"])


def test_a_country_search_finds_public_sources_without_a_registered_website(rdb):  # noqa: F811
    db = rdb
    assert db.pg.val("SELECT count(*) FROM sources WHERE source_type <> 'web_search' AND deleted_at IS NULL") == "0"   # nothing registered
    asked: list[tuple[str, str | None]] = []
    plan, run = _run(db, dsc.SearchSpec("country", ["KE"], [], ["airline_representation", "capacity_lanes"]), SEARCH, site(), _search(asked))
    assert plan["open_web"]["planned"] and plan["open_web"]["connected"] and plan["open_web"]["queries"] >= 4
    assert plan["sources"][0]["name"].startswith("Open web") and "Open-web search" in plan["coverage_note"]
    assert run["outcome"] in ("results", "incomplete"), run["counts"]
    counts = run["counts"]
    assert counts["matched"] >= 1 and all(c == "KE" for _q, c in asked)
    assert any(w["status"] == "run" and w["results"] == 3 for w in counts["web_searches"])
    # the official portal notice became a sourced tender opportunity; the trade-press route launch a market signal
    assert db.pg.val("SELECT count(*) FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-301'") == "1"
    assert db.pg.val("SELECT doc_authority FROM source_documents WHERE canonical_url LIKE 'https://tenders.go.ke/%'") == "official_portal"
    assert db.pg.val("SELECT doc_authority FROM source_documents WHERE canonical_url LIKE '%aircargonews.net/%'") == "trade_press"
    assert db.pg.val("SELECT doc_family FROM source_documents WHERE canonical_url LIKE 'https://tenders.go.ke/%'") == "tenders.go.ke"
    assert db.pg.val("SELECT publisher FROM source_documents WHERE canonical_url LIKE '%aircargonews.net/%'") == "aircargonews.net"
    assert db.pg.val("SELECT count(*) FROM signals WHERE classification NOT IN ('historical_record','excluded') AND tender_ref IS NULL") >= "1"  # the route launch: a market signal
    # the two restricted results are labelled, never read, and a public original of the gated notice was searched for and read
    restricted = {r["url"]: r for r in counts["restricted"]}
    assert restricted[GATED]["label"] == "Registration or login required" and restricted[WALL]["restriction"] in ("login_required", "payment_required")
    assert restricted[GATED]["corroboration"] == "1 other source(s) found and read"
    assert any(q.startswith('"Tender EXA-GSSA-2026-301') for q, _c in asked)
    assert db.pg.val("SELECT count(*) FROM source_documents WHERE canonical_url LIKE '%example-air.example/press/gssa-tender-kenya'") == "1"
    assert db.pg.val(f"SELECT count(*) FROM source_documents WHERE canonical_url IN ('{GATED}', '{WALL}')") == "0"
    assert "inaccessible_sources" in counts["flags"] and counts["restricted_count"] == 2
    assert counts["issue_counts"].get("access_restricted") == 2
    # the syndicated copy corroborates the portal notice: one opportunity, two evidence documents from two publishers
    assert int(db.pg.val("SELECT count(DISTINCT ce.source_document_id) FROM opportunities o JOIN signal_claims sc ON sc.signal_id = o.signal_id "
                         "JOIN claim_evidence ce ON ce.claim_id = sc.claim_id JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-GSSA-2026-301'")) == 2


def test_region_and_worldwide_searches_query_per_country_and_report_coverage(rdb):  # noqa: F811
    db = rdb
    asked: list[tuple[str, str | None]] = []
    plan, run = _run(db, dsc.SearchSpec("region", [], ["EAC"], ["airline_representation"]), SEARCH, site(), _search(asked))
    assert {c for _q, c in asked} >= {"KE", "UG", "TZ"} and plan["open_web"]["countries"] == 8
    assert run["counts"]["coverage"]["planned"] and "KE" in run["counts"]["coverage"]["retrieved"]
    asked.clear()
    plan, run = _run(db, dsc.SearchSpec("worldwide", [], [], []), SEARCH, site(), _search(asked))
    assert all(c is None for _q, c in asked) and len(asked) >= 9 and plan["open_web"]["queries"] == len(asked)
    assert run["outcome"] == "no_relevant_results" and "worldwide" in plan["coverage_note"]
    assert "not a complete worldwide view" in plan["coverage_note"]


def test_no_connector_is_not_nothing_found_and_a_failed_search_is_a_failure(rdb):  # noqa: F811
    db = rdb
    no_search = config.load({"ENVIRONMENT": "test"})
    plan, run = _run(db, dsc.SearchSpec("country", ["OM"], [], ["service_operations"]), no_search, site(), None)
    assert not plan["open_web"]["connected"] and "NOT configured" in plan["coverage_note"]
    assert run["outcome"] == "search_not_configured" and run["status"] == "completed"
    assert run["counts"]["web_searches"] and all(w["status"] == "not_run" and w["link"].startswith("https://www.google.com/search?q=")
                                                 for w in run["counts"]["web_searches"])

    def broken(_s, query, country, count):
        raise SearchFailed("search provider returned HTTP 429")
    plan, run = _run(db, dsc.SearchSpec("country", ["OM"], [], ["service_operations"]), SEARCH, site(), broken)
    assert run["outcome"] == "search_failure" and run["status"] == "failed"
    assert all(w["status"] == "failed" for w in run["counts"]["web_searches"]) and run["counts"]["issue_counts"]["search_failed"] >= 1


def test_configured_sources_remain_optional_monitoring_inputs_beside_the_open_web(rdb):  # noqa: F811
    db = rdb
    from tests.integration.test_review3_regressions import BASE, _listing, _source
    web = site()
    web.pages[BASE + "/n/"] = _listing([BASE + "/n/ke"])
    web.pages[BASE + "/n/ke"] = _page("RFP EXA-GSSA-2026-301", KE, published=PUBLISHED)
    _source(db, "Example Air procurement", "listing", BASE + "/n/", country_coverage=["KE"], max_items=5)
    asked: list[tuple[str, str | None]] = []
    plan, run = _run(db, dsc.SearchSpec("country", ["KE"], [], ["airline_representation"]), SEARCH, web, _search(asked))
    assert [s["name"] for s in plan["sources"]] == ["Example Air procurement", "Open web (authorised search)"] or \
        {s["name"] for s in plan["sources"]} == {"Example Air procurement", "Open web (authorised search)"}
    assert "plus 1 configured monitoring source" in plan["coverage_note"]
    assert run["outcome"] in ("results", "incomplete") and run["counts"]["matched"] >= 1

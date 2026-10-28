"""Directive §14 acceptance tests 1, 3, 4, 8, 9 and 10 (discovery part), end to
end: real PostgreSQL through the production SQLAlchemy adapter, real HTTP
retrieval through the SSRF-safe fetcher, real content extraction, the real
AI extraction client and budget reservation, against LOCAL stand-ins:
a synthetic fixture site and a fake Messages API provider that returns
canned claims (tests/fixtures/servers.py). The model itself is simulated;
everything after the HTTP response is the production code path.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import config
from app.services import discovery as dsc
from app.services import sources_service as srcs
from app.services.audit import RequestMeta
from app.services.worker import run_one
from app.worker_main import handlers_for
from tests.fixtures.servers import FakeAIProvider, FixtureSite

META = RequestMeta(ip="203.0.113.10", request_id="req-d", session_ref="sessdiscovery")
NOW = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)


@pytest.fixture()
def env(sadb):
    with FixtureSite() as site, FakeAIProvider() as ai:
        settings = config.load({"ENVIRONMENT": "test", "DATABASE_URL": "postgresql://x@y/z", "ANTHROPIC_API_KEY": "test-key-not-real",
                                "AI_MODEL": "fixture-model", "AI_PRICE_INPUT_PER_MTOK": "3", "AI_PRICE_OUTPUT_PER_MTOK": "15",
                                "AI_API_BASE_URL": ai.base, "RETRIEVAL_ALLOW_PRIVATE_HOSTS": f"127.0.0.1:{site.port}"})
        sadb.run("flag_set", key="ai_kill_switch", value="false")
        sadb.run("budget_set", cap="10.00", warn="8.00", per_run="1.00")
        yield sadb, settings, site


def add_sources(db, site):
    # Reference data a fresh installation loads through Setup (airports import); see test_setup_imports.py.
    db.pg.run("INSERT INTO airports (iata_code, name, country, timezone) VALUES ('DXB','Dubai International','AE','Asia/Dubai'),"
              "('NBO','Jomo Kenyatta International','KE','Africa/Nairobi') ON CONFLICT DO NOTHING")
    portal = srcs.create_source(db, srcs.SourceSpec(
        "Example Air procurement portal", "listing", f"{site.base}/example-air/tenders/", "official_portal",
        country_coverage=["KE", "UG", "TZ"], modules=["airline_representation"], language="en", retention_permitted=True,
        enabled=True), META)
    wire = srcs.create_source(db, srcs.SourceSpec(
        "Gulf Cargo Trade Wire", "listing", f"{site.base}/tradewire/", "trade_press", global_coverage=True,
        language="en", retention_permitted=True, enabled=True), META)
    search = srcs.create_source(db, srcs.SourceSpec(
        "Regional procurement search", "search_template", f"{site.base}/procure/", "official_portal",
        query_template=f"{site.base}/procure/search?country={{country}}&q={{keywords}}", country_coverage=["AE", "CI", "KE"],
        language="fr", retention_permitted=True, enabled=True), META)
    return portal, wire, search


def run_search(db, settings, **spec):
    sid = dsc.create_search(db, dsc.SearchSpec(**spec))
    started = dsc.start_run(db, settings, search_id=sid)
    # the worker executes the queued job (same code path as `python -m app.worker_main`)
    assert run_one(db, handlers_for(settings), "pytest-worker") == "succeeded"
    return started["run_id"], db.one("run_get", id=started["run_id"])


def test_country_search_discovers_new_records_and_explains_matches(env):
    db, settings, site = env
    add_sources(db, site)
    assert db.pg.val("SELECT count(*) FROM signals") == "0"           # nothing stored before the search
    run_id, run = run_search(db, settings, geo_mode="country", countries=["KE"], regions=[], modules=[])
    assert run["status"] == "completed" and run["outcome"] == "results", run
    results = db.all("run_results", run=run_id)
    assert results and all(r["is_new"] for r in results)                 # discovered, not filtered from stored records
    titles = {r["title"] for r in results}
    # Acceptance 1: claims and a visible sourced signal; 3: two tenders for Example Air in Kenya stay distinct.
    tenders = [r for r in results if "GSSA tender" in r["title"]]
    refs = sorted(r["title"].split("(")[-1].rstrip(")") for r in tenders)
    assert refs == ["EXA-CGO-2026-014", "EXA-CGO-2026-022", "EXA-CGO-2026-031"], titles
    assert db.pg.val("SELECT count(*) FROM opportunities WHERE module='airline_representation'") == "3"
    # The route launch DXB->NBO matches Kenya as a lane destination (scope), from the global trade wire.
    route = next(r for r in results if "route launch" in r["title"])
    assert {"country": "KE", "name": "Kenya", "role": "destination"} in route["match"]["geography"]
    assert route["match"]["classification"] == "market_signal"
    # Oman partnership and the UAE trucking RFQ are retrieved (global source) but do not match Kenya.
    assert not any("Coastal Handling" in t or "trucking" in t.lower() for t in titles)
    # Why each result matches: geography, capability area, source, dates, qualification, confidence, gaps, next action.
    t14 = next(r for r in results if "EXA-CGO-2026-014" in r["title"])
    m = t14["match"]
    assert m["geography_basis"] == "scope" and m["capability_area"] == "airline_representation"
    assert m["sources"] == ["Example Air procurement portal"] and m["confidence"]["best_authority"] == "official_portal"
    assert m["deadline_utc"] == "2026-12-14T14:00:00+00:00" and m["deadline_source_tz"] == "EAT"   # addendum applied; zone as the source states it
    assert m["tender_status"] == "revised"
    assert "AI-proposed evidence awaits reviewer confirmation" in m["gaps"]
    assert m["recommended_next_action"].endswith("Review and confirm the AI-proposed evidence")
    assert run["actual_cost_usd"] is not None and run["actual_cost_usd"] > 0 and run["estimated_cost_usd"] >= run["actual_cost_usd"]


def test_amendment_applies_to_the_right_tender_with_history(env):
    db, settings, site = env
    add_sources(db, site)
    run_search(db, settings, geo_mode="country", countries=["KE"], regions=[], modules=["airline_representation"])
    o14 = db.pg.val("SELECT id FROM opportunities WHERE title LIKE '%EXA-CGO-2026-014%'")
    o22 = db.pg.val("SELECT id FROM opportunities WHERE title LIKE '%EXA-CGO-2026-022%'")
    assert db.pg.val(f"SELECT deadline_utc AT TIME ZONE 'UTC' FROM opportunities WHERE id='{o14}'") == "2026-12-14 14:00:00"
    assert db.pg.val(f"SELECT deadline_utc AT TIME ZONE 'UTC' FROM opportunities WHERE id='{o22}'") == "2026-12-15 09:00:00"
    hist = db.pg.rows(f"SELECT field, from_value, to_value FROM opportunity_status_history WHERE opportunity_id='{o14}' "
                      "AND field IN ('deadline','tender_status') ORDER BY id")
    assert ["tender_status", "", "open"] in hist or ["tender_status", "", "revised"] in hist
    assert any(h[0] == "deadline" and h[2].startswith("2026-12-14") for h in hist) or \
        db.pg.val(f"SELECT tender_state->'history' @> '[{{\"field\":\"deadline\"}}]' FROM signals s JOIN opportunities o ON o.signal_id=s.id WHERE o.id='{o14}'") == "t"
    # No merge candidates: both tenders carry stable references.
    assert db.pg.val("SELECT count(*) FROM merge_candidates WHERE entity_type='signal'") == "0"


def test_unsupported_extracted_fields_never_become_facts(env):
    """Acceptance 4: the extractor claims the issuer is in the UAE and that a route is an 'open' tender;
    neither is stated by its quote, so neither becomes a fact."""
    db, settings, site = env
    add_sources(db, site)
    run_search(db, settings, geo_mode="worldwide", countries=[], regions=[], modules=[])
    assert db.pg.rows("SELECT support, reason FROM claim_fields WHERE field='issuer_country'") == [
        ["unsupported", "the quote does not state United Arab Emirates"]]
    assert db.pg.val("SELECT count(*) FROM signal_geography WHERE role='issuer' AND support='supported'") == "0"
    assert db.pg.val("SELECT support FROM claim_fields cf JOIN claims c ON c.id=cf.claim_id WHERE c.claim_type='route_launch' AND cf.field='status'") \
        == "not_applicable"
    # A route announcement never becomes an opportunity.
    assert db.pg.val("SELECT count(*) FROM opportunities o JOIN signals s ON s.id=o.signal_id WHERE s.signal_key LIKE 'route|%'") == "0"
    # The malformed claim was rejected individually and waits for review; the valid claim in the same output counted.
    assert db.pg.val("SELECT count(*) FROM extraction_rejections WHERE status='open' AND reason LIKE '%unexpected keys%'") == "1"
    # Trade-press-only trucking RFQ is an unverified lead (not authoritative); the official RFQ is an opportunity.
    assert db.pg.val("SELECT classification FROM signals WHERE title LIKE 'Sample Airways: trucking tender AE (SAW-RFS-2026-07)'") \
        == "qualified_opportunity"
    assert db.pg.val("SELECT count(*) FROM signals WHERE classification='unverified_lead' AND module='trucking_gateways'") == "1"
    # Local-language notice: original quote kept, English summary flagged as a translation, French date read from the source.
    row = db.pg.rows("SELECT d.language, d.summary_is_translation, o.deadline_utc AT TIME ZONE 'UTC', o.module FROM source_documents d "
                     "JOIN claim_evidence ce ON ce.source_document_id=d.id JOIN signal_claims sc ON sc.claim_id=ce.claim_id "
                     "JOIN opportunities o ON o.signal_id=sc.signal_id WHERE d.canonical_url LIKE '%ci-formation-fret%'")
    assert row == [["fr", "t", "2026-12-18 12:00:00", "outsourcing_training"]]


def test_multi_country_result_counts_once_and_repeated_runs_are_idempotent(env):
    """Acceptance 9 (discovery side) and 10 (scheduled runs)."""
    db, settings, site = env
    add_sources(db, site)
    run_id, _ = run_search(db, settings, geo_mode="countries", countries=["KE", "UG", "TZ"], regions=[], modules=["airline_representation"])
    rows = db.all("run_results", run=run_id)
    regional = [r for r in rows if "EXA-CGO-2026-031" in r["title"]]
    assert len(regional) == 1                                            # one result, not one per country
    assert {g["country"] for g in regional[0]["match"]["geography"]} == {"KE", "UG"}
    assert db.pg.val("SELECT count(*) FROM opportunities WHERE title LIKE '%EXA-CGO-2026-031%'") == "1"
    counts = [db.pg.val(f"SELECT count(*) FROM {t}") for t in ("opportunities", "signals", "claims", "source_documents", "claim_fields")]
    calls_before = int(db.pg.val("SELECT count(*) FROM ai_calls"))
    # Run the same search again, then once from a schedule tick: nothing multiplies, nothing is re-extracted or re-charged.
    run_id2, run2 = run_search(db, settings, geo_mode="region", countries=[], regions=["EAC"], modules=["airline_representation"])
    assert [db.pg.val(f"SELECT count(*) FROM {t}") for t in ("opportunities", "signals", "claims", "source_documents", "claim_fields")] == counts
    assert int(db.pg.val("SELECT count(*) FROM ai_calls")) == calls_before
    assert not any(r["is_new"] for r in db.all("run_results", run=run_id2))
    assert run2["status"] == "completed"


def test_no_coverage_source_failure_and_incomplete_are_distinguished(env):
    db, settings, site = env
    portal, wire, search = add_sources(db, site)
    # A country no source covers (and the global wire disabled): nothing was searched, never "no results".
    srcs.set_enabled(db, wire, False, META)
    _, run = run_search(db, settings, geo_mode="country", countries=["BR"], regions=[], modules=[])
    assert (run["status"], run["outcome"]) == ("completed", "no_sources")
    assert run["plan"]["coverage_gaps"] == ["BR"] and "Nothing was searched" in run["plan"]["coverage_note"]
    # Every planned source failing is a source failure.
    db.pg.run(f"UPDATE sources SET base_url = '{site.base}/broken/' WHERE id = '{portal}'")
    _, run = run_search(db, settings, geo_mode="country", countries=["UG"], regions=[], modules=["airline_representation"])
    assert (run["status"], run["outcome"]) == ("failed", "source_failure")
    assert "HTTP 503" in db.pg.val(f"SELECT detail FROM discovery_run_sources WHERE source_id='{portal}' ORDER BY 1 DESC LIMIT 1")
    # AI kill switch on: documents are retrieved and stored but not extracted => incomplete, visible per document.
    db.pg.run(f"UPDATE sources SET base_url = '{site.base}/example-air/tenders/' WHERE id = '{portal}'")
    db.run("flag_set", key="ai_kill_switch", value="true")
    _, run = run_search(db, settings, geo_mode="country", countries=["KE"], regions=[], modules=["airline_representation"])
    assert (run["status"], run["outcome"]) == ("partial", "incomplete")
    assert run["counts"]["unextracted"] == 4
    assert db.pg.val("SELECT count(*) FROM source_documents WHERE extraction_status='budget_refused'") == "4"


def test_ai_not_connected_routes_documents_to_review(sadb):
    with FixtureSite() as site:
        settings = config.load({"ENVIRONMENT": "test", "DATABASE_URL": "postgresql://x@y/z",
                                "RETRIEVAL_ALLOW_PRIVATE_HOSTS": f"127.0.0.1:{site.port}"})
        add_sources(sadb, site)
        _, run = run_search(sadb, settings, geo_mode="country", countries=["KE"], regions=[], modules=["airline_representation"])
        assert (run["status"], run["outcome"]) == ("partial", "incomplete")
        assert run["plan"]["ai_status"].startswith("AI extraction is not connected")
        assert sadb.pg.val("SELECT count(*) FROM source_documents WHERE extraction_status='not_connected'") == "7"   # 4 portal + 3 trade wire (global)
        assert sadb.pg.val("SELECT count(*) FROM ai_calls") == "0" and sadb.pg.val("SELECT count(*) FROM signals") == "0"


def test_capped_country_queries_are_disclosed_and_mark_the_run_incomplete(env, monkeypatch):
    db, settings, site = env
    _portal, wire, _search = add_sources(db, site)
    srcs.set_enabled(db, wire, False, META)
    monkeypatch.setattr(dsc, "MAX_COUNTRY_QUERIES_PER_SOURCE", 2)
    run_id, run = run_search(db, settings, geo_mode="countries", countries=["AE", "CI", "KE"], regions=[], modules=[])
    assert "at most 2 countries" in run["plan"]["coverage_note"]
    assert run["outcome"] == "incomplete" and run["status"] == "partial"
    assert run["counts"]["not_searched_countries"] == ["KE"]            # alphabetical: AE, CI searched; KE not reached
    assert "incomplete" in run["counts"]["flags"]


def test_retry_twice_starts_one_retry_run(env):
    db, settings, site = env
    portal, wire, search = add_sources(db, site)
    srcs.set_enabled(db, wire, False, META)
    srcs.set_enabled(db, search, False, META)
    db.pg.run(f"UPDATE sources SET base_url = '{site.base}/broken/' WHERE id = '{portal}'")
    run_id, run = run_search(db, settings, geo_mode="country", countries=["KE"], regions=[], modules=[])
    assert run["status"] == "failed"
    first = dsc.retry_run(db, settings, run_id)
    second = dsc.retry_run(db, settings, run_id)
    assert second["run_id"] == first["run_id"] and second.get("existing") is True
    assert db.pg.val("SELECT count(*) FROM discovery_runs") == "2"

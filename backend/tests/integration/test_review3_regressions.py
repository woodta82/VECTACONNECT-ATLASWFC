"""Review of 26 Oct 2026 ("Full build review and Claude amendments"), §5 acceptance tests that need
the database: deadline precision end to end, truthful run completion, cumulative per-run budgets,
bounded estimates, publication-date provenance and resumable coverage. Real PostgreSQL through the
production adapter; synthetic fixture site and SIMULATED AI provider where a run is executed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.field_validation import FieldClaim as F
from app.services import imports_service as imp
from app.services import ingestion as ing
from app.services import sources_service as srcs
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401

UTC = timezone.utc
META = RequestMeta(ip="203.0.113.10", request_id="req-r3", session_ref="sessreview003")


@pytest.fixture()
def db(sadb):  # noqa: F811
    for ds, text in {"operating_companies": "name\nWFC-KE\n",
                     "airports": "iata_code,name,country,timezone\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n",
                     "airlines": "iata_code,name,country\nXA,Example Air,AE\n"}.items():
        imp.import_file(sadb, ds, f"{ds}.csv", text.encode(), None, META)
    sid = srcs.create_source(sadb, srcs.SourceSpec("Portal", "web_page", "https://tenders.example-air.example", "official_portal",
                                                   retention_permitted=True, enabled=True), META)
    sadb.portal = ing.SourceInfo(sid, "portal", "official_portal", "https://tenders.example-air.example", True)
    return sadb


DATE_ONLY = ("Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya. "
             "Tender reference EXA-CGO-2027-050. Proposals are due on 30 November 2026.")
Q = "Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya."


def _ingest(db, text, now, url="https://tenders.example-air.example/rfp/50", dl=("2026-11-30T00:00:00Z", "Proposals are due on 30 November 2026.")):
    p = ing.ClaimProposal("gssa_tender", Q, {"airline": F("Example Air", Q), "country": F("Kenya", Q), "service": F("GSSA", Q),
                                             "status": F("open", Q), "tender_ref": F("EXA-CGO-2027-050", "Tender reference EXA-CGO-2027-050."),
                                             "deadline": F(*dl)}, deadline_timezone="Africa/Nairobi")
    return ing.ingest(db, ing.IncomingDocument(db.portal, url, url, text, published_at=now - timedelta(days=2)), [p], now=now)


def test_date_only_deadline_is_never_a_timestamp(db):
    now = datetime(2026, 10, 26, 8, tzinfo=UTC)
    r = _ingest(db, DATE_ONLY, now)
    row = db.one("opportunity_scope", id=r.opportunity_id)
    assert row["deadline_utc"] is None                                     # no invented midnight UTC
    assert row["deadline_info"]["precision"] == "date" and row["deadline_info"]["day"] == "2026-11-30"
    assert row["deadline_info"]["assumed_utc"] is None                     # no time stated: no zone assumption applied
    assert row["deadline_earliest_utc"] == datetime(2026, 11, 29, 10, tzinfo=UTC)
    assert row["deadline_latest_utc"] == datetime(2026, 12, 1, 12, tzinfo=UTC)
    field = db.pg.val("SELECT normalised FROM claim_fields WHERE field='deadline' LIMIT 1")
    assert field == "2026-11-30"


def test_date_only_deadline_on_its_day_needs_review_not_expiry(db):
    on_the_day = datetime(2026, 11, 30, 9, tzinfo=UTC)
    r = _ingest(db, DATE_ONLY, on_the_day)
    check = next(c for c in db.all("opportunity_checks", id=r.opportunity_id) if c["check_code"] == "not_expired")
    assert check["result"] == "review_required" and "may already have passed" in check["rationale"]
    assert db.pg.val(f"SELECT tender_status FROM opportunities WHERE id='{r.opportunity_id}'") != "expired"
    after = datetime(2026, 12, 1, 13, tzinfo=UTC)                         # the date has ended everywhere
    ing.evaluate_signal(db, r.signal_id, after)
    assert db.pg.val(f"SELECT result FROM qualification_checks WHERE opportunity_id='{r.opportunity_id}' AND check_code='not_expired'") == "fail"


def test_a_timed_notice_refines_a_date_only_one(db):
    now = datetime(2026, 10, 26, 8, tzinfo=UTC)
    r = _ingest(db, DATE_ONLY, now)
    timed = DATE_ONLY.replace("Proposals are due on 30 November 2026.", "Proposals are due on 30 November 2026 at 17:00 EAT.")
    _ingest(db, timed, now, url="https://tenders.example-air.example/rfp/50/v2",
            dl=("2026-11-30T17:00", "Proposals are due on 30 November 2026 at 17:00 EAT."))
    row = db.one("opportunity_scope", id=r.opportunity_id)
    assert row["deadline_info"]["precision"] == "instant" and row["deadline_utc"] == datetime(2026, 11, 30, 14, tzinfo=UTC)
    hist = db.pg.rows(f"SELECT to_value FROM opportunity_status_history WHERE opportunity_id='{r.opportunity_id}' AND field='deadline'")
    assert hist and "17:00 EAT" in hist[-1][0]


# ===================================================================== discovery runs (items 5, 6, 7)
# The executor runs with an injected fetcher (a dict of synthetic pages) and an injected Messages-API transport,
# so each case controls exactly which target fails, what language a page is in and what the model proposes.
# Everything between those two edges is the production code path on real PostgreSQL.

import hashlib  # noqa: E402
import json  # noqa: E402
import threading  # noqa: E402
from decimal import Decimal  # noqa: E402

from app import config  # noqa: E402
from app.ai import extraction as ai  # noqa: E402
from app.domain import retrieval  # noqa: E402
from app.reference.geography import COUNTRIES  # noqa: E402
from app.services import discovery as dsc  # noqa: E402
from app.services import review_service as rev  # noqa: E402

BASE = "https://portal.example-air.example"
SETTINGS = config.load({"ENVIRONMENT": "test", "DATABASE_URL": "postgresql://x@y/z", "ANTHROPIC_API_KEY": "test-key-not-real",
                        "AI_MODEL": "fixture-model", "AI_PRICE_INPUT_PER_MTOK": "3", "AI_PRICE_OUTPUT_PER_MTOK": "15",
                        "AI_API_BASE_URL": "http://127.0.0.1:9"})
PER_DOC = ai.estimate_per_document(SETTINGS)


def _page(title: str, body: str, *, lang: str = "en", published: str | None = None) -> bytes:
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    return (f"<!doctype html><html lang='{lang}'><head><title>{title}</title>{meta}</head><body><main><h1>{title}</h1>"
            f"<p>{body}</p></main></body></html>").encode()


def _listing(links: list[str]) -> bytes:
    items = "".join(f'<li><a href="{u}">Notice {i}</a></li>' for i, u in enumerate(links))
    return f"<!doctype html><html lang='en'><head><title>Notices</title></head><body><main><ul>{items}</ul></main></body></html>".encode()


class Web:
    """Synthetic fetcher: url -> bytes (HTML), (bytes, content_type), or an exception instance to raise."""

    def __init__(self, pages: dict):
        self.pages, self.fetched = pages, []

    def __call__(self, url: str) -> retrieval.FetchResult:
        self.fetched.append(url)
        v = self.pages.get(url)
        if v is None:
            raise retrieval.RetrievalFailed("HTTP 404")
        if isinstance(v, Exception):
            raise v
        body, ctype = v if isinstance(v, tuple) else (v, "text/html")
        return retrieval.FetchResult(url, url, 200, ctype, body, hashlib.sha256(body).hexdigest())


def model(reply=lambda doc: {"language": "en", "claims": []}, calls: list | None = None):
    """Messages-API transport stand-in. Usage is not reported, so every call is charged at the estimate."""
    def transport(_settings, _system, user):
        if calls is not None:
            calls.append(user)
        doc = user.split("<document>\n", 1)[-1].split("\n</document>", 1)[0]
        return json.dumps(reply(doc)), None, None
    return transport


@pytest.fixture()
def rdb(sadb):  # noqa: F811
    sadb.run("flag_set", key="ai_kill_switch", value="false")
    sadb.run("budget_set", cap="50.00", warn="40.00", per_run="10.00")
    return sadb


def _source(db, name, stype, base, **kw):
    return srcs.create_source(db, srcs.SourceSpec(name, stype, base, kw.pop("authority", "official_portal"), retention_permitted=True,
                                                  enabled=True, **kw), META)


def _run(db, web, transport=None, **spec):
    sid = dsc.create_search(db, dsc.SearchSpec(**({"regions": [], "modules": [], "countries": []} | spec)))
    started = dsc.start_run(db, SETTINGS, search_id=sid)
    dsc.execute_run(db, SETTINGS, started["run_id"], None, fetch=web, transport=transport or model())
    return sid, db.one("run_get", id=started["run_id"])


def _sources_of(db, run_id):
    return {r[0]: (r[1], json.loads(r[2])) for r in db.pg.rows(
        f"SELECT s.name, rs.status, rs.issues::text FROM discovery_run_sources rs JOIN sources s ON s.id = rs.source_id "
        f"WHERE rs.run_id = '{run_id}'")}


def test_one_failed_target_makes_the_run_incomplete_not_no_results(rdb):
    _source(rdb, "Procurement search", "search_template", BASE, query_template=BASE + "/search?c={country}",
            country_coverage=["KE", "UG"], max_items=5)
    web = Web({BASE + "/search?c=KE": _listing([BASE + "/n/ke-1"]),
               BASE + "/n/ke-1": _page("Warehouse notice", "A logistics company opened a warehouse in Nairobi, Kenya."),
               BASE + "/search?c=UG": retrieval.RetrievalFailed("HTTP 503")})
    _, run = _run(rdb, web, geo_mode="countries", countries=["KE", "UG"])
    assert (run["status"], run["outcome"]) == ("partial", "incomplete")
    assert run["outcome"] != "no_relevant_results"
    assert run["counts"]["issue_counts"] == {"retrieval_failed": 1}
    issue = run["counts"]["issues"][0]
    assert issue["url"] == BASE + "/search?c=UG" and issue["country"] == "UG" and "HTTP 503" in issue["detail"]
    status, issues = _sources_of(rdb, run["id"])["Procurement search"]
    assert status == "partial" and [i["reason"] for i in issues] == ["retrieval_failed"]
    cov = run["counts"]["coverage"]
    assert cov["attempted"] == ["KE", "UG"] and cov["retrieved"] == ["KE"] and cov["extracted"] == ["KE"]
    assert "incomplete" in run["counts"]["flags"]
    # The failed run can be retried; the retry is a new run sharing the original's budget ceiling.
    retry = dsc.retry_run(rdb, SETTINGS, run["id"])
    assert rdb.one("run_get", id=retry["run_id"])["budget_root_id"] == run["id"]


def test_language_skips_and_rejected_only_extraction_are_explicit(rdb):
    _source(rdb, "French portal", "listing", BASE + "/fr/", country_coverage=["CI"], language="fr", local_language_permitted=False)
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["CI"], language="en")
    web = Web({BASE + "/fr/": _listing([BASE + "/fr/a"]),
               BASE + "/fr/a": _page("Appel d'offres", "Appel d'offres pour la représentation fret en Côte d'Ivoire.", lang="fr"),
               BASE + "/en/": _listing([BASE + "/en/a"]),
               BASE + "/en/a": _page("Notice", "Sample Airways is reviewing cargo representation options in Côte d'Ivoire.")})
    # The model proposes one claim whose quote is not in the document: the only claim is rejected.
    bad = {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports",
                                         "quote": "Sample Airways invites GSSA proposals for Côte d'Ivoire.", "fields": {}}]}
    _, run = _run(rdb, web, model(lambda doc: bad), geo_mode="country", countries=["CI"])
    assert (run["status"], run["outcome"]) == ("partial", "incomplete")
    assert run["counts"]["issue_counts"] == {"language_not_permitted": 1, "extraction_rejected": 1}
    by_source = _sources_of(rdb, run["id"])
    assert by_source["French portal"][0] == "partial"         # it answered, but its only document was not processed
    assert by_source["French portal"][1][0]["reason"] == "language_not_permitted" and "'fr'" in by_source["French portal"][1][0]["detail"]
    assert by_source["English portal"][1][0]["reason"] == "extraction_rejected"
    assert run["counts"]["coverage"]["extracted"] == []      # rejected-only is not coverage


def test_clean_run_with_nothing_relevant_is_the_only_no_relevant_results(rdb):
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"])
    web = Web({BASE + "/en/": _listing([BASE + "/en/a"]), BASE + "/en/a": _page("Notice", "Office closure notice for a holiday period.")})
    _, run = _run(rdb, web, geo_mode="country", countries=["KE"])
    assert (run["status"], run["outcome"]) == ("completed", "no_relevant_results") and run["counts"]["issues"] == []


# --------------------------------------------------------------------- budget


def _docs(n: int) -> tuple[dict, list[str]]:
    urls = [f"{BASE}/en/d{i}" for i in range(n)]
    pages = {BASE + "/en/": _listing(urls)} | {u: _page(f"Notice {i}", f"Routine notice number {i} about cargo operations in Kenya.")
                                               for i, u in enumerate(urls)}
    return pages, urls


def test_many_small_calls_cannot_exceed_the_run_ceiling(rdb):
    rdb.run("budget_set", cap="50.00", warn="40.00", per_run=str(PER_DOC * 2))   # the run may afford exactly two extractions
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"], max_items=5)
    pages, _ = _docs(5)
    calls: list = []
    _, run = _run(rdb, Web(pages), model(calls=calls), geo_mode="country", countries=["KE"])
    assert len(calls) == 2                                                   # the third call was never dispatched
    assert Decimal(run["plan"]["run_budget_cap_usd"]) == PER_DOC * 2 and Decimal(run["plan"]["estimated_cost_usd"]) == PER_DOC * 5
    assert run["counts"]["issue_counts"] == {"budget_run_cap": 3} and (run["status"], run["outcome"]) == ("partial", "incomplete")
    assert "run budget reached" in run["counts"]["issues"][0]["detail"]
    assert Decimal(rdb.pg.val(f"SELECT sum(actual_usd) FROM budget_reservations WHERE run_id = '{run['id']}'")) <= PER_DOC * 2
    assert run["actual_cost_usd"] == PER_DOC * 2


def test_retries_and_manual_reextraction_share_the_ceiling(rdb):
    from app.services.audit import RequestMeta as RM
    rdb.run("budget_set", cap="50.00", warn="40.00", per_run=str(PER_DOC * 2))
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"], max_items=3)
    pages, urls = _docs(3)
    calls: list = []
    sid, run = _run(rdb, Web(pages), model(calls=calls), geo_mode="country", countries=["KE"])
    assert len(calls) == 2 and run["status"] == "partial"
    # Retry: a new run, same ceiling, already spent -> no further call.
    retry = dsc.retry_run(rdb, SETTINGS, run["id"])
    dsc.execute_run(rdb, SETTINGS, retry["run_id"], None, fetch=Web(pages), transport=model(calls=calls))
    rrun = rdb.one("run_get", id=retry["run_id"])
    assert len(calls) == 2 and rrun["counts"]["issue_counts"].get("budget_run_cap") == 1
    # Manual re-extraction of the unextracted document is charged to the same run family and refused...
    doc = rdb.pg.val(f"SELECT id FROM source_documents WHERE original_url = '{urls[2]}' ORDER BY retrieved_at DESC LIMIT 1")
    meta = RM(ip="203.0.113.10", request_id="req-x", session_ref="sessreview003")
    out = rev.extract_document(rdb, SETTINGS, doc, meta)
    assert out["status"] == "budget_refused" and out["budget_scope"] == "run"
    # ...until a reviewer explicitly approves more for that run; the raise is audited.
    with pytest.raises(rev.ReviewRejected):
        rev.extract_document(rdb, SETTINGS, doc, meta, approve_additional_usd=Decimal("0"))
    import app.ai.extraction as extraction_mod
    orig = extraction_mod.messages_api
    extraction_mod.messages_api = model(calls=calls)
    try:
        out = rev.extract_document(rdb, SETTINGS, doc, meta, approve_additional_usd=PER_DOC)
    finally:
        extraction_mod.messages_api = orig
    assert out["status"] in ("no_claims", "extracted") and len(calls) == 3
    assert Decimal(rdb.pg.val(f"SELECT budget_cap_usd FROM discovery_runs WHERE id = '{run['id']}'")) == PER_DOC * 3
    assert rdb.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'run_budget_raised'") == "1"


def test_concurrent_reservations_respect_the_run_ceiling(rdb):
    rdb.run("budget_set", cap="50.00", warn="40.00", per_run="1.00")
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"], max_items=20)
    pages, _ = _docs(20)
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    run_id = dsc.start_run(rdb, SETTINGS, search_id=sid)["run_id"]
    rdb.pg.run(f"UPDATE discovery_runs SET budget_cap_usd = 0.25 WHERE id = '{run_id}'")
    granted: list = []
    barrier = threading.Barrier(12)

    def worker():
        barrier.wait()
        granted.append(rdb.scalar("budget_reserve_run", job=None, run=run_id, amount=Decimal("0.05"), at=None))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for g in granted if g is not None) == 5                      # 5 x 0.05 = the 0.25 ceiling, never more
    assert Decimal(rdb.pg.val(f"SELECT sum(reserved_usd) FROM budget_reservations WHERE run_id = '{run_id}'")) == Decimal("0.25")


def test_run_ceiling_spans_a_month_boundary(rdb):
    rdb.pg.run("INSERT INTO budget_periods VALUES ('2026-10-01', 50, 40, 10), ('2026-11-01', 50, 40, 10) "
               "ON CONFLICT (period_month) DO UPDATE SET cap_usd = 50, per_run_cap_usd = 10")
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"])
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    run_id = dsc.start_run(rdb, SETTINGS, search_id=sid)["run_id"]
    rdb.pg.run(f"UPDATE discovery_runs SET budget_cap_usd = 0.10 WHERE id = '{run_id}'")
    late_oct, early_nov = "2026-10-31T23:59:00+00:00", "2026-11-01T00:01:00+00:00"
    assert rdb.scalar("budget_reserve_run", job=None, run=run_id, amount=Decimal("0.06"), at=late_oct) is not None
    # A new month resets the MONTHLY total, not the run's cumulative ceiling.
    assert rdb.scalar("budget_reserve_run", job=None, run=run_id, amount=Decimal("0.06"), at=early_nov) is None
    assert rdb.scalar("budget_reserve_run", job=None, run=run_id, amount=Decimal("0.04"), at=early_nov) is not None
    months = rdb.pg.rows(f"SELECT period_month::text FROM budget_reservations WHERE run_id = '{run_id}' ORDER BY created_at")
    assert months == [["2026-10-01"], ["2026-11-01"]]
    # The kill switch still overrides everything.
    rdb.run("flag_set", key="ai_kill_switch", value="true")
    rdb.pg.run(f"UPDATE discovery_runs SET budget_cap_usd = 5 WHERE id = '{run_id}'")
    assert rdb.scalar("budget_reserve_run", job=None, run=run_id, amount=Decimal("0.01"), at=early_nov) is None


# --------------------------------------------------------------------- estimates


def test_multi_country_low_item_limit_cannot_outrun_its_priced_bound(rdb):
    countries = ["KE", "UG", "TZ"]
    _source(rdb, "Procurement search", "search_template", BASE, query_template=BASE + "/search?c={country}",
            country_coverage=countries, max_items=1)
    pages: dict = {}
    for c in countries:
        links = [f"{BASE}/n/{c}-{i}" for i in range(4)]
        pages[f"{BASE}/search?c={c}"] = _listing(links)
        pages |= {u: _page("Notice", f"Routine cargo notice {u} for {COUNTRIES[c][0]}.") for u in links}
    calls: list = []
    sid = dsc.create_search(rdb, dsc.SearchSpec("countries", countries, [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    p = started["plan"]
    assert p["max_documents"] == 3 and p["sources"][0]["max_documents"] == 3     # one item per country query x 3 queries
    assert Decimal(p["estimated_cost_usd"]) == PER_DOC * 3 and p["estimate_is_upper_bound"] is True
    # Tighten the approved bound below what the source would yield: the executor stops at the bound and lists the rest.
    rdb.pg.run(f"UPDATE discovery_runs SET plan = jsonb_set(plan, '{{sources,0,max_documents}}', '2') WHERE id = '{started['run_id']}'")
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=Web(pages), transport=model(calls=calls))
    run = rdb.one("run_get", id=started["run_id"])
    material = {k: v for k, v in run["counts"]["issue_counts"].items() if k in dsc.MATERIAL_ISSUES}
    # Paid extractions never exceed the bound (2). Every other relevant link (1 over the bound, 3 more on each of the
    # three results pages) is listed AND queued for the next run (amendments item 5), so nothing is silently dropped.
    assert len(calls) == 2 and material == {"not_fetched_limit": 10}
    assert run["counts"]["queue"]["pending"] == 10
    assert run["status"] == "partial"


# --------------------------------------------------------------------- publication dates


def _feed(items: list[tuple[str, str | None]]) -> bytes:
    xs = "".join(f"<item><title>Item</title><link>{u}</link>" + (f"<pubDate>{d}</pubDate>" if d else "") + "</item>" for u, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Wire</title>{xs}</channel></rss>'.encode()


def test_rss_date_is_kept_with_provenance_and_unknown_dates_are_labelled(rdb):
    _source(rdb, "Cargo wire", "rss", BASE + "/feed.xml", authority="trade_press", global_coverage=True)
    a, b, c = BASE + "/n/a", BASE + "/n/b", BASE + "/n/c"
    pages = {BASE + "/feed.xml": (_feed([(a, "Mon, 19 Oct 2026 09:00:00 GMT"), (b, None), (c, "Tue, 03 Mar 2026 09:00:00 GMT")]),
                                  "application/rss+xml"),
             a: _page("Hub", "Example Air opens a cargo hub in Nairobi, Kenya."),                      # no date on the page
             b: _page("Office", "Example Air opens a sales office in Mombasa, Kenya."),                # no date anywhere
             c: _page("Old", "Example Air closed its Kisumu office in Kenya.")}                        # feed date out of range
    _, run = _run(rdb, Web(pages), geo_mode="country", countries=["KE"], date_from=datetime(2026, 10, 1).date(),
                  date_to=datetime(2026, 10, 31).date())
    row = rdb.pg.rows(f"SELECT published_at AT TIME ZONE 'UTC', published_at_source FROM source_documents WHERE original_url = '{a}'")
    assert row == [["2026-10-19 09:00:00", "feed"]]
    assert rdb.pg.rows(f"SELECT published_at, published_at_source FROM source_documents WHERE original_url = '{b}'") == [["", ""]]   # NULL, NULL
    assert rdb.pg.val(f"SELECT count(*) FROM source_documents WHERE original_url = '{c}'") == "0"   # excluded by its feed date
    assert run["counts"]["skipped_out_of_range"] == 1 and run["counts"]["date_unknown"] == 1
    # include_unknown (default): processed, counted, and never presented as within the period
    assert run["status"] == "completed"


def test_strict_date_filter_lists_unknown_dates_as_excluded(rdb):
    _source(rdb, "Cargo wire", "rss", BASE + "/feed.xml", authority="trade_press", global_coverage=True)
    b = BASE + "/n/b"
    pages = {BASE + "/feed.xml": (_feed([(b, None)]), "application/rss+xml"), b: _page("Office", "Example Air opens an office in Kenya.")}
    calls: list = []
    _, run = _run(rdb, Web(pages), model(calls=calls), geo_mode="country", countries=["KE"], date_from=datetime(2026, 10, 1).date(),
                  date_filter="strict")
    assert calls == [] and run["counts"]["issue_counts"] == {"date_unknown_excluded": 1}
    assert run["counts"]["issues"][0]["url"] == b


def test_match_for_an_undated_signal_carries_a_date_note(rdb):
    q = "Example Air has signed a partnership agreement with a cargo handler in Kenya."
    reply = {"language": "en", "claims": [{"claim_type": "partnership", "stance": "supports", "quote": q,
                                           "fields": {"organisation": {"value": "Example Air", "quote": q},
                                                      "country": {"value": "Kenya", "quote": q}}}]}
    _source(rdb, "Cargo wire", "rss", BASE + "/feed.xml", authority="trade_press", global_coverage=True)
    b = BASE + "/n/b"
    pages = {BASE + "/feed.xml": (_feed([(b, None)]), "application/rss+xml"), b: _page("Partnership", q)}
    _, run = _run(rdb, Web(pages), model(lambda doc: reply), geo_mode="country", countries=["KE"],
                  date_from=datetime(2026, 10, 1).date())
    results = rdb.all("run_results", run=run["id"])
    assert len(results) == 1
    assert results[0]["match"]["date_note"].startswith("publication date unknown")


# --------------------------------------------------------------------- resumable coverage


def test_capped_worldwide_runs_resume_and_expose_what_remains(rdb):
    cover = sorted(COUNTRIES)[:dsc.MAX_COUNTRY_QUERIES_PER_SOURCE + 10]
    _source(rdb, "Global search", "search_template", BASE, query_template=BASE + "/search?c={country}", country_coverage=cover,
            max_items=1)
    pages = {f"{BASE}/search?c={c}": _listing([]) for c in cover}
    sid, run1 = _run(rdb, Web(pages), geo_mode="worldwide")
    cap = dsc.MAX_COUNTRY_QUERIES_PER_SOURCE
    assert run1["counts"]["coverage"]["attempted"] == cover[:cap]
    assert run1["counts"]["not_searched_countries"] == cover[cap:]
    assert (run1["status"], run1["outcome"]) == ("partial", "incomplete")
    # The next run of the same search continues where the first stopped.
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    web = Web(pages)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model())
    run2 = rdb.one("run_get", id=started["run_id"])
    assert web.fetched[:10] == [f"{BASE}/search?c={c}" for c in cover[cap:]]
    assert set(cover[cap:]) <= set(run2["counts"]["coverage"]["attempted"])
    assert len(run2["counts"]["coverage"]["attempted"]) == cap
    union = set(run1["counts"]["coverage"]["attempted"]) | set(run2["counts"]["coverage"]["attempted"])
    assert union == set(cover)


# --------------------------------------------------------------------- independent review of this work (26 Oct 2026)


def test_prompt_size_is_a_true_upper_bound_for_any_script():
    """Amended: a section never exceeds the byte budget, and an oversized text is refused, never cut."""
    from app.domain import ai_guard as ag
    from app.domain import sections as sec
    budget = ai.MAX_INPUT_TOKENS - ai.MESSAGE_OVERHEAD_TOKENS
    for text in ("货运总代理招标" * 10_000, "การประมูล" * 10_000, "GSSA tender " * 10_000):
        parts = sec.split(text, ai.SECTION_BYTES)
        assert sec.covers_everything(text, parts) and len(parts) > 1
        for part in parts:
            system, user = ag.build_prompt(part.text, max_chars=len(part.text), max_bytes=budget)
            assert len(system.encode()) + len(user.encode()) <= budget
        with pytest.raises(ag.DocumentTooLong):
            ag.build_prompt(text, max_chars=len(text), max_bytes=budget)


def test_source_disabled_after_planning_makes_the_run_incomplete(rdb):
    sid_src = _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"])
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    srcs.set_enabled(rdb, sid_src, False, META)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=Web({}), transport=model())
    run = rdb.one("run_get", id=started["run_id"])
    assert (run["status"], run["outcome"]) == ("partial", "incomplete") and run["counts"]["issue_counts"] == {"source_disabled": 1}


def test_rejected_only_document_stays_incomplete_on_later_runs(rdb):
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"])
    web = Web({BASE + "/en/": _listing([BASE + "/en/a"]), BASE + "/en/a": _page("Notice", "Example Air reviews cargo options in Kenya.")})
    bad = {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports",
                                         "quote": "Example Air invites GSSA proposals for Kenya now.", "fields": {}}]}
    sid, run1 = _run(rdb, web, model(lambda doc: bad), geo_mode="country", countries=["KE"])
    assert run1["counts"]["issue_counts"] == {"extraction_rejected": 1}
    calls: list = []
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(calls=calls))
    run2 = rdb.one("run_get", id=started["run_id"])
    assert calls == []                                                       # not re-extracted or re-charged
    assert run2["counts"]["issue_counts"] == {"extraction_rejected": 1} and run2["status"] == "partial"


def test_feed_date_reaches_a_document_stored_earlier_without_one(rdb):
    _source(rdb, "Cargo wire", "rss", BASE + "/feed.xml", authority="trade_press", global_coverage=True)
    a = BASE + "/n/a"
    page = _page("Hub", "Example Air opens a cargo hub in Nairobi, Kenya.")
    _run(rdb, Web({BASE + "/feed.xml": (_feed([(a, None)]), "application/rss+xml"), a: page}), geo_mode="country", countries=["KE"])
    assert rdb.pg.val(f"SELECT published_at FROM source_documents WHERE original_url = '{a}'") == ""
    _run(rdb, Web({BASE + "/feed.xml": (_feed([(a, "Mon, 19 Oct 2026 09:00:00 GMT")]), "application/rss+xml"), a: page}),
         geo_mode="country", countries=["KE"])
    assert rdb.pg.rows(f"SELECT published_at AT TIME ZONE 'UTC', published_at_source FROM source_documents WHERE original_url = '{a}'") == \
        [["2026-10-19 09:00:00", "feed"]]


def test_feed_items_beyond_the_item_limit_are_listed(rdb):
    _source(rdb, "Cargo wire", "rss", BASE + "/feed.xml", authority="trade_press", global_coverage=True, max_items=1)
    a, b = BASE + "/n/a", BASE + "/n/b"
    pages = {BASE + "/feed.xml": (_feed([(a, None), (b, None)]), "application/rss+xml"), a: _page("A", "Kenya cargo notice A."),
             b: _page("B", "Kenya cargo notice B.")}
    _, run = _run(rdb, Web(pages), geo_mode="country", countries=["KE"])
    assert run["counts"]["issue_counts"] == {"not_fetched_limit": 1} and run["counts"]["issues"][0]["url"] == b
    assert run["status"] == "partial"


def test_cursor_does_not_skip_a_failed_country(rdb):
    cover = sorted(COUNTRIES)[:dsc.MAX_COUNTRY_QUERIES_PER_SOURCE + 10]
    _source(rdb, "Global search", "search_template", BASE, query_template=BASE + "/search?c={country}", country_coverage=cover, max_items=1)
    pages = {f"{BASE}/search?c={c}": _listing([]) for c in cover}
    failed = cover[5]
    pages[f"{BASE}/search?c={failed}"] = retrieval.RetrievalFailed("HTTP 503")
    sid, _ = _run(rdb, Web(pages), geo_mode="worldwide")
    pages[f"{BASE}/search?c={failed}"] = _listing([])
    web = Web(pages)
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model())
    assert web.fetched[0] == f"{BASE}/search?c={failed}"                  # resumes at the failed country, not past it


def test_retry_of_a_run_planned_without_ai_gets_an_approved_ceiling(rdb):
    _source(rdb, "English portal", "listing", BASE + "/en/", country_coverage=["KE"])
    pages, _ = _docs(1)
    no_ai = config.load({"ENVIRONMENT": "test", "DATABASE_URL": "postgresql://x@y/z"})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, no_ai, search_id=sid)
    dsc.execute_run(rdb, no_ai, started["run_id"], None, fetch=Web(pages))
    run = rdb.one("run_get", id=started["run_id"])
    assert run["counts"]["issue_counts"] == {"extraction_not_run": 1} and run["plan"]["run_budget_cap_usd"] is None
    calls: list = []
    retry = dsc.retry_run(rdb, SETTINGS, run["id"])
    assert Decimal(rdb.one("run_get", id=run["id"])["budget_cap_usd"]) == Decimal(retry["plan"]["run_budget_cap_usd"]) > 0   # from the retry's plan
    rdb.pg.run("UPDATE source_documents SET extraction_status = 'not_connected'")
    dsc.execute_run(rdb, SETTINGS, retry["run_id"], None, fetch=Web(pages), transport=model(calls=calls))
    assert len(calls) == 1


def test_parallel_fit_ticks_do_not_duplicate_reassessments(rdb):
    from app.services import fit_service
    rdb.pg.run("INSERT INTO organisations (id, canonical_name, kind) VALUES ('00000000-0000-0000-0000-0000000000a2', 'Coastal Handling', 'other')")
    cand = rdb.scalar("network_insert", kind="partner", org="00000000-0000-0000-0000-0000000000a2", territory=None, service=None, title="Coastal")
    cid = rdb.pg.val("INSERT INTO claims (claim_type, claim_key, subject_organisation_id, value, status) VALUES ('partnership', 'k1', "
                     "'00000000-0000-0000-0000-0000000000a2', '{\"kind\": \"serves_territory\", \"value\": \"KE\"}', 'supported') RETURNING id")
    fit_service.assess(rdb, str(cand), "00000000-0000-0000-0000-0000000000a2", [["KE", "GSSA"]], META)
    rdb.pg.run(f"UPDATE claims SET status = 'contradicted' WHERE id = '{cid}'")
    out: list = []
    ts = [threading.Thread(target=lambda: out.append(fit_service.reassess_stale(rdb))) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert rdb.pg.val(f"SELECT count(*) FROM fit_assessments WHERE network_candidate_id = '{cand}'") == "2"

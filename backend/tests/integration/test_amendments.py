"""Amendments of 26 Oct 2026, end to end on real PostgreSQL (production adapter; synthetic pages and a
simulated Messages-API transport, as in test_review3_regressions):

1. complete reading of long documents in sections, evidence locations, resume, never "checked" when partly read;
4. a document that announces an opportunity and says it has ended is shown as contradictory, not open;
5. relevant links beyond the limits are queued and read first by the next run, for every geography mode;
6. deadlines migrated from earlier versions are taken out of "exact" status and revalidated against evidence.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai import extraction as ai
from app.domain import retrieval
from app.domain import sections as sec
from app.domain.field_validation import FieldClaim
from app.services import deadline_revalidation as dr
from app.services import discovery as dsc
from app.services import ingestion as ing
from app.services import review_service as rev
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_review3_regressions import BASE, PER_DOC, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401

UTC = timezone.utc
META = RequestMeta(ip="203.0.113.10", request_id="req-am", session_ref="sessamend0001")
SQL = Path(__file__).resolve().parents[2] / "migrations" / "sql"

ANNOUNCE = "Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya."
LATE = "Tender reference EXA-CGO-2027-077. Proposals are due on 30 November 2026."


def _long_page() -> tuple[bytes, str]:
    """A long notice: the announcement at the start, the reference and deadline only near the end."""
    filler = "\n\n".join(f"Section {i}. General conditions of contract, clause {i}: the provider shall comply with all applicable rules."
                         * 3 for i in range(260))
    text_body = f"{ANNOUNCE}\n\n{filler}\n\n{LATE}"
    html = ("<html lang='en'><head><title>RFP</title></head><body><main>"
            + "".join(f"<p>{p}</p>" for p in text_body.split("\n\n")) + "</main></body></html>").encode()
    return html, text_body


def _reply_for_sections(doc: str) -> dict:
    claims = []
    if ANNOUNCE in doc:
        claims.append({"claim_type": "gssa_tender", "stance": "supports", "quote": ANNOUNCE,
                       "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE}, "country": {"value": "Kenya", "quote": ANNOUNCE},
                                  "service": {"value": "GSSA", "quote": ANNOUNCE}, "status": {"value": "open", "quote": ANNOUNCE}}})
    if "EXA-CGO-2027-077" in doc:
        claims.append({"claim_type": "tender_deadline", "stance": "supports", "quote": LATE,
                       "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE} if ANNOUNCE in doc else {"value": "", "quote": ""},
                                  "tender_ref": {"value": "EXA-CGO-2027-077", "quote": "Tender reference EXA-CGO-2027-077."},
                                  "deadline": {"value": "2026-11-30", "quote": "Proposals are due on 30 November 2026."}}})
        for c in claims:
            c["fields"] = {k: v for k, v in c["fields"].items() if v["value"]}
    return {"language": "en", "claims": claims}


# ===================================================================== 1. complete reading


def test_a_long_document_is_read_in_full_with_evidence_locations(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, full = _long_page()
    sections = sec.split(full, ai.SECTION_BYTES)
    assert len(sections) >= 3
    calls: list = []
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    rdb.run("budget_set", cap="50.00", warn="40.00", per_run="10.00")
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_reply_for_sections, calls))
    run = rdb.one("run_get", id=started["run_id"])
    assert len(calls) == len(sections)                                          # every section read once
    doc = rdb.one("document_review_get", id=rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'"))
    assert doc["extraction_status"] == "extracted" and doc["read_progress"]["done"] == list(range(len(sections)))
    # The reference and deadline from the LAST section were found (nothing silently truncated) ...
    assert rdb.pg.val("SELECT count(*) FROM claims WHERE tender_ref = 'EXACGO2027077' OR tender_ref = 'EXA-CGO-2027-077'") != "0"
    # ... and each claim records where its quote sits in the full text.
    refs = [r[0] for r in rdb.pg.rows("SELECT page_ref FROM claim_evidence WHERE page_ref IS NOT NULL")]
    late = full.index(LATE)
    assert any(r == f"chars {late}-{late + len(LATE)}" for r in refs), refs
    assert run["counts"]["issue_counts"].get("document_partially_read") is None


def test_budget_stop_mid_document_is_incomplete_and_resumes(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, full = _long_page()
    n = len(sec.split(full, ai.SECTION_BYTES))
    rdb.run("budget_set", cap="50.00", warn="40.00", per_run=str(PER_DOC * 2))      # two sections' worth
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    calls: list = []
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_reply_for_sections, calls))
    run = rdb.one("run_get", id=started["run_id"])
    doc_id = rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'")
    doc = rdb.one("document_review_get", id=doc_id)
    assert len(calls) == 2 and doc["extraction_status"] == "incomplete" and doc["read_progress"]["done"] == [0, 1]
    assert doc["extraction_status"] not in ("no_claims", "extracted")                # never "checked" or "nothing found"
    assert (run["status"], run["outcome"]) == ("partial", "incomplete")
    assert run["counts"]["issue_counts"] == {"document_partially_read": 1}
    assert f"read 2 of {n}" in run["counts"]["issues"][0]["detail"]
    assert run["counts"]["queue"]["pending"] == 1                                     # the document waits in the queue
    # A reviewer approves more for that run and continues reading: only the unread sections are read.
    calls2: list = []
    out = rev.extract_document(rdb, SETTINGS, doc_id, META, approve_additional_usd=PER_DOC * n, transport=model(_reply_for_sections, calls2))
    assert len(calls2) == n - 2 and out["read"] == {"sections_read": n, "sections_total": n, "complete": True}
    assert rdb.one("document_review_get", id=doc_id)["extraction_status"] == "extracted"


def test_a_failed_section_stops_reading_and_is_retried_not_skipped(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, full = _long_page()
    n = len(sec.split(full, ai.SECTION_BYTES))
    seen: list = []

    def flaky(_s, _sys, user):
        seen.append(user)
        if len(seen) == 2:
            raise RuntimeError("provider unreachable: TimeoutError")
        return json.dumps(_reply_for_sections(user.split("<document>\n", 1)[-1])), None, None

    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=flaky)
    doc_id = rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'")
    assert rdb.one("document_review_get", id=doc_id)["read_progress"]["done"] == [0]
    # The next run of the same search resumes at section 2 (the failed one) and finishes.
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=flaky)
    assert len(seen) == 1 + 1 + (n - 1)
    assert rdb.one("document_review_get", id=doc_id)["extraction_status"] == "extracted"
    assert rdb.one("run_get", id=started["run_id"])["counts"]["queue"]["pending"] == 0


def test_manual_extraction_never_uses_the_excerpt(rdb):  # noqa: F811
    sid_src = _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    rdb.pg.run(f"UPDATE sources SET retention_permitted = false WHERE id = '{sid_src}'")
    html, _full = _long_page()
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    no_ai = dataclasses.replace(SETTINGS, anthropic_api_key="")
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, no_ai, search_id=sid)
    dsc.execute_run(rdb, no_ai, started["run_id"], None, fetch=web)
    doc_id = rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'")
    assert rdb.pg.val(f"SELECT body_text IS NULL FROM source_documents WHERE id = '{doc_id}'") == "t"
    calls: list = []
    rdb.pg.run(f"UPDATE discovery_runs SET budget_cap_usd = 10 WHERE id = '{started['run_id']}'")
    out = rev.extract_document(rdb, SETTINGS, doc_id, META, fetch=web, transport=model(_reply_for_sections, calls))
    assert out["read"]["complete"] and len(calls) == out["read"]["sections_total"] > 1          # the page was fetched again in full
    changed = Web({BASE + "/rfp/77": _page("RFP", "A different page now.")})
    rdb.pg.run(f"UPDATE source_documents SET extraction_status = 'incomplete', read_progress = NULL WHERE id = '{doc_id}'")
    with pytest.raises(rev.ReviewRejected) as exc:
        rev.extract_document(rdb, SETTINGS, doc_id, META, fetch=changed, transport=model(_reply_for_sections, calls))
    assert exc.value.status == 409 and "changed" in str(exc.value)


# ===================================================================== 4. contradictions


def test_self_contradicting_notice_is_not_shown_as_open(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    body = f"{ANNOUNCE} {LATE}\n\nUpdate 25 October 2026: this tender has been cancelled."
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/78"]), BASE + "/rfp/78": _page("RFP", body.replace("\n\n", " "))})
    reply = {"language": "en", "claims": [{"claim_type": "gssa_tender", "stance": "supports", "quote": ANNOUNCE,
                                           "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE},
                                                      "country": {"value": "Kenya", "quote": ANNOUNCE},
                                                      "status": {"value": "open", "quote": ANNOUNCE},
                                                      "tender_ref": {"value": "EXA-CGO-2027-077", "quote": "Tender reference EXA-CGO-2027-077."}}}]}
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(lambda d: reply))
    assert rdb.pg.val("SELECT status_contradiction FROM source_documents WHERE original_url LIKE '%/rfp/78'").startswith("the source announces")
    opp = rdb.pg.val("SELECT id FROM opportunities LIMIT 1")
    status = rdb.pg.val(f"SELECT tender_status FROM opportunities WHERE id = '{opp}'")
    assert status == "contradictory" and status not in ("open", "revised")
    live = rdb.pg.rows(f"SELECT result, rationale FROM qualification_checks WHERE opportunity_id = '{opp}' AND check_code = 'live_status'")
    assert live and live[0][0] == "review_required" and "contradictory source" in live[0][1]
    f = rdb.pg.rows("SELECT support, reason FROM claim_fields WHERE field = 'status'")
    assert f == [["review_required", f[0][1]]] and "contradictory" in f[0][1]


# ===================================================================== 5. link queue, every geography mode


@pytest.mark.parametrize("mode,countries,regions", [
    ("country", ["KE"], []), ("countries", ["KE", "UG"], []), ("region", [], ["EAC"]), ("worldwide", [], []),
])
def test_relevant_links_beyond_the_limit_are_queued_and_resumed(rdb, mode, countries, regions):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/notices/", country_coverage=["KE", "UG"], max_items=2)
    links = [f"{BASE}/notices/{i}" for i in range(5)]
    nav = [f"{BASE}/about", f"{BASE}/contact", f"{BASE}/privacy"]
    nav_html = "".join(f'<a href="{u}">{t}</a>' for u, t in zip(nav, ("About us", "Contact", "Privacy policy"), strict=True))
    listing = _listing(links).replace(b"<main>", f"<header>{nav_html}</header><main>".encode()).replace(
        b"</main>", f"</main><div>{nav_html}</div>".encode())
    pages = {BASE + "/notices/": listing,
             **{u: _page(f"Notice {i}", f"Routine cargo notice {i} for Kenya.") for i, u in enumerate(links)}}
    web = Web(pages)
    sid = dsc.create_search(rdb, dsc.SearchSpec(mode, countries, regions, []))
    statuses, fetched = [], []
    for _ in range(3):
        started = dsc.start_run(rdb, SETTINGS, search_id=sid)
        web.fetched.clear()
        dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model())
        run = rdb.one("run_get", id=started["run_id"])
        statuses.append((run["status"], run["counts"]["queue"]["pending"]))
        fetched.append([u for u in web.fetched if u in links])
    # run 1 reads 2 and queues 3; run 2 reads the 2 oldest queued first; run 3 reads the last one: complete.
    assert statuses == [("partial", 3), ("partial", 1), ("completed", 0)], statuses
    assert fetched[0] == links[:2] and fetched[1] == links[2:4] and fetched[2][0] == links[4]   # then a re-check of a read link
    assert not any(u in web.fetched for u in nav)                                    # navigation never fetched as an article


def test_a_link_that_keeps_failing_is_given_up_and_listed(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/notices/", country_coverage=["KE"], max_items=5)
    pages = {BASE + "/notices/": _listing([f"{BASE}/notices/bad"]), f"{BASE}/notices/bad": retrieval.RetrievalFailed("HTTP 503")}
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    for _ in range(dsc.MAX_LINK_ATTEMPTS):
        started = dsc.start_run(rdb, SETTINGS, search_id=sid)
        dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=Web(pages), transport=model())
    run = rdb.one("run_get", id=started["run_id"])
    assert run["counts"]["queue"]["gave_up"] == 1 and run["status"] == "partial"
    assert "given up" in run["counts"]["issues"][0]["detail"]


# ===================================================================== 6. migrated deadlines


def _legacy(db, text: str, value: str, stored_utc: str, tz: str | None, url: str):
    """A claim and opportunity in the shape earlier versions stored (deadline_info NULL, an instant in deadline_utc)."""
    src = db.portal if hasattr(db, "portal") else None
    if src is None:
        sid = _source(db, "Example Air procurement portal", "web_page", "https://tenders.example-air.example", country_coverage=["KE"])
        db.portal = ing.SourceInfo(sid, "portal", "official_portal", "https://tenders.example-air.example", True)
    q = ANNOUNCE
    p = ing.ClaimProposal("gssa_tender", q, {"airline": FieldClaim("Example Air", q), "country": FieldClaim("Kenya", q),
                                              "status": FieldClaim("open", q), "tender_ref": FieldClaim(url[-3:], url[-3:]),
                                              "deadline": FieldClaim(value, text)}, assessed_by="human")
    r = ing.ingest(db, ing.IncomingDocument(db.portal, url, url, f"{q} Reference {url[-3:]}. {text}",
                                            published_at=datetime(2026, 10, 1, tzinfo=UTC)), [p], now=datetime(2026, 10, 26, tzinfo=UTC))
    # Rewrite into the legacy shape.
    db.pg.run(f"UPDATE claims SET deadline_utc = '{stored_utc}', deadline_source_tz = {repr(tz) if tz else 'NULL'}, deadline_info = NULL "
              f"WHERE id IN (SELECT claim_id FROM claim_evidence WHERE source_document_id = '{r.document_id}')")
    db.legacy_docs = getattr(db, "legacy_docs", {}) | {url[-3:]: r.document_id}
    db.pg.run(f"UPDATE opportunities SET deadline_utc = '{stored_utc}', deadline_info = NULL WHERE id = '{r.opportunity_id}'")
    return r.opportunity_id


def test_migrated_midnight_deadlines_are_not_exact_and_are_revalidated(rdb):  # noqa: F811
    o_date = _legacy(rdb, "Proposals are due on 30 November 2026.", "2026-11-30T00:00:00Z", "2026-11-30 00:00:00+00", "Africa/Nairobi",
                     "https://tenders.example-air.example/rfp/a01")
    o_time = _legacy(rdb, "Proposals are due on 30 November 2026 at 17:00 EAT.", "2026-11-30T17:00", "2026-11-30 14:00:00+00", "EAT",
                     "https://tenders.example-air.example/rfp/a02")
    o_noquote = _legacy(rdb, "Proposals are due soon.", "2026-12-15T00:00:00Z", "2026-12-15 00:00:00+00", None,
                        "https://tenders.example-air.example/rfp/a03")
    rdb.pg.run(f"UPDATE claim_fields SET quote = NULL WHERE field = 'deadline' AND source_document_id = '{rdb.legacy_docs['a03']}'")
    rdb.pg.run("INSERT INTO opportunities (module, dedup_key, title, deadline_utc) VALUES "
               "('airline_representation', 'manual-1', 'Manual record', '2026-12-01 00:00:00+00')")
    # Apply the migration's legacy step (idempotent) exactly as `alembic upgrade` does.
    rdb.pg.run((SQL / "wfc_0004_legacy_deadlines.sql").read_text())
    for oid in (o_date, o_noquote):
        info = rdb.one("opportunity_scope", id=oid)
        assert info["deadline_utc"] is None and info["deadline_info"]["precision"] == "date"   # midnight no longer exact
    pre = rdb.one("opportunity_scope", id=o_time)                                             # no legacy value stays exact
    assert pre["deadline_utc"] is None and pre["deadline_info"]["precision"] == "local_time"
    assert pre["deadline_info"]["local_time"] == "17:00" and pre["deadline_info"]["assumed_zone"] == "EAT"
    assert rdb.pg.val("SELECT count(*) FROM jobs WHERE job_type = 'deadline_revalidation'") == "1"
    report = dr.revalidate(rdb, now=datetime(2026, 10, 26, tzinfo=UTC))
    assert report["claims"] == 3 and report["date"] == 1 and report["instant"] == 1 and report["unverified"] == 1
    d = rdb.one("opportunity_scope", id=o_date)
    assert d["deadline_utc"] is None and d["deadline_info"]["precision"] == "date" and d["deadline_info"]["day"] == "2026-11-30"
    t = rdb.one("opportunity_scope", id=o_time)
    assert t["deadline_utc"] == datetime(2026, 11, 30, 14, tzinfo=UTC) and t["deadline_info"]["zone"] == "EAT"
    n = rdb.one("opportunity_scope", id=o_noquote)
    assert n["deadline_utc"] is None and any("unverified" in x for x in n["deadline_info"]["notes"])
    m = rdb.pg.rows("SELECT deadline_utc, deadline_info->>'precision', deadline_info->>'verified' FROM opportunities WHERE dedup_key = 'manual-1'")
    assert m == [["", "date", "false"]]
    assert dr.revalidate(rdb)["claims"] == 0                                          # idempotent


def test_fresh_installs_queue_no_revalidation_job(rdb):  # noqa: F811
    assert rdb.pg.val("SELECT count(*) FROM jobs WHERE job_type = 'deadline_revalidation'") == "0"


def test_estimate_assumes_one_section_and_the_ceiling_still_holds(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"], max_items=1)
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    p = dsc.start_run(rdb, SETTINGS, search_id=sid)["plan"]
    assert Decimal(p["estimated_cost_usd"]) == PER_DOC and "section" in p["estimate_basis"]


# ===================================================================== independent review of the amendments (regressions)


def test_a_deadline_in_a_later_section_attaches_to_the_tender_from_section_one(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, full = _long_page()
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})

    def reply(doc: str) -> dict:          # the deadline claim names no reference and no airline: it relies on the anchor
        claims = []
        if ANNOUNCE in doc:
            claims.append({"claim_type": "gssa_tender", "stance": "supports", "quote": ANNOUNCE,
                           "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE}, "country": {"value": "Kenya", "quote": ANNOUNCE},
                                      "status": {"value": "open", "quote": ANNOUNCE}}})
        if "Proposals are due on 30 November 2026." in doc:
            claims.append({"claim_type": "tender_deadline", "stance": "supports", "quote": "Proposals are due on 30 November 2026.",
                           "fields": {"deadline": {"value": "2026-11-30", "quote": "Proposals are due on 30 November 2026."}}})
        return {"language": "en", "claims": claims}

    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply))
    assert rdb.pg.val("SELECT count(*) FROM opportunities") == "1"
    info = rdb.one("opportunity_scope", id=rdb.pg.val("SELECT id FROM opportunities LIMIT 1"))["deadline_info"]
    assert info is not None and info["day"] == "2026-11-30"                     # the tender received its deadline


def test_a_document_read_by_an_older_version_is_read_again_in_full(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, full = _long_page()
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_reply_for_sections))
    # Make it look like an earlier version's work: marked read, but no record of the sections read.
    rdb.pg.run("UPDATE source_documents SET read_progress = NULL, extraction_status = 'no_claims' WHERE original_url LIKE '%/rfp/77'")
    rdb.pg.run("UPDATE discovery_link_queue SET status = 'done'")
    calls: list = []
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_reply_for_sections, calls))
    assert len(calls) == len(sec.split(full, ai.SECTION_BYTES))
    assert rdb.pg.val("SELECT extraction_status FROM source_documents WHERE original_url LIKE '%/rfp/77'") == "extracted"


def test_a_section_that_keeps_failing_is_given_up_not_recharged_every_run(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, _full = _long_page()
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    calls: list = []

    def broken(_s, _sys, user):
        calls.append(user)
        return "this is not JSON", None, None        # the output is quarantined every time

    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    for _ in range(5):
        started = dsc.start_run(rdb, SETTINGS, search_id=sid)
        dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=broken)
    assert len(calls) == 3                                                        # three attempts, then given up
    run = rdb.one("run_get", id=started["run_id"])
    assert run["counts"]["queue"]["gave_up"] == 1 and run["status"] == "partial"
    doc = rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'")
    assert rdb.one("document_review_get", id=doc)["extraction_status"] == "failed"
    assert doc in [str(d["id"]) for d in rdb.all("review_documents", limit=50)]   # surfaced to a person


def test_partly_read_documents_are_in_the_review_queue_and_stay_incomplete_after_a_manual_claim(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, _full = _long_page()
    rdb.run("budget_set", cap="50.00", warn="40.00", per_run=str(PER_DOC))
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_reply_for_sections))
    doc = rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'")
    assert doc in [str(d["id"]) for d in rdb.all("review_documents", limit=50)]
    rev.add_claim(rdb, doc, claim_type="gssa_tender", quote=ANNOUNCE, fields={"airline": {"value": "Example Air", "quote": ANNOUNCE}},
                  meta=META, settings=SETTINGS)
    assert rdb.one("document_review_get", id=doc)["extraction_status"] == "incomplete"


def test_a_reference_cited_only_at_the_end_joins_the_documents_tender(rdb):  # noqa: F811
    """The announcement (section 1) has no reference; "Tender reference ... Proposals are due ..." comes last."""
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    html, _full = _long_page()
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": html})

    def reply(doc: str) -> dict:
        claims = []
        if ANNOUNCE in doc:
            claims.append({"claim_type": "gssa_tender", "stance": "supports", "quote": ANNOUNCE,
                           "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE}, "country": {"value": "Kenya", "quote": ANNOUNCE},
                                      "status": {"value": "open", "quote": ANNOUNCE}}})
        if "EXA-CGO-2027-077" in doc:
            claims.append({"claim_type": "tender_deadline", "stance": "supports", "quote": "Proposals are due on 30 November 2026.",
                           "fields": {"tender_ref": {"value": "EXA-CGO-2027-077", "quote": "Tender reference EXA-CGO-2027-077."},
                                      "deadline": {"value": "2026-11-30", "quote": "Proposals are due on 30 November 2026."}}})
        return {"language": "en", "claims": claims}

    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply))
    assert rdb.pg.val("SELECT count(*) FROM signals") == "1" and rdb.pg.val("SELECT count(*) FROM opportunities") == "1"
    info = rdb.one("opportunity_scope", id=rdb.pg.val("SELECT id FROM opportunities"))["deadline_info"]
    assert info is not None and info["day"] == "2026-11-30"


# ===================================================================== 2 (evening). validation version and re-check

ELIG_SRC = "Applicants based in Kenya must hold a licence if operating in France."
ELIG_WRONG = "Applicants based in France must hold a licence if operating in Kenya."


def _opportunity_with_eligibility(rdb, value: str, quote: str) -> tuple[str, str]:  # noqa: F811
    """A discovered tender whose eligibility claim was read as `value` (one document; simulated transport)."""
    _source(rdb, "Portal", "listing", BASE + "/rfp/", country_coverage=["KE"])
    body = f"{ANNOUNCE} {quote} Tender reference EXA-CGO-2027-077."
    web = Web({BASE + "/rfp/": _listing([BASE + "/rfp/77"]), BASE + "/rfp/77": _page("RFP", body)})

    def reply(doc: str) -> dict:
        return {"language": "en", "claims": [
            {"claim_type": "gssa_tender", "stance": "supports", "quote": ANNOUNCE,
             "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE}, "country": {"value": "Kenya", "quote": ANNOUNCE},
                        "status": {"value": "open", "quote": ANNOUNCE}}},
            {"claim_type": "eligibility", "stance": "supports", "quote": quote,
             "fields": {"airline": {"value": "Example Air", "quote": ANNOUNCE}, "eligibility": {"value": value, "quote": quote}}}]}

    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(reply))
    opp = rdb.pg.val("SELECT id FROM opportunities")
    claim = rdb.pg.val("SELECT id FROM claims WHERE claim_type = 'eligibility'")
    return opp, claim


def test_fields_record_the_validation_version(rdb):  # noqa: F811
    from app.domain import eligibility as el
    _opportunity_with_eligibility(rdb, ELIG_SRC, ELIG_SRC)
    assert rdb.pg.val("SELECT DISTINCT validation_version FROM claim_fields") == str(el.VALIDATION_VERSION)
    assert rdb.pg.val("SELECT count(*) FROM jobs WHERE job_type = 'eligibility_revalidation'") == "0"   # nothing older to re-check


def test_records_validated_under_the_defective_rules_are_rechecked_and_flagged(rdb):  # noqa: F811
    from app.domain import eligibility as el
    from app.services import eligibility_revalidation as er
    opp, claim = _opportunity_with_eligibility(rdb, ELIG_WRONG, ELIG_SRC)
    # Under the current rules the swapped reading is unsupported. Put the record into the shape version 1 left it in:
    # a 'supported' verdict, confirmed by a reviewer, with version 1.
    assert rdb.pg.val(f"SELECT support FROM claim_fields WHERE claim_id = '{claim}' AND field = 'eligibility'") == "unsupported"
    rdb.pg.run(f"UPDATE claim_fields SET support = 'supported', reason = 'requirement stated in the quote', validation_version = 1 "
               f"WHERE claim_id = '{claim}' AND field = 'eligibility'")
    rdb.pg.run(f"UPDATE claims SET review_status = 'confirmed', review_note = 'looks right' WHERE id = '{claim}'")
    original = rdb.pg.val(f"SELECT id FROM claim_fields WHERE claim_id = '{claim}' AND field = 'eligibility'")
    # The migration step queues the job only when something is below the current version.
    rdb.pg.run((SQL / "wfc_0005_validation_version.sql").read_text())
    assert rdb.pg.val("SELECT count(*) FROM jobs WHERE job_type = 'eligibility_revalidation'") == "1"
    report = er.revalidate(rdb, now=datetime(2026, 10, 26, tzinfo=UTC))
    assert report["checked"] == 1 and report["changed"] == 1 and report["withdrawn"] == 1 and report["opportunities_flagged"] == 1
    # The original row is kept, superseded with the reason; the re-check row points back to it.
    rows = rdb.pg.rows(f"SELECT support, validation_version, superseded_at IS NOT NULL, superseded_reason, recheck_of::text "
                       f"FROM claim_fields WHERE claim_id = '{claim}' AND field = 'eligibility' ORDER BY created_at")
    assert rows[0][:3] == ["supported", "1", "t"] and f"v{el.VALIDATION_VERSION}" in rows[0][3] and rows[0][4] == ""
    assert rows[1][0] == "unsupported" and rows[1][1] == str(el.VALIDATION_VERSION) and rows[1][2] == "f" and rows[1][4] == original
    # The previous decision is in the audit history and the claim's note; the claim is back in review.
    audit = rdb.pg.rows("SELECT detail->>'from_support', detail->>'to_support', detail->>'previous_review_status' FROM audit_events "
                        "WHERE event_type = 'eligibility_revalidated'")
    assert audit == [["supported", "unsupported", "confirmed"]]
    c = rdb.one("claim_get", id=claim)
    assert c["review_status"] == "proposed" and "Previous decision: confirmed" in c["review_note"]
    # The opportunity is flagged, its history says why, its gap and qualification check say so.
    o = rdb.one("opportunity_get", id=opp)
    assert o["review_flags"][0]["flag"] == "eligibility_revalidated" and o["review_flags"][0]["from"] == "supported"
    hist = rdb.pg.rows(f"SELECT field, from_value, to_value FROM opportunity_status_history WHERE opportunity_id = '{opp}' "
                       "AND field = 'eligibility_evidence'")
    assert hist == [["eligibility_evidence", "supported", "unsupported"]]
    assert any("withdrawn" in g for g in o["gaps"])
    checks = {r["check_code"]: (r["result"], r["rationale"]) for r in rdb.all("opportunity_checks", id=opp)}
    assert checks["evidence_reviewed"][0] == "unknown" and "withdrawn" in checks["evidence_reviewed"][1]
    # Idempotent; and a reviewer's correction clears the flag's effect on qualification.
    assert er.revalidate(rdb)["checked"] == 0
    doc = rdb.pg.val("SELECT id FROM source_documents WHERE original_url LIKE '%/rfp/77'")
    rev.correct_claim(rdb, claim, document_id=doc, claim_type=None, quote=None,
                      fields={"eligibility": {"value": ELIG_SRC, "quote": ELIG_SRC}}, note="read correctly from the notice", meta=META)
    o2 = rdb.one("opportunity_get", id=opp)
    assert not any("withdrawn" in g for g in o2["gaps"])
    assert o2["review_flags"][0]["flag"] == "eligibility_revalidated"       # the flag's history stays


def test_unchanged_verdicts_only_get_the_new_version(rdb):  # noqa: F811
    from app.services import eligibility_revalidation as er
    _opp, claim = _opportunity_with_eligibility(rdb, ELIG_SRC, ELIG_SRC)
    rdb.pg.run(f"UPDATE claim_fields SET validation_version = 1 WHERE claim_id = '{claim}' AND field = 'eligibility'")
    report = er.revalidate(rdb)
    assert (report["checked"], report["unchanged"], report["changed"], report["withdrawn"], report["claims_reopened"],
            report["opportunities_flagged"]) == (1, 1, 0, 0, 0, 0)
    # Unchanged verdicts re-evaluate no signal on their own; from v4 every live tender signal is re-evaluated once anyway
    # (effective status with the age rule, geography from live verdicts, freight relevance), which changes nothing here.
    assert report["signals"] == 1 and report["freight_scope_added"] == 0
    assert rdb.pg.val(f"SELECT count(*) FROM claim_fields WHERE claim_id = '{claim}' AND field = 'eligibility'") == "1"
    assert rdb.pg.val(f"SELECT validation_version FROM claim_fields WHERE claim_id = '{claim}' AND field = 'eligibility'") == str(report["version"])

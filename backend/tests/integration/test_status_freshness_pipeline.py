"""27 Oct 2026, fourth instruction, items 1-4 through the real pipeline on PostgreSQL: discovery, ingestion, the database,
briefing, live counts, country (run) results, the opportunities export, and the v6 re-check of records made under earlier
rules (publication dates, status freshness, route-launch area), including idempotence."""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

from app.services import discovery as dsc
from app.services import eligibility_revalidation as er
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_meaning_relevance_pipeline import _client
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401

UTC = timezone.utc
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)

OLD = "Example Air invites proposals from cargo general sales and service agents for Kenya. Reference EXA-CGO-2025-31."
CONTACT = ("Example Air request for proposals EXA-CGO-2025-31, cargo general sales and service agent for Kenya. "
           "Contact for enquiries: commercial office, Nairobi.")
OLD2 = "Example Air invites proposals from cargo general sales and service agents for Kenya. Reference EXA-CGO-2025-33."
RECONF = "Tender EXA-CGO-2025-33 remains open: proposals from cargo GSSA providers are still being accepted."
OLD3 = "Example Air invites proposals from cargo general sales and service agents for Kenya. Reference EXA-CGO-2025-34."
AWARD = "Tender EXA-CGO-2025-34 has been awarded to Kivu Cargo Services."
PDF_OLD = "Request for proposal for the appointment of a cargo general sales and service agent in Kenya. Sample Airways. Reference SAW-CGO-2022-4."
PDF_NODATE = "Request for proposal: cargo general sales and service agent for Kenya. Sample Airways. Reference SAW-CGO-2026-52."
FUTURE = "Example Air invites proposals from cargo general sales and service agents for Kenya. Reference EXA-CGO-2026-53."
NODATE = "Sample Airways invites proposals from cargo general sales and service agents for Kenya. Reference SAW-CGO-2026-54."
LOTS0 = "Sample Airways invites proposals for two separate lots."
LOT_A = "Lot A: passenger sales and ticketing agent in Kenya. Reference SAW-PAX-2027-8. Proposals are due on 15 April 2027."
LOT_B = "Lot B: cargo general sales and service agent in Kenya. Reference SAW-CGO-2027-9. Proposals are due on 15 April 2027."
ROUTE = "Example Cargo will start a twice-weekly Boeing 777 freighter service between Dubai and Nairobi from 4 January 2027."
MIXED = "Example Air invites tenders for passenger and cargo ground handling at Mombasa, Kenya. Reference EXA-HDL-2027-22. Bids are due on 30 January 2027."


def _tender(quote: str, ref: str, *, status_quote: str | None = None, airline: str = "Example Air", deadline: str | None = None,
            ctype: str = "gssa_tender", service: str = "GSSA") -> dict:
    fields = {"airline": {"value": airline, "quote": quote}, "country": {"value": "Kenya", "quote": quote},
              "service": {"value": service, "quote": quote}, "tender_ref": {"value": ref, "quote": quote}}
    if status_quote:
        fields["status"] = {"value": "open", "quote": status_quote}
    if deadline:
        fields["deadline"] = {"value": deadline, "quote": quote}
    return {"claim_type": ctype, "stance": "supports", "quote": quote, "fields": fields}


def _claims(doc: str) -> dict:
    out: list[dict] = []
    for quote, item in (
        (OLD, _tender(OLD, "EXA-CGO-2025-31", status_quote=OLD)),
        (CONTACT, _tender(CONTACT, "EXA-CGO-2025-31")),
        (OLD2, _tender(OLD2, "EXA-CGO-2025-33", status_quote=OLD2)),
        (RECONF, {"claim_type": "tender_status", "stance": "supports", "quote": RECONF, "fields": {
            "airline": {"value": "Example Air", "quote": OLD2}, "tender_ref": {"value": "EXA-CGO-2025-33", "quote": RECONF},
            "status": {"value": "open", "quote": RECONF}}}),
        (OLD3, _tender(OLD3, "EXA-CGO-2025-34", status_quote=OLD3)),
        (AWARD, {"claim_type": "tender_status", "stance": "supports", "quote": AWARD, "fields": {
            "airline": {"value": "Example Air", "quote": OLD3}, "tender_ref": {"value": "EXA-CGO-2025-34", "quote": AWARD},
            "status": {"value": "awarded", "quote": AWARD}}}),
        (PDF_OLD, _tender(PDF_OLD, "SAW-CGO-2022-4", airline="Sample Airways")),
        (PDF_NODATE, _tender(PDF_NODATE, "SAW-CGO-2026-52", airline="Sample Airways")),
        (FUTURE, _tender(FUTURE, "EXA-CGO-2026-53", status_quote=FUTURE)),
        (NODATE, _tender(NODATE, "SAW-CGO-2026-54", status_quote=NODATE, airline="Sample Airways")),
        (LOT_A, _tender(LOT_A, "SAW-PAX-2027-8", status_quote=LOT_A, airline="Sample Airways", deadline="2027-04-15")),
        (LOT_B, _tender(LOT_B, "SAW-CGO-2027-9", status_quote=LOT_B, airline="Sample Airways", deadline="2027-04-15")),
        (MIXED, _tender(MIXED, "EXA-HDL-2027-22", status_quote=MIXED, deadline="2027-01-30", ctype="service_tender", service="HANDLING")),
    ):
        if " ".join(quote.split()) in " ".join(doc.split()):
            out.append(item)
    if ROUTE in doc:
        out.append({"claim_type": "route_launch", "stance": "supports", "quote": ROUTE, "fields": {
            "airline": {"value": "Example Cargo", "quote": ROUTE}, "origin": {"value": "United Arab Emirates", "quote": ROUTE},
            "destination": {"value": "Kenya", "quote": ROUTE}}})
    return {"language": "en", "claims": out}


def _pdf(text: str, created: str | None) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    buf = io.BytesIO()
    SimpleDocTemplate(buf).build([Paragraph(text, getSampleStyleSheet()["Normal"])])
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(buf.getvalue())))
    w.add_metadata({"/Title": "RFP"} | ({"/CreationDate": created} if created else {}))
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def _run(rdb, pages: dict) -> str:  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/f/", country_coverage=["KE", "AE"])
    web = Web({BASE + "/f/": _listing([BASE + f"/f/{k}" for k in pages])} | {BASE + f"/f/{k}": v for k, v in pages.items()})
    sid = dsc.create_search(rdb, dsc.SearchSpec("countries", ["KE", "AE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_claims), now=NOW)
    return started["run_id"]


PAGES = {
    "a-old": _page("RFP EXA-CGO-2025-31", OLD, published="2025-10-26T08:00:00Z"),
    "b-contact": _page("Contact update", CONTACT, published="2026-10-26T07:00:00Z"),
    "c-old2": _page("RFP EXA-CGO-2025-33", OLD2, published="2025-10-20T08:00:00Z"),
    "d-reconf": _page("Status EXA-CGO-2025-33", RECONF, published="2026-10-22T07:00:00Z"),
    "e-old3": _page("RFP EXA-CGO-2025-34", OLD3, published="2025-11-03T08:00:00Z"),
    "f-award": _page("Award EXA-CGO-2025-34", AWARD, published="2026-10-21T07:00:00Z"),
    "g-pdf-old": (_pdf(PDF_OLD, "D:20220314090000Z"), "application/pdf"),
    "h-pdf-nodate": (_pdf(PDF_NODATE, None), "application/pdf"),
    "i-future": _page("RFP EXA-CGO-2026-53", FUTURE, published="2027-03-01T08:00:00Z"),
    "j-nodate": _page("RFP SAW-CGO-2026-54", NODATE),
    "k-lots": _page("Request for proposals: sales agents, Kenya (two lots)", f"{LOTS0} {LOT_A} {LOT_B}", published="2026-10-20T08:00:00Z"),
    "l-route": _page("Example Cargo adds Dubai-Nairobi freighter", ROUTE, published="2026-10-20T08:00:00Z"),
    "m-mixed": _page("Tender EXA-HDL-2027-22", MIXED, published="2026-10-20T08:00:00Z"),
}


def _sig(rdb, ref):  # noqa: F811
    return rdb.pg.rows(f"SELECT classification, freight_scope, tender_state->>'status', id, tender_state::text, module FROM signals WHERE tender_ref = '{ref}'")[0]


def _opp(rdb, ref):  # noqa: F811
    rows = rdb.pg.rows(f"SELECT o.id, o.tender_status, o.tender_status_basis, o.review_flags::text FROM opportunities o JOIN signals s ON s.id = o.signal_id "
                       f"WHERE s.tender_ref = '{ref}'")
    return rows[0] if rows else None


def _doc(rdb, frag):  # noqa: F811
    return rdb.pg.rows(f"SELECT coalesce(published_at::text, ''), coalesce(published_at_source, ''), coalesce(publication_flag, ''), "
                       f"coalesce(publication_note, ''), publication_version FROM source_documents WHERE canonical_url LIKE '%/f/{frag}'")[0]


def test_status_freshness_through_ingestion_database_briefing_counts_country_results_and_export(rdb):  # noqa: F811
    run_id = _run(rdb, PAGES)
    # the reported defect: a year-old open assertion plus a contact update published today stays unverified
    cls, sc, st, sid, state, _m = _sig(rdb, "EXA-CGO-2025-31")
    s = json.loads(state)
    assert st == "unverified" and s["status_verified_at"].startswith("2025-10-26") and s["actionable"] is False
    # the newer contact update is attached as supporting information (fifth instruction, item 5), not as a tender observation
    assert rdb.pg.val(f"SELECT count(*) FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id WHERE sc.signal_id = '{sid}' "
                      "AND c.claim_type = 'tender_context'") == "1"
    o = _opp(rdb, "EXA-CGO-2025-31")
    assert o[1] == "unverified"
    # an explicit reconfirmation renews it; a terminal status is kept
    assert _sig(rdb, "EXA-CGO-2025-33")[2] == "open" and _opp(rdb, "EXA-CGO-2025-33")[1] == "open"
    assert _sig(rdb, "EXA-CGO-2025-34")[2] == "awarded"
    # live counts, country (run) results and export agree
    c = _client(rdb)
    try:
        b = c.get("/briefing").json()
        live = {p["tender_status"]: int(p["n"]) for p in b["pipeline"] if p["freight_scope"] == "cargo"}
        assert live.get("open", 0) == 2                     # EXA-CGO-2025-33 (reconfirmed) and lot B (closing date); not the defect case
        assert live.get("unverified", 0) >= 2               # the defect case and the undated notice
        results = {r["title"]: r for r in rdb.all("run_results", run=run_id)}
        row = next(r for t, r in results.items() if "EXA-CGO-2025-31" in t)
        assert row["tender_status"] == "unverified"
        csv = c.get("/reports/opportunities.csv").text.splitlines()
        header = next(r for r in csv if r.startswith("id,"))
        assert "status_stated_at,status_first_stated_at,last_retrieved_at" in header
        cols = header.split(",")
        line = next(r for r in csv if "EXA-CGO-2025-31" in r)
        assert "unverified" in line and "2025-10-26" in line
        undated = next(r for r in csv if "SAW-CGO-2026-54" in r)
        assert undated.split(",")[cols.index("status_stated_at")] == "unknown" or ",unknown," in undated
    finally:
        c.__exit__(None, None, None)


def test_publication_dates_pdf_missing_future_and_old_documents(rdb):  # noqa: F811
    _run(rdb, PAGES)
    pub, src, flag, _note, ver = _doc(rdb, "g-pdf-old")
    assert pub.startswith("2022-03-14") and src == "pdf_metadata" and flag == "" and ver == "6"
    st = json.loads(_sig(rdb, "SAW-CGO-2022-4")[4])
    assert st["status"] == "historical" and "-1 days" not in st["basis"] and "days ago" in st["basis"]
    pub, src, flag, note, _v = _doc(rdb, "h-pdf-nodate")
    assert pub == "" and src == "" and flag == "" and "no publication date" in note
    st = json.loads(_sig(rdb, "SAW-CGO-2026-52")[4])
    assert st["status"] == "announced" and "publication date unknown" in st["basis"]
    pub, src, flag, note, _v = _doc(rdb, "i-future")
    assert pub == "" and flag == "future" and "2027-03-01" in note
    assert _sig(rdb, "EXA-CGO-2026-53")[2] == "unverified"
    pub, _s, flag, _n, _v = _doc(rdb, "j-nodate")
    assert pub == "" and flag == ""
    st = json.loads(_sig(rdb, "SAW-CGO-2026-54")[4])
    assert st["status"] == "unverified" and st["status_date_known"] is False and "does not verify" in st["basis"]


def test_classification_fixes_through_the_pipeline(rdb):  # noqa: F811
    _run(rdb, PAGES)
    # a route launch without trucking scope enters capacity and trade lanes
    assert rdb.pg.val("SELECT module FROM signals WHERE title LIKE 'Example Cargo%'") == "capacity_lanes"
    # the passenger lot stays inspectable as excluded evidence, with its reason; the cargo lot is the opportunity
    cls, sc, _st, sid, _s, _m = _sig(rdb, "SAW-PAX-2027-8")
    assert (cls, sc) == ("excluded", "passenger") and _opp(rdb, "SAW-PAX-2027-8") is None
    gaps = rdb.pg.val(f"SELECT gaps::text FROM signals WHERE id = '{sid}'")
    assert "Excluded from the freight pipeline" in gaps
    assert rdb.pg.val("SELECT count(*) FROM extraction_rejections WHERE raw::text LIKE '%SAW-PAX-2027-8%'") == "0"
    assert _sig(rdb, "SAW-CGO-2027-9")[:2] == ["qualified_opportunity", "cargo"]
    # mixed passenger and cargo handling is held for review, not forced
    assert _sig(rdb, "EXA-HDL-2027-22")[:2] == ["freight_candidate", "mixed"]


def test_v6_recheck_withdraws_stale_open_status_fixes_dates_and_areas_and_is_idempotent(rdb):  # noqa: F811
    _run(rdb, PAGES)
    # Put records into the shape earlier rules left them: the defect case 'open' (renewed by the contact update), the future
    # date stored as a publication date, the route launch filed under airline representation, everything below v6.
    sid = _sig(rdb, "EXA-CGO-2025-31")[3]
    rdb.pg.run(f"UPDATE signals SET tender_state = jsonb_set(tender_state, '{{status}}', '\"open\"') WHERE id = '{sid}'")
    rdb.pg.run(f"UPDATE opportunities SET tender_status = 'open', tender_status_basis = 'stated open 0 days ago; no closing date stated' "
               f"WHERE signal_id = '{sid}'")
    rdb.pg.run("UPDATE source_documents SET published_at = '2027-03-01T08:00:00Z', published_at_source = 'page', publication_flag = NULL, "
               "publication_note = NULL WHERE canonical_url LIKE '%/f/i-future'")
    rdb.pg.run("UPDATE signals SET module = 'airline_representation' WHERE title LIKE 'Example Cargo%'")
    rdb.pg.run("UPDATE source_documents SET publication_version = 5")
    rdb.pg.run("UPDATE claim_fields SET validation_version = 5")
    from pathlib import Path
    rdb.pg.run((Path(__file__).resolve().parents[2] / "migrations" / "sql" / "wfc_0009_status_freshness_v6.sql").read_text())
    assert rdb.pg.val("SELECT payload->>'to_version' FROM jobs WHERE execution_key = 'field-revalidation:wfc_0009'") == "6"
    report = er.revalidate(rdb, now=NOW, to_version=6)
    assert report["status_withdrawn"] >= 1 and report["publication_dates_changed"] >= 1 and report["areas_changed"] == 1
    o = _opp(rdb, "EXA-CGO-2025-31")
    assert o[1] == "unverified" and "status_revalidated" in o[3]
    pub, src, flag, note, ver = _doc(rdb, "i-future")
    assert pub == "" and flag == "future" and ver == "6"
    ev_ = json.loads(rdb.pg.val("SELECT detail::text FROM audit_events WHERE event_type = 'publication_date_revalidated' LIMIT 1"))
    assert ev_["from"].startswith("2027-03-01") and ev_["to"] is None and ev_["flag"] == "future"
    assert rdb.pg.val("SELECT module FROM signals WHERE title LIKE 'Example Cargo%'") == "capacity_lanes"
    assert rdb.pg.val("SELECT count(*) FROM audit_events WHERE event_type = 'capability_area_revalidated'") == "1"
    # history and evidence are kept: the original claims and documents are still there
    assert rdb.pg.val("SELECT count(*) FROM source_documents WHERE canonical_url LIKE '%/f/b-contact'") == "1"
    again = er.revalidate(rdb, now=NOW, to_version=6)
    assert again["checked"] == 0 and again["publication_dates_changed"] == 0 and again["status_withdrawn"] == 0 and again["areas_changed"] == 0
    assert rdb.pg.val("SELECT count(*) FROM audit_events WHERE event_type IN ('publication_date_revalidated','capability_area_revalidated')") == "2"


AWARD_ONLY = "Tender 58/DCO/SGSIA/2023 for cargo handling in Kenya has been awarded to Rift Handling Services."
OPEN_THEN_CANCELLED = "Example Air invites proposals for cargo handling in Kenya under reference EXA-HDL-2026-77."
CANCELLED = "Tender EXA-HDL-2026-77 has been cancelled."


def _terminal_claims(doc: str) -> dict:
    out: list[dict] = []
    if "58/DCO/SGSIA/2023" in doc:
        out.append({"claim_type": "service_tender", "stance": "supports", "quote": AWARD_ONLY, "fields": {
            "organisation": {"value": "SGSIA", "quote": AWARD_ONLY}, "country": {"value": "Kenya", "quote": AWARD_ONLY},
            "service": {"value": "HANDLING", "quote": AWARD_ONLY}, "status": {"value": "awarded", "quote": AWARD_ONLY},
            "tender_ref": {"value": "58/DCO/SGSIA/2023", "quote": AWARD_ONLY}}})
    if "EXA-HDL-2026-77" in doc:
        out.append(_tender(OPEN_THEN_CANCELLED, "EXA-HDL-2026-77", status_quote=OPEN_THEN_CANCELLED, ctype="service_tender", service="HANDLING"))
        out.append({"claim_type": "tender_status", "stance": "supports", "quote": CANCELLED, "fields": {
            "airline": {"value": "Example Air", "quote": OPEN_THEN_CANCELLED}, "tender_ref": {"value": "EXA-HDL-2026-77", "quote": CANCELLED},
            "status": {"value": "cancelled", "quote": CANCELLED}}})
    return {"language": "en", "claims": out}


def test_terminal_only_notices_are_historical_records_and_reference_years_are_not_dates(rdb):  # noqa: F811
    _source(rdb, "Portal", "listing", BASE + "/t/", country_coverage=["KE"])
    pages = {BASE + "/t/award": _page("Award 58/DCO/SGSIA/2023", AWARD_ONLY, published="2026-10-20T08:00:00Z"),
             BASE + "/t/cancel": _page("Tender EXA-HDL-2026-77", f"{OPEN_THEN_CANCELLED} {CANCELLED}", published="2026-10-20T08:00:00Z")}
    web = Web({BASE + "/t/": _listing(list(pages))} | pages)
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_terminal_claims), now=NOW)
    # a year inside the reference code is not a past date: the award notice is read as an award. Not tracked before, so it is
    # historical intelligence (fifth instruction, item 4): no opportunity, never live.
    assert rdb.pg.rows("SELECT tender_state->>'status', classification FROM signals WHERE tender_ref = '58/DCO/SGSIA/2023'")[0] == \
        ["awarded", "historical_record"]
    assert _opp(rdb, "58/DCO/SGSIA/2023") is None
    # a notice that announced the tender and its cancellation together: also a historical record, not an opportunity
    assert rdb.pg.val("SELECT classification FROM signals WHERE tender_ref = 'EXA-HDL-2026-77'") == "historical_record"
    assert _opp(rdb, "EXA-HDL-2026-77") is None

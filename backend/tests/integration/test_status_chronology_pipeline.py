"""27 Oct 2026, fifth instruction, items 1-5 through the real pipeline on PostgreSQL: discovery, ingestion, the database,
qualification, briefing (live counts), country (run) results and the opportunities export, for cancelled, awarded and
closed tenders; the v7 re-check of records made under earlier rules (idempotent); supporting tender context and lot issuers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services import discovery as dsc
from app.services import eligibility_revalidation as er
from tests.integration.sa import sadb  # noqa: F401
from tests.integration.test_meaning_relevance_pipeline import _client
from tests.integration.test_review3_regressions import BASE, SETTINGS, Web, _listing, _page, _source, model, rdb  # noqa: F401

NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
TERMINAL_TEXT = {"cancelled": "has been cancelled", "awarded": "has been awarded to Kivu Cargo Agents", "closed": "is closed"}
CODE = {"cancelled": "CAN", "awarded": "AWD", "closed": "CLS"}


def ref(t: str, k: str) -> str:
    return f"CHR-{CODE[t]}-{k}"


def open_text(r: str, *, deadline: str = "20 January 2027", again: bool = False) -> str:
    lead = f"Tender {r} has been reopened: Example Air invites proposals again" if again else "Example Air invites proposals"
    return f"{lead} from cargo general sales and service agents for Kenya. Reference {r}. Proposals must be submitted by {deadline}."


def end_text(t: str, r: str) -> str:
    return f"Tender {r} (cargo GSSA, Kenya, Example Air) {TERMINAL_TEXT[t]}."


DEADLINE_ISO = {"20 January 2027": "2027-01-20", "15 December 2026": "2026-12-15"}


def _claims(doc: str) -> dict:
    import re
    d = " ".join(doc.split())
    out: list[dict] = []
    for m in re.finditer(r"(?:Tender \S+ has been reopened: )?Example Air invites proposals(?: again)? from cargo general sales and service agents "
                         r"for Kenya\. Reference (\S+?)\.(?: Proposals must be submitted by ([^.]+)\.)?", d):
        quote, r, dl = m.group(0), m.group(1), m.group(2)
        fields = {"airline": {"value": "Example Air", "quote": quote}, "country": {"value": "Kenya", "quote": quote},
                  "service": {"value": "GSSA", "quote": quote}, "tender_ref": {"value": r, "quote": quote},
                  "status": {"value": "open", "quote": quote}}
        if dl:
            fields["deadline"] = {"value": DEADLINE_ISO[dl], "quote": quote}
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": quote, "fields": fields})
    for m in re.finditer(r"Tender (\S+) \(cargo GSSA, Kenya, Example Air\) (has been cancelled|has been awarded to Kivu Cargo Agents|is closed)\.", d):
        t = next(k for k, v in TERMINAL_TEXT.items() if v == m.group(2))
        out.append({"claim_type": "tender_status", "stance": "supports", "quote": m.group(0), "fields": {
            "airline": {"value": "Example Air", "quote": m.group(0)}, "tender_ref": {"value": m.group(1), "quote": m.group(0)},
            "status": {"value": t, "quote": m.group(0)}}})
    for m in re.finditer(r"Contact update for tender (\S+) \([^)]*\): [^.]*\.", d):
        q = m.group(0)
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": q, "fields": {
            "airline": {"value": "Example Air", "quote": q}, "country": {"value": "Kenya", "quote": q},
            "service": {"value": "GSSA", "quote": q}, "tender_ref": {"value": m.group(1), "quote": q}}})
    for m in re.finditer(r"Lot 1: [^.]*\. Reference (\S+?)\.", d):
        q = m.group(0)
        out.append({"claim_type": "gssa_tender", "stance": "supports", "quote": q, "fields": {
            "airline": {"value": "Sample Airways", "quote": q}, "country": {"value": "Kenya", "quote": q},
            "service": {"value": "GSSA", "quote": q}, "tender_ref": {"value": m.group(1), "quote": q},
            "status": {"value": "open", "quote": q}}})
    return {"language": "en", "claims": out}


def _pages() -> dict[str, bytes]:
    p: dict[str, bytes] = {}
    for t in TERMINAL_TEXT:
        # A: the reproduction: dated terminal statement, then an UNDATED open notice with a future deadline
        p[f"{t}-a1"] = _page("End", end_text(t, ref(t, "A")), published="2026-10-24T08:00:00Z")
        p[f"{t}-a2"] = _page("RFP", open_text(ref(t, "A")))
        # B: an older dated notice rediscovered after the terminal statement
        p[f"{t}-b1"] = _page("End", end_text(t, ref(t, "B")), published="2026-10-21T08:00:00Z")
        p[f"{t}-b2"] = _page("RFP", open_text(ref(t, "B")), published="2026-06-08T08:00:00Z")
        # D: open and terminal statements published the same day
        p[f"{t}-d1"] = _page("RFP", open_text(ref(t, "D")), published="2026-10-22T08:00:00Z")
        p[f"{t}-d2"] = _page("End", end_text(t, ref(t, "D")), published="2026-10-22T09:00:00Z")
        # E: a tracked tender, then the terminal statement, then an undated repeated copy of the original announcement
        p[f"{t}-e1"] = _page("RFP", open_text(ref(t, "E"), deadline="15 December 2026"), published="2026-08-27T08:00:00Z")
        p[f"{t}-e2"] = _page("End", end_text(t, ref(t, "E")), published="2026-10-06T08:00:00Z")
        p[f"{t}-e3"] = _page("RFP (copy)", open_text(ref(t, "E"), deadline="15 December 2026"))
        # F: a terminal old round, and a new round with a similar title and its own reference
        p[f"{t}-f1"] = _page("Cargo GSSA, Kenya", end_text(t, ref(t, "F")), published="2026-08-27T08:00:00Z")
        p[f"{t}-f2"] = _page("Cargo GSSA, Kenya", open_text(ref(t, "G")), published="2026-10-23T08:00:00Z")
        # C: an explicit, dated reopening
        p[f"{t}-c1"] = _page("End", end_text(t, ref(t, "C")), published="2026-09-26T08:00:00Z")
        p[f"{t}-c2"] = _page("Reopened", open_text(ref(t, "C"), again=True), published="2026-10-23T08:00:00Z")
    return p


def _run(rdb, pages: dict[str, bytes], path: str = "chr") -> str:  # noqa: F811
    """One search run over one listing (a listing yields at most 25 targets per run, so larger page sets use several paths)."""
    _source(rdb, f"Portal {path}", "listing", BASE + f"/{path}/", country_coverage=["KE"], max_items=100)
    web = Web({BASE + f"/{path}/": _listing([BASE + f"/{path}/{k}" for k in pages])} | {BASE + f"/{path}/{k}": v for k, v in pages.items()})
    sid = dsc.create_search(rdb, dsc.SearchSpec("country", ["KE"], [], []))
    started = dsc.start_run(rdb, SETTINGS, search_id=sid)
    dsc.execute_run(rdb, SETTINGS, started["run_id"], None, fetch=web, transport=model(_claims), now=NOW)
    return started["run_id"]


def _sig(rdb, r):  # noqa: F811
    rows = rdb.pg.rows(f"SELECT tender_state->>'status', classification, (tender_state->>'actionable'), coalesce(tender_state->>'status_conflict', ''), id "
                       f"FROM signals WHERE tender_ref = '{r}'")
    assert rows, r
    return rows[0]


def _opp(rdb, r):  # noqa: F811
    rows = rdb.pg.rows(f"SELECT o.id, o.tender_status, o.review_flags::text FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = '{r}'")
    return rows[0] if rows else None


def test_status_transitions_for_every_terminal_status_through_the_pipeline(rdb):  # noqa: F811
    pages = _pages()
    run_ids = [_run(rdb, {k: v for k, v in pages.items() if k.startswith(t + "-")}, path=f"chr-{t}") for t in TERMINAL_TEXT]
    for t in TERMINAL_TEXT:
        # A (the reproduction): never open, never actionable; a historical record, no opportunity; the conflict kept
        st, cls, act, conflict, _ = _sig(rdb, ref(t, "A"))
        assert (st, cls, act) == (t, "historical_record", "false") and "does not establish" in conflict, (t, st, cls, conflict)
        assert _opp(rdb, ref(t, "A")) is None
        # B: an older notice rediscovered later is placed by its own date
        assert _sig(rdb, ref(t, "B"))[:3] == [t, "historical_record", "false"]
        # D: same-day conflict: a person decides; never actionable
        st, cls, act, conflict, _ = _sig(rdb, ref(t, "D"))
        assert st == "contradictory" and act == "false" and "same day" in conflict
        # E: the tracked tender moves to the terminal status; the undated copy does not reopen it, and the conflict is flagged
        o = _opp(rdb, ref(t, "E"))
        assert o is not None and o[1] == t and "status_conflict" in o[2], (t, o)
        checks = {r[0]: r[1] for r in rdb.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id = '{o[0]}'")}
        assert checks.get("live_status") != "pass"
        # F/G: the old round stays a historical record; the new round is its own open tender
        assert _sig(rdb, ref(t, "F"))[:2] == [t, "historical_record"]
        assert _sig(rdb, ref(t, "G"))[:3] == ["open", "qualified_opportunity", "true"]
        # C: an explicit, dated reopening is supported
        assert _sig(rdb, ref(t, "C"))[:3] == ["open", "qualified_opportunity", "true"]
        assert _opp(rdb, ref(t, "C"))[1] == "open"
    # briefing live counts, country (run) results and export agree
    c = _client(rdb)
    try:
        b = c.get("/briefing").json()
        live = sum(int(p["n"]) for p in b["pipeline"] if p["tender_status"] in ("open", "revised"))
        assert live == 6                                            # C and G for each terminal status, nothing else
        results = [r for rid in run_ids for r in rdb.all("run_results", run=rid)]
        by_title_ref = {r["title"]: r for r in results}
        for t in TERMINAL_TEXT:
            row = next(r for k, r in by_title_ref.items() if ref(t, "A") in k)
            assert row["classification"] == "historical_record" and row["opportunity_id"] is None
        csv = c.get("/reports/opportunities.csv").text
        for t in TERMINAL_TEXT:
            assert ref(t, "A") not in csv and ref(t, "B") not in csv and ref(t, "F") not in csv
            line = next(x for x in csv.splitlines() if ref(t, "E") in x)
            assert f",{t}," in line
        opened = [x for x in csv.splitlines() if ",open," in x]
        assert len(opened) == 6 and all(("-C)" in x or "-G)" in x) for x in opened), opened
    finally:
        c.__exit__(None, None, None)


def test_v7_recheck_withdraws_open_status_decided_by_retrieval_order_and_is_idempotent(rdb):  # noqa: F811
    _run(rdb, {k: v for k, v in _pages().items() if k.startswith("cancelled-a")})
    sid = _sig(rdb, ref("cancelled", "A"))[4]
    # the shape v6 left: the undated open notice retrieved after the cancellation made the tender open and actionable
    rdb.pg.run(f"UPDATE signals SET classification = 'qualified_opportunity', tender_state = jsonb_set(jsonb_set(tender_state, '{{status}}', '\"open\"'), "
               f"'{{actionable}}', 'true') WHERE id = '{sid}'")
    rdb.pg.run(f"INSERT INTO opportunities (module, signal_id, dedup_key, title, freight_scope, tender_status, tender_status_basis) "
               f"SELECT module, id, signal_key, title, 'cargo', 'open', 'stated open; deadline 2027-01-20' FROM signals WHERE id = '{sid}'")
    rdb.pg.run("UPDATE claim_fields SET validation_version = 6")
    rdb.pg.run((Path(__file__).resolve().parents[2] / "migrations" / "sql" / "wfc_0010_status_chronology_v7.sql").read_text())
    assert rdb.pg.val("SELECT payload->>'to_version' FROM jobs WHERE execution_key = 'field-revalidation:wfc_0010'") == "7"
    report = er.revalidate(rdb, now=NOW, to_version=7)
    assert report["chronology_changed"] == 1 and report["status_withdrawn"] >= 1
    o = _opp(rdb, ref("cancelled", "A"))
    assert o[1] == "cancelled" and "status_chronology_revalidated" in o[2]
    hist = rdb.pg.rows(f"SELECT field, from_value, to_value FROM opportunity_status_history WHERE opportunity_id = '{o[0]}' AND field = 'tender_status'")
    assert ["tender_status", "open", "cancelled"] in hist                   # the change is recorded, nothing deleted
    assert rdb.pg.val(f"SELECT count(*) FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id WHERE sc.signal_id = '{sid}'") == "2"
    flags_before = rdb.pg.val(f"SELECT jsonb_array_length(review_flags) FROM opportunities WHERE id = '{o[0]}'")
    again = er.revalidate(rdb, now=NOW, to_version=7)
    assert again["checked"] == 0 and again["chronology_changed"] == 0 and again["status_withdrawn"] == 0
    assert rdb.pg.val(f"SELECT jsonb_array_length(review_flags) FROM opportunities WHERE id = '{o[0]}'") == flags_before


def test_contact_update_attaches_as_context_without_refreshing_status_and_lot_issuer_from_introduction(rdb):  # noqa: F811
    r = "CHR-CTX-1"
    pages = {
        "ctx-1": _page("RFP", f"Example Air invites proposals from cargo general sales and service agents for Kenya. Reference {r}.",
                       published="2026-05-01T08:00:00Z"),
        "ctx-2": _page("Contact update", f"Contact update for tender {r} (cargo GSSA, Kenya, Example Air): enquiries now go to the commercial office in Nairobi.",
                       published="2026-10-25T08:00:00Z"),
        "lot": _page("Request for proposals: cargo sales agent, Kenya",
                     "Sample Airways invites proposals for the following lot. Lot 1: cargo general sales and service agent in Kenya. Reference CHR-LOT-31.",
                     published="2026-10-20T08:00:00Z"),
    }
    _run(rdb, pages)
    st = json.loads(rdb.pg.val(f"SELECT tender_state::text FROM signals WHERE tender_ref = '{r}'"))
    assert st["status"] == "unverified" and st["status_verified_at"].startswith("2026-05-01")    # not refreshed by the contact update
    types = sorted(x[0] for x in rdb.pg.rows(f"SELECT c.claim_type FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id "
                                              f"JOIN signals s ON s.id = sc.signal_id WHERE s.tender_ref = '{r}'"))
    assert types == ["gssa_tender", "tender_context"]
    assert rdb.pg.val("SELECT count(*) FROM extraction_rejections WHERE raw::text LIKE '%Contact update%'") == "0"
    lot = rdb.pg.rows("SELECT cf.support, cf.reason FROM claim_fields cf JOIN claims c ON c.id = cf.claim_id "
                      "WHERE c.tender_ref = 'CHR-LOT-31' AND cf.field = 'airline' AND cf.superseded_at IS NULL")[0]
    assert lot[0] == "supported" and "introduction" in lot[1]
    assert rdb.pg.val("SELECT o.tender_status FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'CHR-LOT-31'") is not None

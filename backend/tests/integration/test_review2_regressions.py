"""Second independent review (26 Oct 2026): the reviewer's demonstrations of
9 defects, kept as regression tests. Each asserts the directive-correct
behaviour; all 9 failed against commit bea5ae6 and pass after the fixes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import evidence as ev
from app.domain import qualification as qual
from app.domain.field_validation import FieldClaim as F, validate_claim
from app.services import discovery as dsc
from app.services import imports_service as imp
from app.services import ingestion as ing
from app.services import review_service as rev
from app.services import sources_service as srcs
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401

UTC = timezone.utc
META = RequestMeta(ip="203.0.113.10", request_id="req-review", session_ref="sessreview001")
NOW = datetime(2026, 10, 26, 8, tzinfo=UTC)


@pytest.fixture()
def db(sadb):  # noqa: F811
    for ds, text in {"operating_companies": "name\nWFC-UAE\n",
                     "airports": "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n",
                     "airlines": "iata_code,name,country\nXA,Example Air,AE\n"}.items():
        imp.import_file(sadb, ds, f"{ds}.csv", text.encode(), None, META)
    sid = srcs.create_source(sadb, srcs.SourceSpec("Portal", "web_page", "https://tenders.example-air.example", "official_portal",
                                                   retention_permitted=True, enabled=True), META)
    tid = srcs.create_source(sadb, srcs.SourceSpec("Wire", "web_page", "https://tradewire.example", "trade_press",
                                                   retention_permitted=True, enabled=True), META)
    sadb.portal = ing.SourceInfo(sid, "portal", "official_portal", "https://tenders.example-air.example", True)
    sadb.wire = ing.SourceInfo(tid, "wire", "trade_press", "https://tradewire.example", True)
    return sadb


def _doc(src, url, text, days=1):
    return ing.IncomingDocument(src, url, url, text, published_at=NOW - timedelta(days=days))


TEMPLATE = ("NOTICE OF INVITATION. Example Air invites proposals from qualified GSSA providers for cargo sales and service "
            "representation in Kenya. This invitation covers the {gw} gateway. Proposals must be submitted by {dl} at 17:00 "
            "East Africa Time. Interested parties should contact the procurement office for the tender documents and the "
            "evaluation criteria applicable to this invitation.")


def _tender(text, dl_value, dl_text, ref=None):
    q = "Example Air invites proposals from qualified GSSA providers for cargo sales and service representation in Kenya."
    fields = {"airline": F("Example Air", q), "country": F("Kenya", q), "service": F("GSSA", q), "status": F("open", q),
              "deadline": F(dl_value, f"Proposals must be submitted by {dl_text} at 17:00 East Africa Time.")}
    if ref:
        fields["tender_ref"] = F(ref, f"Tender reference {ref}.")
    return ing.ClaimProposal("gssa_tender", q, fields, deadline_timezone="Africa/Nairobi")


# D1 (§6): two templated tenders (different gateway, different deadline, no reference) from the same portal.
def test_d1_templated_tenders_without_reference_stay_distinct(db):
    t1 = TEMPLATE.format(gw="Nairobi", dl="30 November 2026")
    t2 = TEMPLATE.format(gw="Mombasa", dl="15 January 2027")
    r1 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/1", t1),
                    [_tender(t1, "2026-11-30T17:00:00", "30 November 2026")], now=NOW)
    r2 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/2", t2),
                    [_tender(t2, "2027-01-15T17:00:00", "15 January 2027")], now=NOW)
    print("families", r1.family_key, r2.family_key, "signals", r1.signal_id, r2.signal_id)
    print("opps", db.pg.val("SELECT count(*) FROM opportunities"),
          db.pg.val("SELECT deadline_utc::text FROM opportunities LIMIT 1"))
    assert r1.signal_id != r2.signal_id, "two distinct tenders auto-merged into one signal/opportunity"


# D2 (§6): an amendment citing the tender reference but not repeating the airline name.
def test_d2_amendment_by_reference_attaches_to_tender(db):
    ref = "EXA-CGO-2027-001"
    base = TEMPLATE.format(gw="Nairobi", dl="30 November 2026") + f" Tender reference {ref}."
    r1 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/1", base, 3),
                    [_tender(base, "2026-11-30T17:00:00", "30 November 2026", ref=ref)], now=NOW)
    amend = f"CORRIGENDUM No. 1 to tender {ref}. The submission deadline is extended to 14 December 2026 at 17:00 East Africa Time."
    q = "The submission deadline is extended to 14 December 2026 at 17:00 East Africa Time."
    r2 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/1/corr-1", amend, 1),
                    [ing.ClaimProposal("tender_deadline", q, {"tender_ref": F(ref, f"CORRIGENDUM No. 1 to tender {ref}."),
                                                              "deadline": F("2026-12-14T17:00:00", q), "status": F("revised", q)},
                                       deadline_timezone="Africa/Nairobi")], now=NOW)
    print("base", r1.signal_id, "amend", r2.signal_id,
          db.pg.val(f"SELECT signal_key FROM signals WHERE id='{r2.signal_id}'"),
          db.pg.val(f"SELECT deadline_utc::text FROM opportunities WHERE id='{r1.opportunity_id}'"))
    assert r2.signal_id == r1.signal_id, "amendment citing the reference did not attach to its tender"


# D2b (§6): amendment to a HANDLING service tender lands in a different module/signal.
def test_d2b_service_tender_amendment_same_module(db):
    ref = "EXA-HDL-2027-005"
    base = (f"Example Air invites tenders for cargo handling services at Nairobi, Kenya. Tender reference {ref}. "
            "Bids are due by 30 November 2026 at 17:00 East Africa Time.")
    q = "Example Air invites tenders for cargo handling services at Nairobi, Kenya."
    r1 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/hdl", base, 3), [ing.ClaimProposal(
        "service_tender", q, {"airline": F("Example Air", q), "country": F("Kenya", q), "service": F("HANDLING", q),
                              "status": F("open", "Bids are due by 30 November 2026"), "tender_ref": F(ref, f"Tender reference {ref}."),
                              "deadline": F("2026-11-30T17:00:00", "Bids are due by 30 November 2026 at 17:00 East Africa Time.")},
        deadline_timezone="Africa/Nairobi")], now=NOW)
    amend = f"Example Air amendment to tender {ref}: the closing date is extended to 14 December 2026 at 17:00 East Africa Time."
    r2 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/hdl/a1", amend, 1), [ing.ClaimProposal(
        "tender_deadline", amend, {"airline": F("Example Air", amend), "tender_ref": F(ref, amend),
                                   "deadline": F("2026-12-14T17:00:00", amend), "status": F("revised", amend)},
        deadline_timezone="Africa/Nairobi")], now=NOW)
    print(db.pg.rows("SELECT module, signal_key FROM signals"))
    assert r2.signal_id == r1.signal_id, "amendment for a service tender created a separate airline_representation signal"


# D3 (§6): after a reviewed merge, later evidence keyed to the merged signal must reach the survivor.
def test_d3_post_merge_amendment_reaches_survivor(db):
    ref = "EXA-CGO-2027-009"
    wire_txt = TEMPLATE.format(gw="Nairobi", dl="30 November 2026") + f" Tender reference {ref}. Reported by the trade wire."
    b = ing.ingest(db, _doc(db.wire, "https://tradewire.example/x", wire_txt, 5),
                   [_tender(wire_txt, "2026-11-30T17:00:00", "30 November 2026", ref=ref)], now=NOW)
    portal_txt = ("Example Air invites proposals from qualified GSSA providers for cargo sales and service representation in Kenya. "
                  "Proposals must be submitted by 30 November 2026 at 17:00 East Africa Time. Contact procurement.")
    a = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/a", portal_txt, 4),
                   [_tender(portal_txt, "2026-11-30T17:00:00", "30 November 2026")], now=NOW)
    assert a.opportunity_id and a.signal_id != b.signal_id
    cand = db.pg.val("SELECT id FROM merge_candidates WHERE status='open' LIMIT 1")
    assert cand, "no merge candidate"
    rev.decide_merge(db, cand, "merged", "same Kenya GSSA RFP", META)
    amend = (f"Example Air corrigendum to tender {ref}: the submission deadline is extended to 14 December 2026 at 17:00 "
             "East Africa Time.")
    ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/a/c1", amend, 1), [ing.ClaimProposal(
        "tender_deadline", amend, {"airline": F("Example Air", amend), "tender_ref": F(ref, amend),
                                   "deadline": F("2026-12-14T17:00:00", amend), "status": F("revised", amend)},
        deadline_timezone="Africa/Nairobi")], now=NOW)
    dl = db.pg.val(f"SELECT deadline_utc AT TIME ZONE 'UTC' FROM opportunities WHERE id='{a.opportunity_id}'")
    print("survivor opp deadline", dl, db.pg.rows("SELECT id, merged_into_id, signal_key FROM signals"))
    assert dl == "2026-12-14 14:00:00", "amendment went to the merged (dead) signal; surviving opportunity kept stale deadline"


# D4 (§7/§8): a 'closed' tender with a future deadline passes not_expired and can reach ready_for_review.
def test_d4_closed_tender_is_not_live():
    obs = [ev.TenderObservation("d1", "f1", "portal", "official_portal", NOW, "closed", NOW + timedelta(days=20), "UTC")]  # type: ignore[arg-type]
    t = ev.resolve_tender(obs, NOW)
    exist = ev.assess_claim([ev.EvidenceLink("d1", "f1", "official_portal", "supports", NOW, "pass")])
    checks = qual.airline_representation_checks(existence=exist, tender=t, territory_cell_state="gap", capability_readiness="ready",
                                                eligibility_known=None, eligibility_met=None, scope_known=True)
    print(t.status, t.actionable, [(c.code, c.result) for c in checks])
    assert not any(c.code == "not_expired" and c.result == "pass" for c in checks), "closed tender passes the live/not_expired check"


# D5 (§7): tender reference validated by substring.
def test_d5_tender_ref_substring():
    text = "Tender reference EXA-CGO-2026-014 for cargo GSSA services in Kenya."
    v = validate_claim("gssa_tender", {"tender_ref": F("EXA-CGO-2026-01", text)}, text, claim_quote=text)
    print([(f.field, f.support, f.reason) for f in v.fields])
    assert v.first("tender_ref") is None, "a truncated reference is 'supported' by substring match"


# D6 (§4): template sources silently truncate countries/documents at 25 while coverage claims all countries.
def test_d6_country_truncation_disclosed():
    src = {"source_type": "search_template", "query_template": "https://p.example/s?c={country}", "base_url": "https://p.example",
           "country_coverage": [], "global_coverage": True}
    from app.reference.geography import COUNTRIES
    wanted = set(list(sorted(COUNTRIES))[:40])
    urls = dsc._urls_for(src, None, wanted)
    note = dsc._coverage_note(1, wanted, set(), True)
    print(len(wanted), len(urls), note)
    assert len(urls) == len(wanted) or "not" in note.lower(), "15 of 40 countries never searched; note says covering 40 of 40"


# D7 (§4): worldwide search with no enabled source reports 'no_relevant_results'.
def test_d7_worldwide_no_sources_outcome(db):
    from app import config
    settings = config.load({"ENVIRONMENT": "test", "DATABASE_URL": "postgresql://x@y/z"})
    db.run("source_set_enabled", id=db.portal.id, enabled=False) if False else None
    db.pg.run("UPDATE sources SET enabled = false")
    sid = dsc.create_search(db, dsc.SearchSpec("worldwide", [], [], []))
    started = dsc.start_run(db, settings, search_id=sid)
    out = dsc.execute_run(db, settings, started["run_id"], fetch=lambda u: (_ for _ in ()).throw(AssertionError("no fetch")))
    print(out, started["plan"]["coverage_note"])
    assert out["outcome"] != "no_relevant_results", "nothing was searched but outcome says no relevant results"


# D8 (§11): pipeline report counts lost opportunities as potential pipeline.
def test_d8_pipeline_excludes_lost(db):
    t1 = TEMPLATE.format(gw="Nairobi", dl="30 November 2026")
    r = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/1", t1),
                   [_tender(t1, "2026-11-30T17:00:00", "30 November 2026")], now=NOW)
    from app.services import economics_service as eco
    eco.set_value(db, r.opportunity_id, {"currency": "USD", "wfc_remuneration": __import__("decimal").Decimal("100000"), "incremental_costs": __import__("decimal").Decimal("20000"),
                                         "basis": "contract", "value_kind": "potential"}, META)
    db.pg.run(f"UPDATE opportunities SET commercial_stage='lost' WHERE id='{r.opportunity_id}'")
    rows = db.all("values_for_pipeline2", company=None, module=None, geo=None, kind="potential")
    print(rows)
    assert not rows, "a LOST opportunity is still counted in the potential pipeline"


# Recovery path for D2: a reviewer can propose two opportunities as one tender; nothing merges until decided.
def test_reviewer_proposes_duplicate_then_merges(db):
    t1 = TEMPLATE.format(gw="Nairobi", dl="30 November 2026")
    t2 = TEMPLATE.format(gw="Mombasa", dl="15 January 2027")
    r1 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/1", t1),
                    [_tender(t1, "2026-11-30T17:00:00", "30 November 2026")], now=NOW)
    r2 = ing.ingest(db, _doc(db.portal, "https://tenders.example-air.example/rfp/2", t2),
                    [_tender(t2, "2027-01-15T17:00:00", "15 January 2027")], now=NOW)
    assert r1.opportunity_id and r2.opportunity_id and r1.opportunity_id != r2.opportunity_id
    with pytest.raises(rev.ReviewRejected):
        rev.propose_merge(db, r1.opportunity_id, r1.opportunity_id, "same", META)
    out = rev.propose_merge(db, r1.opportunity_id, r2.opportunity_id, "the Mombasa notice re-issues the Nairobi RFP", META)
    assert db.pg.val("SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL") == "2"   # nothing merged yet
    rev.decide_merge(db, out["candidate_id"], "merged", "confirmed with the procurement office", META)
    assert db.pg.val("SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL") == "1"

"""Evidence, qualification and import regressions carried forward from the
earlier review (route/tender separation, syndication, revision and
cancellation history, contradictions, inauthentic pages, capability from the
register, contradiction after approval, passed deadlines, exception and
booking import idempotency, reversal conflicts, unresolved references,
register writers). Production adapter on real PostgreSQL; claims enter
through the same validated pipeline the extractor and reviewers use."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.field_validation import FieldClaim as F
from app.services import imports_service as imp
from app.services import ingestion as ing
from app.services import opportunity_service as opps
from app.services import ops_service as ops
from app.services import review_service as rev
from app.services import sources_service as srcs
from app.services.audit import RequestMeta
from tests.fixtures import documents as D

UTC = timezone.utc
META = RequestMeta(ip="203.0.113.10", request_id="req-r", session_ref="sess123456ab")
NOW = datetime(2026, 10, 26, 8, tzinfo=UTC)


def load(db, ds, text):
    return imp.import_file(db, ds, f"{ds}.csv", text.encode(), None, META)


@pytest.fixture()
def db(sadb):
    load(sadb, "operating_companies", "name\nWFC-UAE\nWFC-KE\n")
    load(sadb, "airports", "iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\n"
                           "NBO,Jomo Kenyatta International,KE,Africa/Nairobi\nKGL,Kigali International,RW,Africa/Kigali\n")
    load(sadb, "airlines", "iata_code,name,country\nXA,Example Air,AE\n")
    ids = {}
    for name, url, auth in (("Example Air newsroom", "https://example-air.example", "company_release"),
                            ("Cargo trade wire", "https://tradewire.example", "trade_press"),
                            ("Example Air procurement portal", "https://tenders.example-air.example", "official_portal"),
                            ("Another newsletter", "https://newsletter.example", "trade_press")):
        ids[name] = srcs.create_source(sadb, srcs.SourceSpec(name, "web_page", url, auth, retention_permitted=True, enabled=True), META)
    sadb.src = {n: ing.SourceInfo(i, n.lower().replace(" ", "-"), sadb.one("source_get", id=i)["authority"],
                                  sadb.one("source_get", id=i)["base_url"], True) for n, i in ids.items()}  # type: ignore[attr-defined]
    return sadb


ROUTE_Q = "Example Air will operate a twice-weekly Boeing 777F service from 3 November 2026"
TENDER_Q = "Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya and Uganda."
TENDER_Q_TEXT = "Example Air invites proposals from GSSA providers for cargo sales and service\nrepresentation in Kenya and Uganda."


def route(stance="supports"):
    return ing.ClaimProposal("route_launch", ROUTE_Q, {"airline": F("Example Air", ROUTE_Q),
                                                       "origin": F("DXB", "between Dubai (DXB) and Nairobi (NBO)"),
                                                       "destination": F("NBO", "between Dubai (DXB) and Nairobi (NBO)")}, stance=stance)


def tender(kind="gssa_tender", *, quote=TENDER_Q, deadline=("2026-11-30T17:00:00", "Proposals must be submitted by 30 November 2026\nat 17:00 East Africa Time"),
           status=("open", TENDER_Q), assessed_by="ai_proposed"):
    fields = {"airline": F("Example Air", "Example Air"), "country": F("Kenya", "representation in Kenya and Uganda"), "service": F("GSSA", "GSSA")}
    if deadline:
        fields["deadline"] = F(*deadline)
    if status:
        fields["status"] = F(*status)
    return ing.ClaimProposal(kind, quote, fields, assessed_by=assessed_by, deadline_timezone="Africa/Nairobi")  # type: ignore[arg-type]


def doc(db, source, url, text, published=None):
    return ing.IncomingDocument(db.src[source], url, url, text, published_at=published or NOW - timedelta(days=1))


def test_route_signal_and_tender_stay_separate(db):
    r1 = ing.ingest(db, doc(db, "Example Air newsroom", "https://example-air.example/news/dxb-nbo", D.ROUTE_ANNOUNCEMENT_OFFICIAL), [route()], now=NOW)
    assert r1.classification == "market_signal" and r1.opportunity_id is None
    gaps = db.pg.val(f"SELECT gaps::text FROM signals WHERE id='{r1.signal_id}'")
    assert "capacity" in gaps and "Representation" in gaps and "payable opportunity" in gaps
    r2 = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/ke-ug", D.GSSA_TENDER_OFFICIAL),
                    [tender(quote=TENDER_Q_TEXT)], now=NOW)
    assert r2.classification == "qualified_opportunity" and r2.opportunity_id
    assert r2.signal_id != r1.signal_id                               # a route announcement is never merged with a tender
    checks = dict(db.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id='{r2.opportunity_id}'"))
    assert checks["existence"] == "pass" and checks["not_expired"] == "pass" and checks["capability"] == "unknown"
    assert db.pg.val(f"SELECT deadline_utc AT TIME ZONE 'UTC' FROM opportunities WHERE id='{r2.opportunity_id}'") == "2026-11-30 14:00:00"
    with pytest.raises(opps.ActionRejected):
        opps.change_stage(db, r2.opportunity_id, "pursuing", "keen", META)


def test_syndicated_copies_collapse_to_one_family(db):
    a = ing.ingest(db, doc(db, "Cargo trade wire", "https://tradewire.example/a", D.ROUTE_ANNOUNCEMENT_SYNDICATED), [route()], now=NOW)
    b = ing.ingest(db, doc(db, "Another newsletter", "https://newsletter.example/b", D.ROUTE_ANNOUNCEMENT_SYNDICATED_2), [route()], now=NOW)
    assert a.family_key == b.family_key and not b.family_new
    assert a.signal_id == b.signal_id
    assert db.pg.val(f"SELECT summary FROM signals WHERE id='{a.signal_id}'") == "2 evidence link(s) across 1 announcement family(ies)"
    again = ing.ingest(db, doc(db, "Cargo trade wire", "https://tradewire.example/a", D.ROUTE_ANNOUNCEMENT_SYNDICATED), [route()], now=NOW)
    assert not again.document_new and db.pg.val("SELECT count(*) FROM claim_evidence") == "2"


def test_revision_then_cancellation_keeps_history(db):
    base = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/ke-ug", D.GSSA_TENDER_OFFICIAL,
                              NOW - timedelta(days=3)), [tender(quote=TENDER_Q_TEXT)], now=NOW)
    revised_q = "The submission deadline is extended to 14 December 2026 at 17:00 East Africa Time."
    # The addendum names no airline or reference: it is its own tender candidate and goes to merge review (never auto-merged).
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/ke-ug/addendum-1",
                           D.GSSA_TENDER_REVISED, NOW - timedelta(days=2)),
                   [ing.ClaimProposal("tender_deadline", revised_q, {"deadline": F("2026-12-14T17:00:00", revised_q),
                                                                    "status": F("revised", revised_q)})], now=NOW)
    assert r.signal_id != base.signal_id and r.opportunity_id is None
    mc = db.pg.val("SELECT count(*) FROM merge_candidates WHERE entity_type='signal' AND status='open'")
    # Without an airline the addendum has no subject to compare with: a reviewer merges it explicitly instead.
    assert mc in ("0", "1")
    left, right = sorted([base.signal_id, r.signal_id])
    db.run("merge_candidate_add", entity_type="signal", left=left, right=right, score=None, reason="reviewer: addendum to the same RFP")
    cand = db.pg.val("SELECT id FROM merge_candidates WHERE status='open' ORDER BY created_at DESC LIMIT 1")
    rev.decide_merge(db, cand, "merged", "addendum 1 to the Kenya/Uganda RFP", META)
    opp = base.opportunity_id
    assert db.pg.val("SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL") == "1"   # merged, not duplicated
    assert db.pg.val(f"SELECT deadline_utc AT TIME ZONE 'UTC' FROM opportunities WHERE id='{opp}'") == "2026-12-14 14:00:00"
    cancel_q = "has been cancelled. Example Air will not proceed with this procurement."
    ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/ke-ug/cancelled", D.GSSA_TENDER_CANCELLED,
                       NOW - timedelta(hours=1)),
               [ing.ClaimProposal("gssa_tender", "NOTICE: The Request for Proposal for GSSA cargo representation in Kenya and Uganda\nhas been cancelled.",
                                  {"airline": F("Example Air", "Example Air will not proceed with this procurement."),
                                   "country": F("Kenya", "GSSA cargo representation in Kenya and Uganda"),
                                   "status": F("cancelled", cancel_q), "service": F("GSSA", "GSSA cargo representation")})], now=NOW)
    # Same airline + Kenya, no reference: the cancellation notice is a separate candidate linked for review, not silently applied.
    assert db.pg.val("SELECT count(*) FROM merge_candidates WHERE entity_type='signal' AND status='open'") == "1"
    cand2 = db.pg.val("SELECT id FROM merge_candidates WHERE status='open'")
    rev.decide_merge(db, cand2, "merged", "cancellation notice for the same RFP", META)
    opp = db.pg.val("SELECT id FROM opportunities WHERE merged_into_id IS NULL ORDER BY created_at LIMIT 1")
    checks = dict(db.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id='{opp}'"))
    assert checks.get("live_status") == "fail"
    assert db.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{opp}'") == "blocked"
    hist = db.pg.rows(f"SELECT field, to_value FROM opportunity_status_history WHERE opportunity_id='{opp}' ORDER BY id")
    assert ["tender_status", "cancelled"] in hist and ["qualification_status", "blocked"] in hist
    assert any(h[0] == "deadline" for h in hist)


def test_contradiction_from_independent_source(db):
    ing.ingest(db, doc(db, "Example Air newsroom", "https://example-air.example/news/dxb-nbo", D.ROUTE_ANNOUNCEMENT_OFFICIAL), [route()], now=NOW)
    text = ("Trade wire: Example Air has postponed its planned freighter launch between Dubai (DXB) and Nairobi (NBO) indefinitely. "
            "Example Air will operate a twice-weekly Boeing 777F service from 3 November 2026 is no longer the plan.")
    ing.ingest(db, doc(db, "Cargo trade wire", "https://tradewire.example/postponed", text), [route("contradicts")], now=NOW)
    assert db.pg.val("SELECT status FROM claims WHERE claim_type='route_launch'") == "contradicted"


def test_inauthentic_tender_page_creates_no_opportunity(db):
    r = ing.ingest(db, ing.IncomingDocument(db.src["Example Air procurement portal"], "https://evil-mirror.example/rfp",
                                            "https://evil-mirror.example/rfp", D.GSSA_TENDER_OFFICIAL), [tender(quote=TENDER_Q_TEXT)], now=NOW)
    assert r.opportunity_id is None and r.classification != "qualified_opportunity"
    assert db.pg.val("SELECT result FROM document_checks WHERE check_type='authenticity'") == "fail"


def _ready(db, deadline_days=20):
    when = datetime.now(UTC) + timedelta(days=deadline_days)
    text = (f"Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya and Uganda. "
            f"Proposals must be submitted by {when.day} {when.strftime('%B %Y')} at 17:00 EAT. The scope covers sales and customer service.")
    r = ing.ingest(db, doc(db, "Example Air procurement portal", f"https://tenders.example-air.example/rfp/ke-{deadline_days}", text,
                           datetime.now(UTC) - timedelta(days=1)),
                   [tender(quote=TENDER_Q, deadline=(when.strftime("%Y-%m-%dT17:00:00"), f"{when.day} {when.strftime('%B %Y')} at 17:00 EAT"),
                           assessed_by="human"),
                    ing.ClaimProposal("tender_scope", "The scope covers sales and customer service.", {}, assessed_by="human")])
    load(db, "capabilities", "operating_company,service_code,status,valid_from,valid_to\nWFC-UAE,GSSA,verified,2025-01-01,2030-12-31\n")
    opps.add_override(db, r.opportunity_id, "eligibility", "pass", "no eligibility criteria published; compliance confirmed", None, META)
    company = db.pg.val("SELECT id FROM operating_companies WHERE name='WFC-UAE'")
    service = db.pg.val("SELECT id FROM services WHERE code='GSSA'")
    return r.opportunity_id, opps.set_scope(db, r.opportunity_id, company, service, META)


def test_capability_comes_from_register_not_override(db):
    opp, status = _ready(db)
    with pytest.raises(opps.ActionRejected):
        opps.add_override(db, opp, "capability", "pass", "We are confident we can do this", None, META)
    assert status == "ready_for_review"
    assert opps.set_scope(db, opp, None, None, META) == "incomplete"


def test_contradiction_after_approval_removes_approval(db):
    opp, status = _ready(db)
    assert opps.approve(db, opp, "Board agreed", META) == "approved_for_pursuit"
    for s in ("reviewing", "qualified", "pursuing"):
        opps.change_stage(db, opp, s, s, META)
    deny = "Example Air confirms it is not running a GSSA tender for Kenya and Uganda this year."
    ing.ingest(db, doc(db, "Example Air newsroom", "https://example-air.example/news/no-gssa-tender", deny),
               [ing.ClaimProposal("gssa_tender", deny, {"airline": F("Example Air", deny), "country": F("Kenya", deny)}, stance="contradicts",
                                  assessed_by="human")], now=datetime.now(UTC))
    # The denial carries no reference either: it is linked for review; once merged, the approval falls.
    cand = db.pg.val("SELECT id FROM merge_candidates WHERE entity_type='signal' AND status='open'")
    assert cand
    rev.decide_merge(db, cand, "merged", "the newsroom denial concerns this RFP", META)
    assert db.pg.val("SELECT count(*) FROM opportunities WHERE merged_into_id IS NULL") == "1"
    live = opp
    assert db.pg.val(f"SELECT result FROM qualification_checks WHERE opportunity_id='{live}' AND check_code='existence'") == "review_required"
    assert db.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{live}'") == "incomplete"
    with pytest.raises(opps.ActionRejected):
        opps.change_stage(db, live, "proposal", "continue", META)


def test_passed_deadline_blocks_approval_and_progression(db):
    opp, _ = _ready(db)
    db.pg.run(f"UPDATE opportunities SET deadline_utc = now() - interval '2 days', deadline_earliest_utc = now() - interval '2 days', "
              f"deadline_latest_utc = now() - interval '2 days' WHERE id='{opp}'")
    with pytest.raises(opps.ActionRejected):
        opps.approve(db, opp, "late approval", META)
    opps.change_stage(db, opp, "reviewing", "look again", META)
    with pytest.raises(opps.ActionRejected):
        opps.change_stage(db, opp, "qualified", "x", META)
    assert db.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{opp}'") == "blocked"


def test_exception_imports_never_multiply_and_resolution_closes_task(db):
    head = "external_id,exception_type,severity,booking_ref,customer,operating_company,description,deadline,status\n"
    f1 = head + ("EX-1,reservation,medium,BK-1,Forwarder A,WFC-UAE,Reservation delayed,2026-10-26T14:00:00+04:00,open\n"
                 "EX-2,reservation,high,BK-1,Forwarder A,WFC-UAE,Reservation delayed again,2026-10-26T14:00:00+04:00,open\n")
    for _ in range(3):
        load(db, "exceptions", f1)
    assert db.pg.val("SELECT count(*) FROM operational_exceptions WHERE status <> 'resolved'") == "1"
    assert db.pg.val("SELECT severity FROM operational_exceptions") == "high"
    assert db.pg.val("SELECT count(*) FROM notifications") == "1" and db.pg.val("SELECT count(*) FROM tasks") == "1"
    exc_id = db.pg.val("SELECT id FROM operational_exceptions")
    assert ops.resolve(db, exc_id, "Space confirmed", META)
    assert db.pg.val("SELECT status FROM tasks") == "done"


def test_bookings_rerun_amend_reverse_and_conflicts(db):
    header = "external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency,operating_company\n"
    b1 = header + ("BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,1000,2500.00,USD,WFC-UAE\n"
                   "BK-2,Forwarder A,XA,NBO,DXB,2026-10-06,2026-10-01T10:00:00+04:00,confirmed,300,900.50,USD,WFC-UAE\n"
                   "BK-X,Forwarder A,XA,DXB,DXB,2026-10-06,2026-10-01T10:00:00+04:00,confirmed,300,900.50,USD,WFC-UAE\n"
                   "BK-Y,Forwarder A,XA,DXB,LHR,2026-10-06,2026-10-01T10:00:00+04:00,confirmed,300,900.50,USD,WFC-NOPE\n")
    first = load(db, "bookings", b1)
    assert first["reconciliation"]["inserted"] == 2 and first["reconciliation"]["rows_quarantined"] == 2 and first["partial"]
    assert sorted(e["field"] for e in first["errors"]) == ["destination", "destination", "operating_company"]
    rerun = load(db, "bookings", b1)
    assert (rerun["reconciliation"]["inserted"], rerun["reconciliation"]["updated"], rerun["reconciliation"]["unchanged"]) == (0, 0, 2)
    amend = header + ("BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,amended,1100,2700.00,USD,WFC-UAE\n"
                      "BK-2,Forwarder A,XA,NBO,DXB,2026-10-06,2026-10-01T10:00:00+04:00,cancelled,300,900.50,USD,WFC-UAE\n")
    res = load(db, "bookings", amend)
    assert res["reconciliation"]["updated"] == 2
    imp.reverse(db, res["job_id"], "amendment file was wrong", META)
    assert db.pg.rows("SELECT external_id, status, chargeable_weight_kg FROM bookings ORDER BY external_id") == [
        ["BK-1", "confirmed", "1000.000"], ["BK-2", "confirmed", "300.000"]]
    assert db.pg.val("SELECT count(*) FROM bookings WHERE forwarder_id IS NULL OR airline_id IS NULL OR operating_company_id IS NULL") == "0"
    later = load(db, "bookings", header + "BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,amended,1500,2700.00,USD,WFC-UAE\n")
    assert later["reconciliation"]["updated"] == 1
    with pytest.raises(imp.ImportRejected) as e:
        imp.reverse(db, first["job_id"], "first file was wrong", META)
    assert e.value.status == 409
    with pytest.raises(imp.ImportRejected) as e:
        load(db, "not_a_dataset", "x\n1\n")
    assert e.value.status == 404


def test_register_writers_are_idempotent(db):
    ag = ("external_id,airline_iata,airline_name,operating_company,territories,services,effective_from,effective_to,exclusivity,appointment_rights\n"
          "AG-1,XA,Example Air,WFC-UAE,AE;OM,GSSA,2024-01-01,2027-12-31,exclusive,may_extend\n"
          "AG-2,QQ,Sample Airways,WFC-KE,KE,GSSA;TCM,2025-01-01,,unknown,\n"
          "AG-3,XA,Example Air,WFC-UAE,QA,NOT_A_SERVICE,,,,\n")
    r = load(db, "agreements", ag)
    assert (r["reconciliation"]["inserted"], r["reconciliation"]["rows_quarantined"]) == (2, 1)
    assert load(db, "agreements", ag)["reconciliation"]["unchanged"] == 2
    assert db.pg.val("SELECT country_code FROM territories WHERE code='OM'") == "OM"
    cap = ("external_id,airline_iata,origin,destination,period_start,period_end,basis,capacity_type,amount,snapshot_at\n"
           "C-1,XA,DXB,NBO,2026-10-01,2026-10-31,weight_kg,bookable,6000,2026-09-30T12:00:00Z\n")
    assert load(db, "capacity", cap)["reconciliation"]["inserted"] == 1
    assert load(db, "capacity", cap)["reconciliation"]["unchanged"] == 1
    q = ("external_id,forwarder,origin,destination,quoted_at,status,lost_reason,chargeable_weight,amount,currency\n"
         "Q-1,Forwarder A,DXB,NBO,2026-10-02T09:00:00Z,lost,price,500,1200.00,USD\n")
    assert load(db, "quotes", q)["reconciliation"]["inserted"] == 1
    assert load(db, "quotes", q)["reconciliation"]["unchanged"] == 1
    cp = ("operating_company,service_code,station,status,verification_owner,valid_from,valid_to,languages\n"
          "WFC-UAE,GSSA,DXB,verified,Ops director,2025-01-01,2027-12-31,EN;AR\nWFC-UAE,TRAINING,,verified,,2025-01-01,,EN\n")
    assert load(db, "capabilities", cp)["reconciliation"]["inserted"] == 2
    assert load(db, "capabilities", cp)["reconciliation"]["unchanged"] == 2

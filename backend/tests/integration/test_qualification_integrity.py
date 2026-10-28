"""Directive §8 and acceptance tests 2, 5, 6, 7: a supported tender progresses
through review and qualification; scope changes recompute every dependent
check; station-specific capability never establishes general coverage;
required credentials must be held and valid on the delivery date; an
approval lapses when the conditions it was given on change.
Real PostgreSQL, production adapter, reviewer actions through the services
the API calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.field_validation import FieldClaim as F
from app.services import imports_service as imp
from app.services import ingestion as ing
from app.services import opportunity_service as opps
from app.services import review_service as rev
from app.services import sources_service as srcs
from app.services.audit import RequestMeta

META = RequestMeta(ip="203.0.113.10", request_id="req-q", session_ref="sessqualify01")
FUTURE = (datetime.now(timezone.utc) + timedelta(days=40)).date()
DOC = f"""Request for Proposal: GSSA, cargo, Kenya.
Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya.
Tender reference EXA-CGO-2027-001.
Proposals must be submitted by {FUTURE.day} {FUTURE.strftime('%B %Y')} at 17:00 EAT.
Eligible bidders must hold IATA cargo agent accreditation.
The scope covers sales, documentation and customer service for all cargo products."""
Q1 = "Example Air invites proposals from GSSA providers for cargo sales and service representation in Kenya."


def setup(db):
    for ds, text in {
        "operating_companies": "name,country\nWFC-UAE,AE\nWFC-KE,KE\n",
        "airports": ("iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\nNBO,Jomo Kenyatta International,KE,Africa/Nairobi\n"
                     "LHR,London Heathrow,GB,Europe/London\n"),
        "capabilities": ("operating_company,service_code,station,status,valid_from,valid_to\n"
                         f"WFC-UAE,GSSA,LHR,verified,2025-01-01,{FUTURE + timedelta(days=365)}\n"),
    }.items():
        imp.import_file(db, ds, f"{ds}.csv", text.encode(), None, META)
    sid = srcs.create_source(db, srcs.SourceSpec("Example Air procurement portal", "web_page", "https://tenders.example-air.example/rfp",
                                                 "official_portal", country_coverage=["KE"], retention_permitted=True, enabled=True), META)
    src = ing.SourceInfo(sid, "tenders-example-air-example", "official_portal", "https://tenders.example-air.example/rfp", True)
    props = [
        ing.ClaimProposal("gssa_tender", Q1, {"airline": F("Example Air", Q1), "country": F("Kenya", Q1), "service": F("GSSA", Q1),
                                              "tender_ref": F("EXA-CGO-2027-001", "Tender reference EXA-CGO-2027-001."),
                                              "status": F("open", Q1),
                                              "deadline": F(f"{FUTURE.isoformat()}T17:00:00", f"Proposals must be submitted by {FUTURE.day} {FUTURE.strftime('%B %Y')} at 17:00 EAT.")},
                          deadline_timezone="Africa/Nairobi"),
        ing.ClaimProposal("eligibility", "Eligible bidders must hold IATA cargo agent accreditation.",
                          {"eligibility": F("IATA cargo agent accreditation", "Eligible bidders must hold IATA cargo agent accreditation.")}),
        ing.ClaimProposal("tender_scope", "The scope covers sales, documentation and customer service for all cargo products.", {}),
    ]
    r = ing.ingest(db, ing.IncomingDocument(src, "https://tenders.example-air.example/rfp/ke", "https://tenders.example-air.example/rfp/ke",
                                            DOC, published_at=datetime.now(timezone.utc) - timedelta(days=1)), props)
    company = db.pg.val("SELECT id FROM operating_companies WHERE name='WFC-UAE'")
    gssa = db.pg.val("SELECT id FROM services WHERE code='GSSA'")
    return r, company, gssa


def checks(db, opp):
    return dict(db.pg.rows(f"SELECT check_code, result FROM qualification_checks WHERE opportunity_id='{opp}'"))


def confirm_all(db, opp):
    for (cid,) in db.pg.rows(f"SELECT c.id FROM opportunities o JOIN signal_claims sc ON sc.signal_id=o.signal_id "
                             f"JOIN claims c ON c.id=sc.claim_id WHERE o.id='{opp}'"):
        rev.confirm_claim(db, cid, "checked against the portal", META)


def test_supported_tender_progresses_through_review_and_qualification(sadb):
    """Acceptance 2."""
    r, company, gssa = setup(sadb)
    opp = r.opportunity_id
    assert r.classification == "qualified_opportunity" and r.qualification_status == "incomplete"
    assert checks(sadb, opp)["evidence_reviewed"] == "unknown"           # AI-proposed: awaits a reviewer
    with pytest.raises(opps.ActionRejected):
        opps.approve(sadb, opp, "keen", META)
    confirm_all(sadb, opp)
    assert checks(sadb, opp)["evidence_reviewed"] == "pass"
    assert opps.set_scope(sadb, opp, company, gssa, META, station_code="LHR", delivery_start=FUTURE) == "incomplete"
    assert checks(sadb, opp)["capability"] == "pass"
    # Eligibility and scope are commercial judgements a reviewer may record (with a reason); factual checks are not.
    with pytest.raises(opps.ActionRejected):
        opps.add_override(sadb, opp, "capability", "pass", "We are confident about this one", None, META)
    opps.add_override(sadb, opp, "eligibility", "pass", "WFC-UAE holds IATA cargo agent accreditation (cert 123)", None, META)
    assert opps.set_scope(sadb, opp, company, gssa, META, station_code="LHR", delivery_start=FUTURE) == "ready_for_review"
    assert opps.approve(sadb, opp, "Commercial committee approved", META) == "approved_for_pursuit"
    for stage in ("reviewing", "qualified", "pursuing", "proposal"):
        opps.change_stage(sadb, opp, stage, f"moving to {stage}", META)
    hist = [h[0] for h in sadb.pg.rows(f"SELECT to_value FROM opportunity_status_history WHERE opportunity_id='{opp}' "
                                       "AND field='commercial_stage' ORDER BY id")]
    assert hist == ["reviewing", "qualified", "pursuing", "proposal"]


def test_station_and_scope_rules_and_approval_lapse(sadb):
    """Acceptance 5 and 6, plus approval re-evaluation on scope change."""
    r, company, gssa = setup(sadb)
    opp = r.opportunity_id
    confirm_all(sadb, opp)
    opps.add_override(sadb, opp, "eligibility", "pass", "WFC-UAE holds the accreditation (cert 123)", None, META)
    # 6: verified at LHR only => unknown station is NOT ready, and DXB is not ready.
    opps.set_scope(sadb, opp, company, gssa, META)
    assert checks(sadb, opp)["capability"] == "unknown"
    assert "recorded only at LHR" in sadb.pg.val(f"SELECT rationale FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='capability'")
    assert opps.set_scope(sadb, opp, company, gssa, META, station_code="DXB") == "blocked"
    assert "no capability record for GSSA at DXB" in sadb.pg.val(
        f"SELECT rationale FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='capability'")
    assert opps.set_scope(sadb, opp, company, gssa, META, station_code="LHR", delivery_start=FUTURE) == "ready_for_review"
    opps.approve(sadb, opp, "approved on LHR scope", META)
    # Changing the delivery date (still capable) lapses the approval: re-approval required on the new basis.
    assert opps.set_scope(sadb, opp, company, gssa, META, station_code="LHR", delivery_start=FUTURE + timedelta(days=10)) == "ready_for_review"
    reason = sadb.pg.val(f"SELECT reason FROM opportunity_status_history WHERE opportunity_id='{opp}' AND field='qualification_status' "
                         "ORDER BY id DESC LIMIT 1")
    assert "approval withdrawn" in reason and "delivery_start" in reason
    opps.approve(sadb, opp, "re-approved", META)
    # 5: clearing company and service removes the capability pass and the approval.
    assert opps.set_scope(sadb, opp, None, None, META) == "incomplete"
    assert checks(sadb, opp)["capability"] == "unknown"
    assert "operating company and service not assigned" in sadb.pg.val(
        f"SELECT rationale FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='capability'")
    with pytest.raises(opps.ActionRejected):
        opps.change_stage(sadb, opp, "qualified", "x", META)


def test_missing_or_expired_credentials_prevent_readiness(sadb):
    """Acceptance 7, with the credential register imported (not inserted)."""
    r, company, gssa = setup(sadb)
    opp = r.opportunity_id
    confirm_all(sadb, opp)
    opps.add_override(sadb, opp, "eligibility", "pass", "accreditation confirmed by compliance", None, META)
    status = opps.set_scope(sadb, opp, company, gssa, META, station_code="LHR", delivery_start=FUTURE,
                            required_credentials=["IATA_CARGO_AGENT"])
    assert status == "blocked" and "required credential 'IATA_CARGO_AGENT' not held" in sadb.pg.val(
        f"SELECT rationale FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='capability'")
    # Held but expiring before the delivery date: still blocked (imports re-evaluate live opportunities).
    expired = (f"external_id,operating_company,credential_type,service_code,station,issued_on,expires_on\n"
               f"CR-1,WFC-UAE,IATA_CARGO_AGENT,GSSA,,2024-01-01,{FUTURE - timedelta(days=1)}\n")
    res = imp.import_file(sadb, "training_credentials", "cr.csv", expired.encode(), None, META)
    assert res["opportunities_recomputed"] >= 1
    assert sadb.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{opp}'") == "blocked"
    assert "expired" in sadb.pg.val(f"SELECT rationale FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='capability'")
    # Held only at another station: not ready at LHR.
    elsewhere = expired.replace(f"{FUTURE - timedelta(days=1)}", f"{FUTURE + timedelta(days=400)}").replace("GSSA,,", "GSSA,DXB,")
    imp.import_file(sadb, "airports", "a.csv", b"iata_code,name,country,timezone\nDXB,Dubai International,AE,Asia/Dubai\n", None, META)
    imp.import_file(sadb, "training_credentials", "cr2.csv", elsewhere.encode(), None, META)
    assert "held only at DXB" in sadb.pg.val(f"SELECT rationale FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='capability'")
    # Valid company-wide on the delivery date: ready.
    valid = elsewhere.replace("GSSA,DXB,", "GSSA,,")
    imp.import_file(sadb, "training_credentials", "cr3.csv", valid.encode(), None, META)
    assert sadb.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{opp}'") == "ready_for_review"


def test_reviewer_rejects_corrects_and_adds_claims(sadb):
    r, company, gssa = setup(sadb)
    doc = r.document_id
    tender_claim = sadb.pg.val("SELECT id FROM claims WHERE claim_type='gssa_tender'")
    # Correct a field: the reviewer's deadline must still be stated by its own quote.
    bad = rev.correct_claim(sadb, tender_claim, document_id=doc, claim_type=None, quote=None,
                            fields={"deadline": {"value": "2027-02-01T17:00:00", "quote": "Tender reference EXA-CGO-2027-001."}},
                            note="deadline looked wrong", meta=META)
    assert bad["replacement_claim_ids"]
    fields = dict(sadb.pg.rows(f"SELECT field, support FROM claim_fields WHERE claim_id='{bad['replacement_claim_ids'][0]}'"))
    assert fields["deadline"] == "unsupported"                       # a reviewer cannot assert an unstated deadline either
    assert sadb.pg.val(f"SELECT review_status FROM claims WHERE id='{tender_claim}'") == "corrected"
    # Reject the eligibility claim; add a scope claim by hand from the document text.
    elig = sadb.pg.val("SELECT id FROM claims WHERE claim_type='eligibility'")
    rev.reject_claim(sadb, elig, "not relevant to WFC", META)
    assert sadb.pg.val(f"SELECT status FROM claims WHERE id='{elig}'") == "withdrawn"
    added = rev.add_claim(sadb, doc, claim_type="route_launch", quote="Tender reference EXA-CGO-2027-001.", fields={}, meta=META)
    assert added["claim_ids"] == [] and "does not describe a route launch" in added["rejected"][0]
    assert sadb.pg.val("SELECT count(*) FROM extraction_rejections WHERE status='open'") == "1"
    rid = sadb.pg.val("SELECT id FROM extraction_rejections")
    rev.resolve_rejection(sadb, rid, "dismissed", "entered in error", META)
    assert sadb.pg.val("SELECT status FROM extraction_rejections") == "dismissed"

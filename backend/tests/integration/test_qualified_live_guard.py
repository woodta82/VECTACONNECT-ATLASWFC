"""No historical, excluded, contradictory, cancelled, unsupported or stale record ever appears as a qualified live
opportunity, in any area (28 Oct 2026 instruction, item 6).

"Qualified live" means qualification_status ready_for_review or approved_for_pursuit. Each scenario starts from the
same inputs that DO qualify a record, changes one thing, and checks that the record cannot reach (or keep) that status,
that approval is refused, and that the cross-area invariant query finds nothing. Factual checks (from evidence and WFC
records) and commercial checks (settled by a recorded human judgement) stay separate: no override can pass a factual
check.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain import qualification as qual
from app.domain.field_validation import FieldClaim as F
from app.services import ingestion as ing
from app.services import modules_service as mod
from app.services import opportunity_service as opps
from tests.integration.test_business_workflows import SEP, seed as wf_seed
from tests.integration.test_evidence_regressions import META, TENDER_Q, db, doc, load, tender  # noqa: F401

UTC = timezone.utc
LIVE = ("ready_for_review", "approved_for_pursuit")

# Every opportunity shown as qualified-live must be: live tender status (or an internal-record opportunity), freight in
# scope, every factual check passing, and every claim behind it reviewed by a person.
INVARIANT = """
SELECT o.id, o.title, o.tender_status, o.freight_scope, o.qualification_status
FROM opportunities o
WHERE o.merged_into_id IS NULL AND o.qualification_status IN ('ready_for_review', 'approved_for_pursuit')
  AND ( (o.origin_ref IS NULL AND coalesce(o.tender_status, '') NOT IN ('open', 'revised'))
     OR coalesce(o.freight_scope, '') IN ('passenger', 'not_freight')
     OR EXISTS (SELECT 1 FROM qualification_checks q WHERE q.opportunity_id = o.id AND q.blocking AND q.result <> 'pass'
                AND q.check_code IN ({factual})) )"""


def violations(db):  # noqa: F811
    factual = ", ".join(f"'{c}'" for c in sorted(qual.FACTUAL_CHECKS))
    return db.pg.rows(INVARIANT.format(factual=factual))


def _qualify(db, opp):  # noqa: F811
    """The commercial judgements and scope that DO qualify a clean tender."""
    load(db, "capabilities", "operating_company,service_code,status,valid_from,valid_to\nWFC-UAE,GSSA,verified,2025-01-01,2030-12-31\n")
    opps.add_override(db, opp, "eligibility", "pass", "no eligibility criteria published; compliance confirmed", None, META)
    company = db.pg.val("SELECT id FROM operating_companies WHERE name='WFC-UAE'")
    service = db.pg.val("SELECT id FROM services WHERE code='GSSA'")
    return opps.set_scope(db, opp, company, service, META)


def _assert_never_live(db, opp):  # noqa: F811
    assert db.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{opp}'") not in LIVE
    with pytest.raises(opps.ActionRejected):
        opps.approve(db, opp, "try to approve anyway", META)
    assert violations(db) == []


def _tender_text(days: int) -> str:
    when = datetime.now(UTC) + timedelta(days=days)
    return (f"{TENDER_Q} Proposals must be submitted by {when.day} {when.strftime('%B %Y')} at 17:00 EAT. "
            "The scope covers cargo sales and customer service.")


def _deadline(days: int):
    when = datetime.now(UTC) + timedelta(days=days)
    return (when.strftime("%Y-%m-%dT17:00:00"), f"{when.day} {when.strftime('%B %Y')} at 17:00 EAT")


SCOPE = ing.ClaimProposal("tender_scope", "The scope covers cargo sales and customer service.", {}, assessed_by="human")


# ------------------------------------------------------------------ the control: a clean tender DOES qualify
def test_control_clean_reviewed_tender_qualifies(db):  # noqa: F811
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/clean", _tender_text(20),
                           datetime.now(UTC) - timedelta(days=1)), [tender(deadline=_deadline(20), assessed_by="human"), SCOPE])
    assert _qualify(db, r.opportunity_id) == "ready_for_review"
    assert opps.approve(db, r.opportunity_id, "pursue", META) == "approved_for_pursuit"
    assert violations(db) == []


# ------------------------------------------------------------------ unsupported: claims nobody has reviewed
def test_unsupported_ai_proposed_claims_never_qualify(db):  # noqa: F811
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/ai", _tender_text(20),
                           datetime.now(UTC) - timedelta(days=1)), [tender(deadline=_deadline(20), assessed_by="ai_proposed"), SCOPE])
    assert _qualify(db, r.opportunity_id) not in LIVE
    _assert_never_live(db, r.opportunity_id)


# ------------------------------------------------------------------ historical: an old notice whose deadline has passed
def test_historical_notice_never_qualifies(db):  # noqa: F811
    old = datetime.now(UTC) - timedelta(days=400)
    text = (f"{TENDER_Q} Proposals must be submitted by {old.day} {old.strftime('%B %Y')} at 17:00 EAT.")
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/old", text, old - timedelta(days=30)),
                   [tender(deadline=(old.strftime("%Y-%m-%dT17:00:00"), f"{old.day} {old.strftime('%B %Y')} at 17:00 EAT"), assessed_by="human"),
                    SCOPE])
    assert r.opportunity_id                            # recorded, so the check below is not vacuous
    assert db.pg.val(f"SELECT check_code FROM qualification_checks WHERE opportunity_id='{r.opportunity_id}' AND result <> 'pass' "
                     "AND check_code = 'not_expired'") == "not_expired"
    _qualify(db, r.opportunity_id)
    _assert_never_live(db, r.opportunity_id)


# ------------------------------------------------------------------ excluded: passenger-only mandate
def test_passenger_only_mandate_never_qualifies(db):  # noqa: F811
    q = "Example Air invites proposals for passenger sales and ticketing representation in Kenya."
    when = datetime.now(UTC) + timedelta(days=20)
    text = f"{q} Proposals must be submitted by {when.day} {when.strftime('%B %Y')} at 17:00 EAT."
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/pax", text, datetime.now(UTC) - timedelta(days=1)),
                   [ing.ClaimProposal("gssa_tender", q, {"airline": F("Example Air", q), "country": F("Kenya", q), "service": F("GSSA", q),
                                                         "status": F("open", q), "deadline": F(*_deadline(20))}, assessed_by="human",
                                      deadline_timezone="Africa/Nairobi")])
    assert r.classification == "excluded" and r.opportunity_id is None   # kept as an excluded signal, never an opportunity
    assert db.pg.val("SELECT count(*) FROM opportunities") == "0" and violations(db) == []


# ------------------------------------------------------------------ contradictory: the notice announces and cancels
def test_self_contradicting_notice_never_qualifies(db):  # noqa: F811
    text = _tender_text(20) + " Update: this tender has been cancelled."
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/contra", text,
                           datetime.now(UTC) - timedelta(days=1)), [tender(deadline=_deadline(20), assessed_by="human"), SCOPE])
    assert r.opportunity_id
    assert db.pg.val(f"SELECT tender_status FROM opportunities WHERE id='{r.opportunity_id}'") not in ("open", "revised")
    _qualify(db, r.opportunity_id)
    _assert_never_live(db, r.opportunity_id)


# ------------------------------------------------------------------ cancelled after approval: approval is withdrawn
def test_cancellation_after_approval_withdraws_qualification(db):  # noqa: F811
    url = "https://tenders.example-air.example/rfp/later-cancelled"
    r = ing.ingest(db, doc(db, "Example Air procurement portal", url, _tender_text(20), datetime.now(UTC) - timedelta(days=3)),
                   [tender(deadline=_deadline(20), assessed_by="human", quote=TENDER_Q), SCOPE])
    assert _qualify(db, r.opportunity_id) == "ready_for_review"
    opps.approve(db, r.opportunity_id, "pursue", META)
    cancel = "The Request for Proposal for GSSA cargo representation in Kenya and Uganda has been cancelled by Example Air."
    ing.ingest(db, doc(db, "Example Air procurement portal", url + "/notice", cancel, datetime.now(UTC) - timedelta(hours=1)),
               [ing.ClaimProposal("tender_status", cancel, {"airline": F("Example Air", cancel), "country": F("Kenya", cancel),
                                                            "status": F("cancelled", cancel), "service": F("GSSA", cancel)}, assessed_by="human")])
    live = db.pg.rows("SELECT id FROM opportunities WHERE merged_into_id IS NULL AND qualification_status IN ('ready_for_review','approved_for_pursuit')")
    cancelled = db.pg.rows("SELECT id FROM opportunities WHERE tender_status = 'cancelled'")
    assert not ({x[0] for x in live} & {x[0] for x in cancelled})
    assert violations(db) == []


# ------------------------------------------------------------------ a commercial override never passes a factual check
@pytest.mark.parametrize("code", sorted(qual.FACTUAL_CHECKS))
def test_factual_checks_cannot_be_overridden(db, code):  # noqa: F811
    r = ing.ingest(db, doc(db, "Example Air procurement portal", "https://tenders.example-air.example/rfp/ovr", _tender_text(20),
                           datetime.now(UTC) - timedelta(days=1)), [tender(deadline=_deadline(20), assessed_by="ai_proposed"), SCOPE])
    with pytest.raises(opps.ActionRejected):
        opps.add_override(db, r.opportunity_id, code, "pass", "we are confident", None, META)


# ------------------------------------------------------------------ the module areas: no action, stale data
def test_module_areas_refuse_unsupported_recommendations_and_stale_data(sadb):  # noqa: F811
    wf_seed(sadb)
    # no action (insufficient data) -> no opportunity
    cl = mod.capacity_lanes(sadb, *SEP)
    gap = next(x["recommendation"] for x in cl["lanes"] if x["lane"] == "DXB→EBB")
    with pytest.raises(mod.ModuleRejected):
        mod.opportunity_from_capacity(sadb, gap["key"], *SEP, META)
    tech = mod.technology_solutions(sadb, *SEP)
    insufficient = next(s for s in tech["solutions"] if s["kind"] == "insufficient_data")
    with pytest.raises(mod.ModuleRejected):
        mod.opportunity_from_solution(sadb, insufficient["key"], *SEP, META)
    # a contract that prohibits extension blocks the account-growth candidate
    ag = mod.account_growth(sadb, on=date(2026, 10, 15))
    prohibited = next(c for c in ag["candidates"] if c["airline"] == "Sample Airways")
    res = mod.opportunity_from_account_growth(sadb, prohibited["key"], META)
    assert sadb.pg.val(f"SELECT qualification_status FROM opportunities WHERE id='{res['opportunity_id']}'") == "blocked"
    # stale bookings: the capacity recommendation can be recorded but cannot qualify (data_current fails, blocking)
    sadb.pg.run("UPDATE import_jobs SET created_at = created_at - interval '5 days', committed_at = committed_at - interval '5 days' "
                "WHERE dataset IN ('bookings', 'capacity')")
    sadb.pg.run("UPDATE ingestion_runs SET finished_at = finished_at - interval '5 days', started_at = started_at - interval '5 days'")
    cl = mod.capacity_lanes(sadb, *SEP)
    assert any(s["status"] == "stale" for s in cl["sources"]), cl["sources"]
    add = next(x["recommendation"] for x in cl["lanes"] if x["lane"] == "DXB→NBO")
    opp = mod.opportunity_from_capacity(sadb, add["key"], *SEP, META)["opportunity_id"]
    assert sadb.pg.val(f"SELECT result FROM qualification_checks WHERE opportunity_id='{opp}' AND check_code='data_current'") == "fail"
    _assert_never_live(sadb, opp)
    # outsourcing never lists a non-live tender as demand: covered with data in test_business_workflows::test_7

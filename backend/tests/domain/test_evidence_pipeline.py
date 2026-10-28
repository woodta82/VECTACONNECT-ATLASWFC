"""Verification matrix #1 (end-to-end evidence), #2 (deduplication), #3 (contradiction).

The flow source document -> family -> claim -> signal classification ->
tender state -> qualification is exercised with the pure domain rules.
The database-backed version of the same journey runs in the service layer.
"""
from datetime import datetime, timedelta, timezone

from app.domain import evidence as ev
from app.domain import qualification as q
from tests.fixtures import documents as D

UTC = timezone.utc
NOW = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)


def test_canonical_url_strips_tracking_and_normalises():
    a = ev.canonicalize_url("HTTPS://www.Example.com:443/news/route/?utm_source=x&b=2&a=1#top")
    b = ev.canonicalize_url("https://example.com/news/route?a=1&b=2&fbclid=zzz")
    assert a == b == "https://example.com/news/route?a=1&b=2"


def test_syndicated_copies_form_one_family_and_unrelated_does_not():
    fam1, new1, _ = ev.assign_family(D.ROUTE_ANNOUNCEMENT_OFFICIAL, [])
    assert new1
    existing = [ev.FamilyCandidate(fam1, ev.shingles(ev.normalise_text(D.ROUTE_ANNOUNCEMENT_OFFICIAL)))]
    fam2, new2, sim2 = ev.assign_family(D.ROUTE_ANNOUNCEMENT_SYNDICATED, existing)
    fam3, new3, _ = ev.assign_family(D.ROUTE_ANNOUNCEMENT_SYNDICATED_2, existing)
    assert (fam2, new2) == (fam1, False) and sim2 >= ev.FAMILY_THRESHOLD
    assert (fam3, new3) == (fam1, False)
    fam4, new4, _ = ev.assign_family(D.UNRELATED_ANNOUNCEMENT, existing)
    assert new4 and fam4 != fam1


def test_syndication_does_not_inflate_confidence():
    links = [
        ev.EvidenceLink("d1", "famA", "company_release", "supports", authentic="pass"),
        ev.EvidenceLink("d2", "famA", "trade_press", "supports"),
        ev.EvidenceLink("d3", "famA", "trade_press", "supports"),
    ]
    a = ev.assess_claim(links)
    assert a.status == "supported"
    assert a.supporting_documents == 3
    assert a.supporting_families == 1  # three copies, one announcement


def test_reachable_but_inauthentic_document_does_not_support():
    assert ev.authenticity_check("https://example-air.example/news/1", "https://www.example-air.example") == "pass"
    assert ev.authenticity_check("https://example-air.example.attacker.net/p", "https://example-air.example") == "fail"
    a = ev.assess_claim([ev.EvidenceLink("d1", "famA", "official_portal", "supports", authentic="fail")])
    assert a.status == "unverified"


def test_contradiction_is_kept_and_requires_review():
    a = ev.assess_claim([
        ev.EvidenceLink("d1", "famA", "company_release", "supports"),
        ev.EvidenceLink("d2", "famB", "trade_press", "contradicts"),
    ])
    assert a.status == "contradicted" and a.needs_review and a.contradicting_families == 1


def _obs(doc, fam, authority, days, status=None, deadline=None, source_family="example-air-portal"):
    return ev.TenderObservation(doc, fam, source_family, authority, NOW - timedelta(days=days), status, deadline, "Africa/Nairobi")


DEADLINE_1 = datetime(2026, 11, 30, 14, 0, tzinfo=UTC)   # 17:00 EAT
DEADLINE_2 = datetime(2026, 12, 14, 14, 0, tzinfo=UTC)


def test_e2e_route_signal_then_tender_qualification():
    # Step 1: a route announcement only -> market signal with explicit gaps.
    cls = q.classify_airline_signal(claim_types={"route_launch"}, tender_existence=None)
    assert cls == "market_signal"

    # Step 2: an official tender document arrives.
    existence = ev.assess_claim([ev.EvidenceLink("t1", "famT", "official_portal", "supports", authentic="pass")])
    tender = ev.resolve_tender([_obs("t1", "famT", "official_portal", 2, "open", DEADLINE_1)], NOW)
    assert tender.status == "open" and tender.actionable and tender.deadline_utc == DEADLINE_1
    cls = q.classify_airline_signal(claim_types={"route_launch", "gssa_tender"}, tender_existence=existence)
    assert cls == "qualified_opportunity"

    # Qualification covers only the supported scope: eligibility not yet assessed -> incomplete, not approved.
    checks = q.airline_representation_checks(existence=existence, tender=tender, territory_cell_state="gap",
                                             capability_readiness="ready", eligibility_known=None, eligibility_met=None,
                                             scope_known=True)
    assert q.qualification_status(checks) == "incomplete"
    assert {c.code: c.result for c in checks}["eligibility"] == "unknown"

    # Once eligibility is established from the tender text, it becomes ready for (human) review — but only when the notice
    # establishes CARGO relevance (27 Oct, second instruction): without it the record stays pending review.
    checks = q.airline_representation_checks(existence=existence, tender=tender, territory_cell_state="gap",
                                             capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                             scope_known=True)
    assert q.qualification_status(checks) == "incomplete"
    assert {c.code: c.result for c in checks}["freight_relevance"] == "review_required"
    checks = q.airline_representation_checks(existence=existence, tender=tender, territory_cell_state="gap",
                                             capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                             scope_known=True, freight_scope="cargo", freight_reason="cargo relevance stated (cargo)")
    status = q.qualification_status(checks)
    assert status == "ready_for_review"
    assert q.approve_for_pursuit(status) == "approved_for_pursuit"


def test_unverified_tender_mention_is_a_lead_not_an_opportunity():
    existence = ev.assess_claim([ev.EvidenceLink("p1", "famP", "trade_press", "supports")])
    assert q.classify_airline_signal(claim_types={"gssa_tender"}, tender_existence=existence) == "unverified_lead"


def test_revised_tender_updates_deadline_with_history():
    t = ev.resolve_tender([
        _obs("t1", "famT", "official_portal", 10, "open", DEADLINE_1),
        _obs("t2", "famR", "official_portal", 1, "revised", DEADLINE_2),
    ], NOW)
    assert t.deadline_utc == DEADLINE_2 and not t.deadline_conflict and t.actionable
    assert [h["field"] for h in t.history] == ["status", "deadline", "status", "deadline"]


def test_conflicting_independent_deadlines_are_not_merged():
    t = ev.resolve_tender([
        _obs("t1", "famT", "official_portal", 10, "open", DEADLINE_1, source_family="portal"),
        _obs("p1", "famP", "company_release", 1, None, DEADLINE_2, source_family="airline-newsroom"),
    ], NOW)
    assert t.deadline_conflict and t.deadline_utc is None and not t.actionable
    checks = q.airline_representation_checks(existence=ev.assess_claim([ev.EvidenceLink("t1", "famT", "official_portal", "supports")]),
                                             tender=t, territory_cell_state="gap", capability_readiness="ready",
                                             eligibility_known=True, eligibility_met=True, scope_known=True)
    assert q.qualification_status(checks) != "ready_for_review"


def test_cancelled_tender_is_not_actionable_and_history_kept():
    t = ev.resolve_tender([
        _obs("t1", "famT", "official_portal", 10, "open", DEADLINE_1),
        _obs("t3", "famC", "official_portal", 1, "cancelled"),
    ], NOW)
    assert t.status == "cancelled" and not t.actionable
    assert any(h["to"] == "cancelled" for h in t.history)


def test_expired_deadline_cannot_remain_actionable_or_be_overridden():
    later = DEADLINE_1 + timedelta(hours=1)
    t = ev.resolve_tender([_obs("t1", "famT", "official_portal", 40, "open", DEADLINE_1)], later)
    assert t.status == "expired" and not t.actionable
    existence = ev.assess_claim([ev.EvidenceLink("t1", "famT", "official_portal", "supports")])
    checks = q.airline_representation_checks(existence=existence, tender=t, territory_cell_state="gap",
                                             capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                             scope_known=True)
    assert q.qualification_status(checks) == "blocked"
    import pytest
    with pytest.raises(q.OverrideRejected):
        q.apply_overrides(checks, [q.Override("not_expired", "pass", "Client says they will accept late bids", later)], later)


def test_lower_authority_status_does_not_override_official():
    t = ev.resolve_tender([
        _obs("t1", "famT", "official_portal", 10, "open", DEADLINE_1),
        _obs("p9", "famZ", "trade_press", 1, "cancelled"),
    ], NOW)
    assert t.status == "open" and t.actionable
    assert any("lower-authority" in r for r in t.reasons)


def test_unknown_deadline_is_unknown_not_fail():
    t = ev.resolve_tender([_obs("t1", "famT", "official_portal", 1, "open", None)], NOW)
    existence = ev.assess_claim([ev.EvidenceLink("t1", "famT", "official_portal", "supports")])
    checks = q.airline_representation_checks(existence=existence, tender=t, territory_cell_state="gap",
                                             capability_readiness="ready", eligibility_known=True, eligibility_met=True,
                                             scope_known=True)
    c = {c.code: c for c in checks}["not_expired"]
    assert c.result == "unknown"
    assert q.qualification_status(checks) == "incomplete"

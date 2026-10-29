"""Relationship health, momentum, attention and contact relevance (29 Oct 2026: ATLAS v1.0 parameters)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain import contact_relevance as cr
from app.domain import relationship_health as rh
from app.domain import research_plan as plan

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)


def _components(**over):
    base = {"recency": rh.recency(NOW - timedelta(days=5), NOW), "frequency": rh.frequency(6), "responsiveness": rh.responsiveness(4, 3),
            "meeting_outcomes": rh.meeting_outcomes(2, 1, 0), "influence": rh.influence("economic_buyer", "final"),
            "opportunity_alignment": rh.opportunity_alignment(1, 59), "strategic_value": rh.strategic_value(True, True, "airline")}
    base.update(over)
    return base


def test_weights_add_to_one_and_a_well_kept_buyer_relationship_is_strong():
    assert round(sum(rh.WEIGHTS.values()), 6) == 1.0
    h = rh.compute(_components())
    assert h["assessed"] and h["band"] == "strong" and h["score"] >= 75 and not h["at_risk"]
    assert {c["factor"] for c in h["contributions"]} == set(rh.WEIGHTS)
    assert all("note" in c for c in h["contributions"])


def test_recency_decays_non_linearly():
    assert rh.recency(NOW - timedelta(days=10), NOW)["score"] == 100 and rh.recency(NOW - timedelta(days=30), NOW)["score"] == 85
    assert rh.recency(NOW - timedelta(days=90), NOW)["score"] == 45 and rh.recency(NOW - timedelta(days=181), NOW)["score"] == 5
    assert rh.recency(None, NOW) == {"score": 0.0, "note": "No engagement recorded"}


def test_a_quiet_economic_buyer_is_at_risk_not_healthy():
    """ATLAS v1.0 calibration note: influence must amplify decay, not offset it."""
    h = rh.compute(_components(recency=rh.recency(NOW - timedelta(days=150), NOW)))
    assert h["at_risk"] and h["score"] <= 40 and h["band"] in ("cooling", "weak", "dormant")
    assert "gone quiet" in h["at_risk_reason"]
    quiet_adviser = rh.compute(_components(recency=rh.recency(NOW - timedelta(days=150), NOW), influence=rh.influence("adviser")))
    assert not quiet_adviser["at_risk"]


def test_not_assessed_until_something_is_recorded():
    h = rh.compute({}, assessed=False)
    assert h["score"] is None and h["band_label"] == "Not assessed" and "Not assessed" in rh.explain(h)


def test_negative_outcomes_weigh_more_and_responsiveness_is_a_rate():
    assert rh.meeting_outcomes(1, 0, 1)["score"] == 40.0          # raw 50 minus a 10-point penalty
    assert rh.responsiveness(3, 0)["note"].startswith("Never responded") and rh.responsiveness(0, 0)["score"] == 50.0


def test_momentum_states_from_the_engagement_record():
    e = lambda days, outcome="positive": {"occurred_at": NOW - timedelta(days=days), "outcome": outcome}  # noqa: E731
    assert rh.momentum([], NOW)["state"] == "new"
    assert rh.momentum([e(10), e(20)], NOW)["state"] == "new"
    assert rh.momentum([e(10), e(20), e(300)], NOW)["state"] == "improving"
    assert rh.momentum([e(120), e(150)], NOW)["state"] == "declining"
    assert rh.momentum([e(200), e(300)], NOW)["state"] == "dormant"
    assert rh.momentum([e(10), e(120)], NOW)["state"] == "stable"
    assert rh.momentum([e(10, "negative"), e(20, "no_response"), e(120, "positive")], NOW)["state"] == "declining"


def test_attention_ranks_a_declining_buyer_above_a_strong_one():
    strong = rh.compute(_components())
    weak = rh.compute(_components(recency=rh.recency(NOW - timedelta(days=150), NOW)))
    a_strong = rh.attention(strong, {"state": "stable"}, 100)
    a_weak = rh.attention(weak, {"state": "declining"}, 100)
    assert a_weak > a_strong
    assert "this week" in rh.recommended_action({"full_name": "Grace Achieng"}, weak, {"state": "declining"})


def test_relevance_scores_role_fit_seniority_organisation_geography_and_evidence():
    s = cr.score(role_title="Head of Cargo", organisation="Savanna Example Air", organisation_kind="airline", countries=["KE"],
                 brief_module="airline_representation", brief_organisation="Savanna Example Air", brief_countries=["KE"],
                 brief_role_focus=None, binding="listed with this title on the leadership page", page_kind="leadership")
    assert s["score"] == 35 + 20 + 20 + 10 + 10
    weak = cr.score(role_title=None, organisation=None, organisation_kind=None, countries=[], brief_module="forwarder_sales",
                    brief_organisation=None, brief_countries=["KE"], brief_role_focus=None, binding="named in the passage", page_kind="news")
    assert weak["score"] == 0 + 0 + 0 + 2 + 3
    focus = cr.score(role_title="Head of Procurement", organisation="Blue Ridge Handling", organisation_kind=None, countries=["TZ"],
                     brief_module=None, brief_organisation=None, brief_countries=["KE"], brief_role_focus="head of procurement",
                     binding="stated in the passage", page_kind="news")
    assert next(c for c in focus["components"] if c["key"] == "role_fit")["points"] == 35
    assert next(c for c in focus["components"] if c["key"] == "geography")["points"] == 0


def test_discovery_queries_cover_the_capability_areas_target_roles():
    qs = plan.build_discovery_queries(module="outsourcing_training", organisation="Example Air", countries=["Kenya"], role_focus=None)
    texts = [q.text for q in qs]
    assert any('"training manager"' in t for t in texts) and any("appoints" in t for t in texts)
    assert all('"Example Air"' in t for t in texts)
    open_market = plan.build_discovery_queries(module="forwarder_sales", organisation=None, countries=["Kenya"], role_focus="head of sales")
    assert open_market[0].text.startswith('"head of sales"') and any("Kenya" in q.text for q in open_market)

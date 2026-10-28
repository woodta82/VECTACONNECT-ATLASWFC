"""Directive §11: prioritisation for every module; dimensions separate; provisional; no currency mixing."""
from decimal import Decimal

from app.domain import prioritisation as pr
from app.domain.scoring import assess

ALL = {"airline_representation", "account_growth", "forwarder_sales", "capacity_lanes", "service_operations", "trucking_gateways",
       "outsourcing_training", "technology_solutions", "network_development"}


def facts(**kw):
    base = dict(module="airline_representation", checks={"capability": "pass", "eligibility": "pass", "territory_conflict": "pass"},
                families=2, best_authority="official_portal", recency_days=5, has_owner=True, days_to_deadline=30, contradicted=0,
                credentials_required=False, contribution=Decimal("300000"), exposure=Decimal("0"), agreements_elsewhere=1,
                has_contact=True, has_engagement=True, duration_months=24)
    base.update(kw)
    return pr.Facts(**base)


def test_every_module_has_a_definition_and_all_are_provisional():
    d = pr.definitions()
    assert {x["module"] for x in d} == ALL
    assert all(x["provisional"] for x in d)
    for x in d:
        if x["method"] == "scored":
            assert "Not a probability" in x["note"]
            assert x["dimensions_kept_separate"] == ["attractiveness", "evidence_confidence", "readiness", "risk"]
        else:
            assert x["order"] and x["why_no_score"]


def test_scored_models_weights_sum_to_one_per_dimension():
    for m in pr.SCORED.values():
        for dim in ("attractiveness", "evidence_confidence", "readiness", "risk"):
            ws = [f.weight for f in m.factors if f.dimension == dim]
            if ws:
                assert sum(ws) == Decimal("1.00"), (m.module, dim)


def test_dimensions_are_never_combined():
    values, _ = pr.factor_values(facts())
    model = pr.SCORED["airline_representation"]
    out = assess(model, {k: v for k, v in values.items() if k in {f.code for f in model.factors}})
    assert set(out) == {"attractiveness", "evidence_confidence", "readiness", "risk"}
    assert all(a.status in ("scored", "insufficient_evidence", "blocked") for a in out.values())


def test_money_bands_only_in_their_currency():
    usd, _ = pr.factor_values(facts(value_currency="USD"))
    assert usd["contribution_band"] == 3 and usd["exposure"] == 4
    jpy, why = pr.factor_values(facts(value_currency="JPY", contribution=Decimal("1000000")))
    assert jpy["contribution_band"] is None and jpy["exposure"] is None
    assert "JPY" in why["contribution_band"] and "no conversion basis" in why["contribution_band"]


def test_unknown_contribution_is_unknown_not_low():
    v, why = pr.factor_values(facts(contribution=None, exposure=None))
    assert v["contribution_band"] is None and "unqualified" in why["contribution_band"]


def test_unknown_owner_and_deadline_are_reported():
    v, why = pr.factor_values(facts(has_owner=False, days_to_deadline=None))
    assert "no owner" in why["owner_and_time"] and "deadline unknown" in why["owner_and_time"]

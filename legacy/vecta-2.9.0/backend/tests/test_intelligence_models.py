"""ATLAS Intelligence Models — test suite.

The five models are the platform's IP. These tests protect the
*calibration decisions*, not just the arithmetic — a weight that sums to
1.0 but ranks a dormant economic buyer as "healthy" is correctly
implemented and commercially wrong.

Each model is independently testable, per the Sprint 3 requirement. No
database, no AI key, no network — the engines are pure functions.
"""
from datetime import date, timedelta

import pytest


# ═══════════════════════ EFS — Executive Focus Score ═══════════════════════

class TestExecutiveFocusScore:
    def test_weights_sum_to_one(self):
        from app.focus_score import FOCUS_WEIGHTS

        assert abs(sum(FOCUS_WEIGHTS.values()) - 1.0) < 1e-9

    def test_all_eight_inputs_present(self):
        from app.focus_score import FOCUS_WEIGHTS

        assert set(FOCUS_WEIGHTS) == {
            "strategic_alignment", "commercial_value", "win_probability", "urgency",
            "relationship_readiness", "qualification", "evidence_quality",
            "delivery_capacity",
        }

    def test_focus_differs_from_opportunity_quality(self):
        """The defining property. An excellent opportunity awaiting
        evaluation must score BELOW a moderate one with a closing window —
        otherwise EFS is a second opinion on Pursuit Priority."""
        from app.focus_score import compute_focus_score, urgency_component

        today = date.today()
        done = compute_focus_score(
            {"strategic_alignment": {"score": 95}, "win_probability": {"score": 85},
             "urgency": urgency_component(today + timedelta(days=200))},
            is_actionable=False, suppression_reason="Submitted",
        )
        live = compute_focus_score(
            {"strategic_alignment": {"score": 60},
             "urgency": urgency_component(today + timedelta(days=6))}
        )
        assert done["score"] == 0
        assert live["score"] > done["score"]

    def test_urgency_is_non_linear(self):
        from app.focus_score import urgency_component

        today = date.today()
        near = urgency_component(today + timedelta(days=5))["score"]
        mid = urgency_component(today + timedelta(days=45))["score"]
        far = urgency_component(today + timedelta(days=150))["score"]
        assert near - mid > mid - far

    def test_weak_evidence_scores_high_for_attention(self):
        """Inverted vs DCS on purpose: here weak evidence means there is
        verification work worth doing."""
        from app.focus_score import evidence_quality_component

        assert (
            evidence_quality_component(0, 0, 0)["score"]
            > evidence_quality_component(2, 2, 3, False)["score"]
        )

    def test_disqualified_scores_zero(self):
        from app.focus_score import qualification_component

        assert qualification_component("disqualified")["score"] == 0

    def test_every_score_is_explainable(self):
        from app.focus_score import compute_focus_score, explain, urgency_component

        result = compute_focus_score(
            {"urgency": urgency_component(date.today() + timedelta(days=8))}
        )
        assert result["contributions"]
        assert all("note" in c for c in result["contributions"])
        assert len(explain(result).split()) <= 20


# ═══════════════════ RCI — Relationship Coverage Index ═══════════════════

class TestRelationshipCoverageIndex:
    def test_role_weights_sum_to_one(self):
        from app.coverage_index import COVERAGE_ROLES

        assert abs(sum(r["weight"] for r in COVERAGE_ROLES) - 1.0) < 1e-9

    def test_distinguishes_three_gap_types(self):
        """The design decision that makes RCI more than a percentage.
        Unknown, unengaged and deteriorating need different actions."""
        from app.coverage_index import compute_coverage

        unknown = compute_coverage([{"role": "economic_buyer", "state": "unknown"}])
        identified = compute_coverage(
            [{"role": "economic_buyer", "state": "identified", "stakeholder_name": "X"}]
        )
        declining = compute_coverage(
            [{"role": "economic_buyer", "state": "engaged", "health_score": 30,
              "momentum_state": "declining", "stakeholder_name": "X"}]
        )

        assert unknown["gaps"][0]["gap_type"] == "intelligence"
        assert identified["gaps"][0]["gap_type"] == "execution"
        assert declining["gaps"][0]["gap_type"] == "relationship"

    def test_gap_type_drives_a_different_verb(self):
        from app.coverage_index import compute_coverage

        actions = []
        for state, extra in [
            ("unknown", {}),
            ("identified", {"stakeholder_name": "A Person"}),
            ("engaged", {"stakeholder_name": "A Person", "health_score": 30,
                         "momentum_state": "declining"}),
        ]:
            result = compute_coverage([{"role": "economic_buyer", "state": state, **extra}])
            actions.append(result["gaps"][0]["recommended_action"])

        assert actions[0].startswith("Identify")
        assert actions[1].startswith("Contact")
        assert actions[2].startswith("Repair")

    def test_unmapped_critical_role_caps_the_score(self):
        """A weighted average would flatter a pursuit with no route to a
        decision."""
        from app.coverage_index import compute_coverage

        result = compute_coverage([
            {"role": "economic_buyer", "state": "unknown"},
            {"role": "technical_evaluator", "state": "advocating", "health_score": 95},
            {"role": "operational_champion", "state": "advocating", "health_score": 95},
            {"role": "political_sponsor", "state": "advocating", "health_score": 95},
        ])
        assert result["score"] <= 55
        assert result["cap_reason"] is not None
        assert "Executive sponsor" in " ".join(result["missing_critical"])

    def test_biggest_lever_weighs_headroom_not_just_severity(self):
        from app.coverage_index import compute_coverage

        result = compute_coverage([
            {"role": "economic_buyer", "state": "identified", "stakeholder_name": "Big"},
            {"role": "political_sponsor", "state": "unknown"},
        ])
        # Economic buyer carries 0.26 weight vs 0.10 — despite the sponsor
        # scoring lower, the buyer is the better lever.
        assert result["biggest_lever"]["role"] == "economic_buyer"

    def test_pursuit_recommendation_accounts_for_time(self):
        from app.coverage_index import compute_coverage, pursuit_recommendation

        coverage = compute_coverage([{"role": "economic_buyer", "state": "unknown"}])
        urgent = pursuit_recommendation(coverage, days_to_deadline=10)
        distant = pursuit_recommendation(coverage, days_to_deadline=120)

        assert urgent["posture"] == "high_risk_pursuit"
        assert distant["posture"] == "close_coverage_first"

    def test_explanation_names_the_gap_type(self):
        from app.coverage_index import compute_coverage

        result = compute_coverage([
            {"role": "economic_buyer", "state": "identified", "stakeholder_name": "X"},
            {"role": "budget_holder", "state": "unknown"},
        ])
        assert "unidentified" in result["explanation"] or "never contacted" in result["explanation"]


# ═══════════════════ CRI — Commercial Readiness Index ═══════════════════

class TestCommercialReadinessIndex:
    def test_weights_sum_to_one(self):
        from app.readiness_index import CRI_DIMENSIONS

        assert abs(sum(d["weight"] for d in CRI_DIMENSIONS.values()) - 1.0) < 1e-9

    def test_blocking_dimension_caps_the_band(self):
        """An earlier version reported 'Mostly ready. Blocked by...' — a
        contradiction that would let an executive commit resources to a
        pursuit that cannot proceed."""
        from app.readiness_index import compute_readiness

        result = compute_readiness({
            "qualification": {"score": 95},
            "relationship_maturity": {"score": 20},
            "evidence_quality": {"score": 95},
            "delivery_capability": {"score": 95},
            "resource_availability": {"score": 95},
            "strategic_alignment": {"score": 95},
        })
        assert result["blocking_dimensions"]
        assert result["band"] not in ("ready", "mostly_ready")
        assert result["cap_reason"]

    def test_unblocked_readiness_is_not_capped(self):
        from app.readiness_index import CRI_DIMENSIONS, compute_readiness

        result = compute_readiness({k: {"score": 85} for k in CRI_DIMENSIONS})
        assert result["cap_reason"] is None
        assert result["band"] == "ready"

    def test_names_weakest_dimensions(self):
        from app.readiness_index import compute_readiness

        result = compute_readiness({
            "qualification": {"score": 90},
            "relationship_maturity": {"score": 45, "note": "Buyer unmapped"},
            "evidence_quality": {"score": 90},
            "delivery_capability": {"score": 88},
            "resource_availability": {"score": 85},
            "strategic_alignment": {"score": 92},
        })
        assert "Relationship maturity" in result["weakest_dimensions"]
        assert result["biggest_lever"]["dimension"] == "Relationship maturity"

    def test_every_dimension_explains_why_it_matters(self):
        from app.readiness_index import CRI_DIMENSIONS

        assert all(d.get("why") for d in CRI_DIMENSIONS.values())


# ═══════════════════ RMI — Relationship Momentum Index ═══════════════════

class TestRelationshipMomentumIndex:
    def test_health_weights_sum_to_one(self):
        from app.relationship_health import HEALTH_WEIGHTS

        assert abs(sum(HEALTH_WEIGHTS.values()) - 1.0) < 1e-9

    def test_trajectory_distinguishes_what_a_delta_cannot(self):
        """80→70→60 and 50→70→60 both show 'down 10' from the previous
        reading but are opposite stories."""
        from app.relationship_health import compute_momentum

        decline = compute_momentum([80, 70, 60], influence_score=80)
        correction = compute_momentum([50, 70, 60], influence_score=80)
        assert decline["slope"] < 0 < correction["slope"]
        assert decline["state"] == "declining"

    def test_leading_indicators_move_before_the_score(self):
        """Health is lagging. By the time it falls the relationship has
        already cooled."""
        from app.relationship_health import compute_momentum

        flat = compute_momentum([65, 65, 65], influence_score=70)
        flat_but_quiet = compute_momentum(
            [65, 65, 65], influence_score=70,
            days_since_engagement=80, overdue_followups=2,
        )
        assert flat["state"] == "stable"
        assert flat_but_quiet["state"] in ("declining", "critical")

    def test_influence_amplifies_decay_rather_than_offsetting_it(self):
        """The calibration bug found during Sprint 2: an economic buyer
        untouched for 150 days scored 'Healthy' because influence offset
        recency."""
        from app.relationship_health import (
            compute_health, frequency_component, influence_component,
            meeting_outcome_component, opportunity_alignment_component,
            recency_component, responsiveness_component, strategic_value_component,
        )

        today = date.today()

        def build(stakeholder_type):
            return {
                "recency": recency_component(today - timedelta(days=150)),
                "frequency": frequency_component(6),
                "responsiveness": responsiveness_component(5, 4),
                "meeting_outcomes": meeting_outcome_component(2, 1, 0),
                "influence": influence_component(stakeholder_type),
                "opportunity_alignment": opportunity_alignment_component(1, 70),
                "strategic_value": strategic_value_component(True, 1, "government"),
            }

        buyer = compute_health(build("economic_buyer"))
        consultant = compute_health(build("consultant"))

        assert buyer["at_risk"] is True
        assert consultant["at_risk"] is False
        assert buyer["score"] < consultant["score"]

    def test_critical_reserved_for_relationships_that_matter(self):
        from app.relationship_health import compute_momentum

        junior = compute_momentum([60, 50, 40], at_risk=True, influence_score=30)
        senior = compute_momentum([60, 50, 40], at_risk=True, influence_score=90)
        assert junior["state"] != "critical"
        assert senior["state"] == "critical"

    def test_negative_meetings_weighted_harder_than_positive(self):
        from app.relationship_health import meeting_outcome_component

        good = meeting_outcome_component(3, 0, 0)["score"]
        mixed = meeting_outcome_component(2, 0, 1)["score"]
        assert mixed < good - 25

    def test_explanation_never_contradicts_the_label(self):
        """'Declining — health broadly flat' was a real bug."""
        from app.relationship_health import compute_momentum

        result = compute_momentum(
            [65, 65, 65], influence_score=70,
            days_since_engagement=80, overdue_followups=2,
        )
        assert "broadly flat" not in result["explanation"]

    def test_attention_priority_is_not_health(self):
        from app.relationship_health import combined_priority, compute_momentum

        strong = combined_priority(85, compute_momentum([70, 78, 85], influence_score=90), 90)
        weak = combined_priority(35, compute_momentum([55, 45, 35], influence_score=90), 90)
        assert weak > strong


# ═══════════════════ DCS — Decision Confidence Score ═══════════════════

class TestDecisionConfidenceScore:
    def test_weights_sum_to_one(self):
        from app.readiness_index import DCS_FACTORS

        assert abs(sum(f["weight"] for f in DCS_FACTORS.values()) - 1.0) < 1e-9

    def test_refuses_to_advise_below_the_floor(self):
        """The property that makes DCS worth having: ATLAS says it does
        not know enough rather than advising with false authority."""
        from app.readiness_index import (
            assumption_load_factor, compute_confidence, data_completeness_factor,
            evidence_quality_factor, historical_accuracy_factor, model_certainty_factor,
        )

        result = compute_confidence({
            "evidence_quality": evidence_quality_factor(0, 0, 1),
            "data_completeness": data_completeness_factor(30, 3, 16, 0),
            "historical_accuracy": historical_accuracy_factor(None, 0),
            "assumption_load": assumption_load_factor(5, 0, 3),
            "model_certainty": model_certainty_factor(1, 5, 2),
        })
        assert result["should_advise"] is False
        assert "does not have enough" in result["caveat"]

    def test_no_history_returns_neutral_not_flattering(self):
        """Claiming confidence because there is no contrary evidence yet
        is the failure this model exists to prevent."""
        from app.readiness_index import historical_accuracy_factor

        result = historical_accuracy_factor(None, 0)
        assert result["score"] == 50
        assert "unproven" in result["note"]

    def test_small_sample_does_not_raise_confidence(self):
        from app.readiness_index import historical_accuracy_factor

        assert historical_accuracy_factor(1.0, 3)["score"] == 50

    def test_sufficient_sample_is_used(self):
        from app.readiness_index import historical_accuracy_factor

        result = historical_accuracy_factor(0.8, 25)
        assert result["score"] == 80

    def test_invalidated_assumption_weighted_hardest(self):
        """Not a risk — a known error still being relied upon."""
        from app.readiness_index import assumption_load_factor

        assert (
            assumption_load_factor(1, invalidated=1)["score"]
            < assumption_load_factor(5)["score"]
        )

    def test_evidence_quality_inverted_relative_to_focus(self):
        """Same input, opposite meaning. EFS asks 'is there work to do';
        DCS asks 'should you believe this'. Conflating them is a real bug."""
        from app.focus_score import evidence_quality_component as efs_evidence
        from app.readiness_index import evidence_quality_factor as dcs_evidence

        assert efs_evidence(0, 0, 0)["score"] > efs_evidence(2, 2, 3, False)["score"]
        assert dcs_evidence(0, 0, 0)["score"] < dcs_evidence(2, 2, 3)["score"]

    def test_names_what_would_raise_confidence(self):
        from app.readiness_index import (
            assumption_load_factor, compute_confidence, data_completeness_factor,
            evidence_quality_factor, historical_accuracy_factor, model_certainty_factor,
        )

        result = compute_confidence({
            "evidence_quality": evidence_quality_factor(0, 0, 2),
            "data_completeness": data_completeness_factor(50, 8, 16, 1),
            "historical_accuracy": historical_accuracy_factor(None, 0),
            "assumption_load": assumption_load_factor(2),
            "model_certainty": model_certainty_factor(3, 5),
        })
        assert result["what_would_raise_confidence"]
        assert all(item["action"] for item in result["what_would_raise_confidence"])


# ═══════════════════ Intelligence Pipeline ═══════════════════

class TestIntelligencePipeline:
    def test_signed_document_outweighs_many_ai_observations(self):
        """Volume of speculation must not outweigh one hard source."""
        from app.intelligence_pipeline import weigh_evidence

        signed = weigh_evidence([{"kind": "signed_document", "is_verified": True}])
        guesses = weigh_evidence([{"kind": "ai_observation"} for _ in range(6)])
        assert signed["total_weight"] > guesses["total_weight"]

    def test_unverified_high_tier_evidence_is_downgraded(self):
        """A Tier 1 URL nobody opened is a claim about a source, not a
        source."""
        from app.intelligence_pipeline import classify_evidence

        assert (
            classify_evidence("tier_1_source", is_verified=False)["weight"]
            < classify_evidence("tier_1_source", is_verified=True)["weight"]
        )

    def test_phase2_tiers_map_into_the_pipeline(self):
        from app.intelligence_pipeline import weigh_evidence

        result = weigh_evidence([{"source_tier": "tier_1", "is_verified": True}])
        assert result["items"][0]["tier"] == "high"

    def test_priority_is_impact_over_effort(self):
        """Ranking on impact alone systematically buries quick wins."""
        from app.intelligence_pipeline import build_recommendation, weigh_evidence

        evidence = weigh_evidence([{"kind": "tier_1_source", "is_verified": True}])
        confidence = {"score": 80, "band_label": "High", "should_advise": True}

        quick = build_recommendation(
            action="Call", because="Window closing", impact="moderate",
            effort="trivial", evidence=evidence, confidence=confidence,
        )
        slow = build_recommendation(
            action="Build consortium", because="Entity required", impact="high",
            effort="major", evidence=evidence, confidence=confidence,
        )
        assert quick["priority"] > slow["priority"]

    def test_thin_evidence_blocks_the_recommendation(self):
        from app.intelligence_pipeline import build_recommendation, weigh_evidence

        evidence = weigh_evidence([{"kind": "assumption"}])
        result = build_recommendation(
            action="Pursue", because="Seems good", impact="high", effort="low",
            evidence=evidence,
            confidence={"score": 70, "band_label": "Moderate", "should_advise": True},
        )
        assert result["should_advise"] is False
        assert "too thin" in result["caveat"]

    def test_withheld_recommendations_rank_last_but_are_not_hidden(self):
        """Suppressing them entirely would hide a real situation."""
        from app.intelligence_pipeline import build_recommendation, rank_recommendations, weigh_evidence

        strong = weigh_evidence([{"kind": "signed_document", "is_verified": True}])
        weak = weigh_evidence([{"kind": "assumption"}])
        confidence = {"score": 80, "band_label": "High", "should_advise": True}

        good = build_recommendation(action="Act", because="Evidenced", impact="high",
                                    effort="low", evidence=strong, confidence=confidence)
        withheld = build_recommendation(action="Guess", because="Hunch", impact="transformational",
                                        effort="trivial", evidence=weak, confidence=confidence)
        ranked = rank_recommendations([withheld, good])
        assert ranked[0]["action"] == "Act"
        assert len(ranked) == 2

    def test_every_recommendation_states_why(self):
        """`because` is required, not optional. A recommendation without a
        reason is an instruction, which cannot be evaluated."""
        import inspect

        from app.intelligence_pipeline import build_recommendation

        signature = inspect.signature(build_recommendation)
        assert signature.parameters["because"].default is inspect.Parameter.empty

    def test_every_recommendation_cites_models(self):
        from app.intelligence_pipeline import build_recommendation, weigh_evidence

        result = build_recommendation(
            action="Act", because="Reason", impact="high", effort="low",
            evidence=weigh_evidence([{"kind": "tier_1_source", "is_verified": True}]),
            confidence={"score": 80, "band_label": "High", "should_advise": True},
            models=["EFS", "DCS"],
        )
        codes = [m["code"] for m in result["intelligence_models"]]
        assert codes == ["EFS", "DCS"]
        assert all(m["question"] for m in result["intelligence_models"])


# ═══════════════════ framework-level guarantees ═══════════════════

class TestIntelligenceFramework:
    def test_all_five_models_registered(self):
        from app.readiness_index import INTELLIGENCE_MODELS

        assert set(INTELLIGENCE_MODELS) == {"EFS", "RCI", "CRI", "RMI", "DCS"}

    def test_every_model_states_the_question_it_answers(self):
        from app.readiness_index import INTELLIGENCE_MODELS

        assert all(m["question"].endswith("?") for m in INTELLIGENCE_MODELS.values())

    def test_every_model_is_versioned(self):
        from app.readiness_index import INTELLIGENCE_MODELS

        assert all(m["version"] for m in INTELLIGENCE_MODELS.values())

    def test_no_model_is_a_black_box(self):
        """Every model must expose its per-factor contributions."""
        from app.coverage_index import compute_coverage
        from app.focus_score import compute_focus_score
        from app.readiness_index import compute_confidence, compute_readiness
        from app.relationship_health import compute_health

        assert compute_focus_score({})["contributions"]
        assert compute_coverage([{"role": "economic_buyer", "state": "unknown"}])["roles"]
        assert compute_readiness({})["dimensions"]
        assert compute_confidence({})["factors"]
        assert compute_health({})["contributions"]

    def test_every_advisor_response_cites_models(self):
        import ast
        import inspect

        from app.services import advisor_service

        source = inspect.getsource(advisor_service)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_response":
                kwargs = {k.arg for k in node.keywords}
                assert "models" in kwargs, "every advisor response must cite its models"


# ═══════════════════ Scenario Engine (Sprint 4) ═══════════════════

class TestScenarioEngine:
    """The guarding principle: scenario analysis is theatre if one option
    always wins. These tests assert genuine differentiation."""

    BASE = dict(
        contract_value=4_000_000, win_probability=55, coverage_score=55,
        readiness_score=60, days_to_deadline=90, missing_critical_roles=0,
        capacity_strained=False,
    )

    def test_all_four_scenarios_always_modelled(self):
        from app.scenario_engine import SCENARIOS, model_scenarios

        result = model_scenarios(**self.BASE)
        assert {s["key"] for s in result["scenarios"]} == set(SCENARIOS)

    def test_strong_position_recommends_pursuit(self):
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "coverage_score": 85,
                                    "readiness_score": 85, "win_probability": 70})
        assert result["recommended"] == "pursue_now"

    def test_thin_coverage_with_time_recommends_strengthening(self):
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "coverage_score": 30,
                                    "missing_critical_roles": 2, "days_to_deadline": 150})
        assert result["recommended"] == "strengthen_first"

    def test_unwinnable_pursuit_recommends_withdrawal(self):
        """Withdrawal must be reachable. Scoring it permanently negative is
        how organisations end up bidding everything badly."""
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "readiness_score": 30,
                                    "coverage_score": 25, "days_to_deadline": 18,
                                    "missing_critical_roles": 2, "capacity_strained": True})
        assert result["recommended"] == "withdraw"

    def test_below_viable_value_recommends_withdrawal(self):
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "contract_value": 800_000,
                                    "min_viable_value": 2_000_000})
        assert result["recommended"] == "withdraw"

    def test_strengthening_is_infeasible_when_time_is_short(self):
        """A recommendation that cannot physically be executed is worse
        than no recommendation. This was a real bug: the deadline reduced
        the scenario's expected value but not its impact score, so it kept
        winning with 18 days left."""
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "days_to_deadline": 20,
                                    "coverage_score": 25})
        strengthen = next(s for s in result["scenarios"] if s["key"] == "strengthen_first")
        assert strengthen["commercial_impact"] < 0
        assert any("cannot land in time" in strengthen["rationale"] for _ in [1])

    def test_engine_differentiates_across_situations(self):
        """The meta-test. If every situation produces the same answer, the
        model is decorating a foregone conclusion."""
        from app.scenario_engine import model_scenarios

        situations = [
            {**self.BASE, "coverage_score": 85, "readiness_score": 85},
            {**self.BASE, "coverage_score": 30, "missing_critical_roles": 2,
             "days_to_deadline": 150},
            {**self.BASE, "readiness_score": 30, "days_to_deadline": 18,
             "missing_critical_roles": 2, "capacity_strained": True},
        ]
        winners = {model_scenarios(**s)["recommended"] for s in situations}
        assert len(winners) >= 3

    def test_close_calls_are_declared(self):
        """A narrow margin is information — it tells the executive their
        judgement matters more than usual."""
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "days_to_deadline": 25,
                                    "coverage_score": 35, "contract_value": 6_000_000})
        if result["is_close_call"]:
            assert "close call" in result["explanation"].lower()

    def test_unknown_value_is_not_zero(self):
        """An unquantified opportunity is not a worthless one."""
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "contract_value": None,
                                    "win_probability": None})
        pursue = next(s for s in result["scenarios"] if s["key"] == "pursue_now")
        assert pursue["expected_value"] is None

    def test_every_scenario_names_its_opportunity_cost(self):
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**self.BASE)
        cost = result["opportunity_cost"]
        assert cost["foregone_label"]
        assert cost["what_is_given_up"]

    def test_delay_carries_a_cost_when_the_window_is_closing(self):
        """Delay is never free — the window closes whether or not VECTA acts."""
        from app.scenario_engine import model_scenarios

        far = model_scenarios(**{**self.BASE, "days_to_deadline": 200})
        near = model_scenarios(**{**self.BASE, "days_to_deadline": 20})
        delay_far = next(s for s in far["scenarios"] if s["key"] == "delay_engagement")
        delay_near = next(s for s in near["scenarios"] if s["key"] == "delay_engagement")
        assert delay_near["commercial_impact"] < delay_far["commercial_impact"]

    def test_withdraw_confidence_is_always_high(self):
        """Doing nothing has predictable consequences."""
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**{**self.BASE, "coverage_score": 10, "readiness_score": 10})
        withdraw = next(s for s in result["scenarios"] if s["key"] == "withdraw")
        assert withdraw["confidence"] == "high"

    def test_every_scenario_is_explainable(self):
        from app.scenario_engine import model_scenarios

        result = model_scenarios(**self.BASE)
        for scenario in result["scenarios"]:
            assert scenario["rationale"]
            assert scenario["commercial_impact_label"]
            assert scenario["confidence"] in ("high", "medium", "low")

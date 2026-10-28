"""Phase 3.1 tests — Executive Intelligence.

Covers the six modules built for 3.1. The tests that matter most:

- `test_focus_inverts_priority_for_non_actionable` — the property that
  makes Executive Focus a different score rather than a second opinion.
- `test_risk_not_established_never_shows_a_number` — the suppression that
  must survive every layer.
- `test_learning_loop_refuses_to_adjust_on_small_sample` — the guardrail
  against confident noise.

Offline, no AI key, no network.
"""
from datetime import date, datetime, timedelta

import pytest

from app.database import Base, SessionLocal, engine
from app.models import Contact, Opportunity, Stage
from app.regions import Region, Vertical
from app.timeutils import utcnow


@pytest.fixture(autouse=True)
def fresh_db():
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_opportunity(db, *, title="Test Opportunity", deadline=None,
                     classification="confirmed_opportunity", stage=None,
                     scores=None, qualification="qualified", evidence=True):
    from app.scoring_v2 import DIMENSIONS
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    opp = Opportunity(
        title=title,
        summary=f"{title} — summary for testing.",
        vertical=Vertical.PATHWAYS,
        region=Region.MENA,
        classification=classification,
        primary_vertical="pathways",
        deadline=deadline,
        stage=stage,
    )
    db.add(opp)
    db.commit()

    if evidence:
        svc.persist_evidence(db, opp.id, [{
            "url": "https://gov.example/tender/1",
            "source_tier": "tier_1",
            "claims_supported": ["opportunity_existence", "live_status"],
            "publication_date": "2026-06-01",
            "url_validation_status": "valid",
            "is_official_source": True,
        }])

    factor_scores = scores or {
        d: {f["key"]: 80 for f in info["factors"]} for d, info in DIMENSIONS.items()
    }
    if scores is None:
        factor_scores["risk"] = {f["key"]: 30 for f in DIMENSIONS["risk"]["factors"]}

    computed = svc.persist_scores(db, opp.id, factor_scores)
    if qualification:
        svc.persist_qualification(
            db, opp.id,
            {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS},
            classification=classification, deadline=deadline,
        )
    svc.persist_pursuit_priority(db, opp.id, computed, qualification_state=qualification or "not_assessed")
    db.commit()
    return opp


# ============================================================ focus score

def test_focus_weights_sum_to_one():
    from app.focus_score import FOCUS_WEIGHTS

    assert abs(sum(FOCUS_WEIGHTS.values()) - 1.0) < 1e-9


def test_all_eight_inputs_present():
    from app.focus_score import FOCUS_WEIGHTS

    required = {
        "strategic_alignment", "commercial_value", "win_probability", "urgency",
        "relationship_readiness", "qualification", "evidence_quality", "delivery_capacity",
    }
    assert set(FOCUS_WEIGHTS) == required


def test_urgency_is_non_linear():
    """90 vs 60 days barely affects today's decision; 10 vs 5 is decisive.
    A linear scale would spread attention evenly across a quarter."""
    from app.focus_score import urgency_component

    today = date.today()
    near = urgency_component(today + timedelta(days=5))["score"]
    mid = urgency_component(today + timedelta(days=45))["score"]
    far = urgency_component(today + timedelta(days=120))["score"]

    assert near > mid > far
    assert near - mid > mid - far   # steeper as the deadline closes


def test_weak_evidence_scores_high_for_attention():
    """Counter-intuitive but correct: weak evidence means verification is
    an action worth taking. Strong evidence means nothing left to do."""
    from app.focus_score import evidence_quality_component

    none = evidence_quality_component(0, 0, 0, False)["score"]
    strong = evidence_quality_component(2, 2, 3, False)["score"]
    assert none > strong


def test_blocked_qualification_scores_higher_than_qualified():
    from app.focus_score import qualification_component

    blocked = qualification_component("verification_required", unanswered_mandatory=3)["score"]
    done = qualification_component("qualified")["score"]
    disqualified = qualification_component("disqualified")["score"]

    assert blocked > done
    assert disqualified == 0    # attention cannot change it


def test_focus_inverts_priority_for_non_actionable():
    """THE defining property. An excellent opportunity awaiting evaluation
    must rank BELOW a moderate one with a closing window — otherwise Focus
    is just a second opinion on Pursuit Priority."""
    from app.focus_score import (
        commercial_value_component,
        compute_focus_score,
        evidence_quality_component,
        qualification_component,
        relationship_readiness_component,
        urgency_component,
        delivery_capacity_component,
    )

    today = date.today()
    excellent_but_done = compute_focus_score(
        {
            "strategic_alignment": {"score": 92},
            "commercial_value": commercial_value_component(8_000_000, 2_000_000, 5_000_000),
            "win_probability": {"score": 78},
            "urgency": urgency_component(today + timedelta(days=120)),
            "relationship_readiness": relationship_readiness_component(True, True, 80, False, 5),
            "qualification": qualification_component("qualified"),
            "evidence_quality": evidence_quality_component(2, 2, 3, False),
            "delivery_capacity": delivery_capacity_component(False, False, 0),
        },
        is_actionable=False,
        suppression_reason="Submitted — awaiting evaluation",
    )
    moderate_but_urgent = compute_focus_score(
        {
            "strategic_alignment": {"score": 68},
            "commercial_value": commercial_value_component(3_000_000, 2_000_000, 5_000_000),
            "win_probability": {"score": 55},
            "urgency": urgency_component(today + timedelta(days=9)),
            "relationship_readiness": relationship_readiness_component(False, False, 30, True, 45),
            "qualification": qualification_component("verification_required", 3),
            "evidence_quality": evidence_quality_component(0, 0, 2, True),
            "delivery_capacity": delivery_capacity_component(True, True, 2),
        }
    )

    assert excellent_but_done["score"] == 0
    assert moderate_but_urgent["score"] > 60
    assert moderate_but_urgent["score"] > excellent_but_done["score"]


def test_explanation_is_short():
    """A six-clause explanation is accurate but not executive."""
    from app.focus_score import (
        compute_focus_score, explain, relationship_readiness_component, urgency_component,
    )

    result = compute_focus_score({
        "urgency": urgency_component(date.today() + timedelta(days=9)),
        "relationship_readiness": relationship_readiness_component(False, False, 30, True, 45),
    })
    text = explain(result)
    assert len(text.split()) <= 20
    assert text.count(";") <= 1


def test_focus_bands_cover_full_range():
    from app.focus_score import band_for

    for score, expected in [(90, "act_now"), (70, "this_week"), (50, "this_month"),
                            (30, "monitor"), (5, "no_action")]:
        assert band_for(score)["key"] == expected


# ======================================================== change detection

def test_score_change_below_threshold_is_not_news(db):
    from app.services import change_detector

    opp = make_opportunity(db)
    change_detector.record_score_change(db, opp.id, "win_probability", 70, 100)
    db.commit()
    event = change_detector.record_score_change(db, opp.id, "win_probability", 74, 100)
    db.commit()

    assert event is None, "a 4-point move should not reach the briefing"


def test_material_score_change_is_recorded(db):
    from app.models_memory import ScoreHistory
    from app.services import change_detector

    opp = make_opportunity(db)
    change_detector.record_score_change(db, opp.id, "win_probability", 70, 100)
    db.commit()
    event = change_detector.record_score_change(db, opp.id, "win_probability", 52, 100)
    db.commit()

    assert event is not None
    assert event.delta == -18
    assert "fell" in event.summary
    assert db.query(ScoreHistory).filter_by(opportunity_id=opp.id).count() == 2


def test_history_recorded_even_when_immaterial(db):
    """The delta must stay reconstructable even when it did not warrant
    executive attention."""
    from app.models_memory import ScoreHistory
    from app.services import change_detector

    opp = make_opportunity(db)
    change_detector.record_score_change(db, opp.id, "risk", 40, 100)
    change_detector.record_score_change(db, opp.id, "risk", 42, 100)
    db.commit()

    assert db.query(ScoreHistory).filter_by(opportunity_id=opp.id, dimension="risk").count() == 2


def test_deadline_alert_fires_at_thresholds(db):
    from app.services import change_detector

    today = date.today()
    make_opportunity(db, title="Closing soon", deadline=today + timedelta(days=7))
    make_opportunity(db, title="Not yet", deadline=today + timedelta(days=45))

    events = change_detector.detect_time_based_changes(db)
    db.commit()

    summaries = " ".join(e.summary for e in events)
    assert "Closing soon" in summaries
    assert "Not yet" not in summaries


def test_time_based_events_deduplicate(db):
    """Opening the briefing three times before lunch must not produce three
    identical entries."""
    from app.services import change_detector

    make_opportunity(db, title="Closing soon", deadline=date.today() + timedelta(days=7))

    first = change_detector.detect_time_based_changes(db)
    db.commit()
    second = change_detector.detect_time_based_changes(db)
    db.commit()

    assert len(first) >= 1
    assert len(second) == 0


def test_stale_detection_catches_the_quiet_killer(db):
    """Opportunities rarely fail loudly — they lapse. Nothing else notices."""
    from app.services import change_detector

    opp = make_opportunity(db, title="Forgotten opportunity")
    opp.updated_at = datetime.utcnow() - timedelta(days=20)
    db.commit()

    events = change_detector.detect_time_based_changes(db)
    db.commit()

    stale = [e for e in events if e.event_type == "went_stale"]
    assert stale, "a qualified opportunity untouched for 20 days must surface"
    assert "Forgotten opportunity" in stale[0].summary


# ============================================================ focus service

def test_focus_persisted_and_sorted(db):
    from app.models_memory import ExecutiveFocus
    from app.services import focus_service

    make_opportunity(db, title="Urgent", deadline=date.today() + timedelta(days=5))
    make_opportunity(db, title="Distant", deadline=date.today() + timedelta(days=200))
    db.commit()

    result = focus_service.recompute_all(db)
    db.commit()

    assert result["computed"] == 2
    top = focus_service.top_focus(db, limit=2)
    assert top[0][0].title == "Urgent", "closer deadline must rank higher"
    assert db.query(ExecutiveFocus).count() == 2


def test_non_actionable_excluded_from_priorities(db):
    """An opportunity awaiting evaluation must not occupy a slot in a list
    of five."""
    from app.services import focus_service

    make_opportunity(db, title="Live", deadline=date.today() + timedelta(days=10))
    make_opportunity(db, title="Submitted", deadline=date.today() + timedelta(days=10),
                     stage=Stage.PROPOSAL)
    submitted = db.query(Opportunity).filter_by(title="Submitted").first()
    submitted.stage = Stage.WON      # terminal
    db.commit()

    focus_service.recompute_all(db)
    db.commit()

    titles = [o.title for o, _ in focus_service.top_focus(db, limit=5)]
    assert "Live" in titles
    assert "Submitted" not in titles


def test_expired_deadline_suppresses_focus(db):
    from app.models_memory import ExecutiveFocus
    from app.services import focus_service

    opp = make_opportunity(db, title="Expired", deadline=date.today() - timedelta(days=1))
    focus_service.recompute_all(db)
    db.commit()

    focus = db.query(ExecutiveFocus).filter_by(opportunity_id=opp.id).first()
    assert focus.is_actionable is False
    assert focus.score == 0
    assert "Deadline passed" in focus.suppression_reason


# =============================================================== briefing

def test_briefing_makes_no_ai_calls(db):
    from app.services import briefing_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    briefing = briefing_service.build_briefing(db)
    assert briefing["ai_calls_used"] == 0


def test_briefing_has_all_seven_sections(db):
    from app.services import briefing_service

    briefing = briefing_service.build_briefing(db)
    expected = [
        "1_executive_summary", "2_todays_priorities", "3_what_changed",
        "4_relationship_watchlist", "5_market_intelligence",
        "6_executive_risks", "7_advisor",
    ]
    assert list(briefing["sections"].keys()) == expected


def test_decision_card_has_all_thirteen_fields(db):
    from app.services import briefing_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    cards = briefing_service.todays_priorities(db, limit=1)
    assert cards
    for field in [
        "recommended_decision", "why_this_matters", "confidence", "strategic_alignment",
        "commercial_value", "win_probability", "risk", "focus_score",
        "opportunity_cost_of_waiting", "required_relationships",
        "recommended_next_action", "target_date", "supporting_evidence",
    ]:
        assert field in cards[0], f"card missing {field}"


def test_recommendation_appears_before_metrics(db):
    """Field order is the enforcement — the frontend renders in sequence."""
    from app.services import briefing_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    card = briefing_service.todays_priorities(db, limit=1)[0]
    keys = list(card.keys())
    assert keys.index("recommended_decision") < keys.index("strategic_alignment")
    assert keys.index("why_this_matters") < keys.index("win_probability")


def test_card_always_has_owner_target_date_and_cost_of_waiting(db):
    """A recommendation with no date is an observation."""
    from app.services import briefing_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    card = briefing_service.todays_priorities(db, limit=1)[0]
    assert card["target_date"] is not None
    assert card["opportunity_cost_of_waiting"]["summary"]
    assert card["recommended_next_action"]


def test_risk_not_established_never_shows_a_number(db):
    """The suppression must survive every layer to the card."""
    from app.services import briefing_service, focus_service, opportunity_service as svc

    opp = make_opportunity(db, deadline=date.today() + timedelta(days=10),
                           scores={"risk": {"financial_exposure": 10}})
    computed = svc.persist_scores(db, opp.id, {"risk": {"financial_exposure": 10}})
    db.commit()
    focus_service.recompute_all(db)
    db.commit()

    card = briefing_service.todays_priorities(db, limit=1)[0]
    assert card["risk"]["score"] is None
    assert card["risk"]["label"] == "Risk not established"


def test_relationship_position_is_labelled_inferred(db):
    """An unlabelled inference presented beside evidence-backed scores is
    the failure this platform exists to prevent."""
    from app.services import briefing_service

    opp = make_opportunity(db)
    db.add(Contact(name="A Director", role="Technical Director",
                   opportunity_id=opp.id, relevance_score=80))
    db.commit()

    status = briefing_service._relationship_status(db, opp.id)
    assert status["is_inferred"] is True
    assert "not verified" in status["basis"]
    assert status["level"] != "strong", "strong must be unreachable by inference"


def test_briefing_states_when_nothing_needs_attention(db):
    """Step 7 of the workflow is 'leave the platform'."""
    from app.services import briefing_service

    briefing = briefing_service.build_briefing(db)
    summary = briefing["sections"]["1_executive_summary"]
    assert summary["is_complete"] is True
    assert "up to date" in summary["completion_message"].lower()


def test_score_reconciliation_when_focus_and_priority_diverge(db):
    from app.services import briefing_service, focus_service

    opp = make_opportunity(db, title="High value, nothing to do",
                           deadline=date.today() + timedelta(days=300))
    focus_service.recompute_all(db)
    db.commit()

    cards = briefing_service.todays_priorities(db, limit=5)
    if cards:
        # Reconciliation is present as a field whether or not it fires.
        assert "score_reconciliation" in cards[0]


# ================================================================ advisor

def test_advisor_response_has_six_sections_in_order(db):
    from app.services import advisor_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    response = advisor_service.ask(db, "focus_today")
    assert list(response["sections"].keys()) == [
        "1_recommendation", "2_key_reasons", "3_supporting_evidence",
        "4_risks", "5_assumptions", "6_suggested_actions",
    ]


def test_advisor_makes_no_ai_calls(db):
    from app.services import advisor_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    assert advisor_service.ask(db, "focus_today")["ai_calls_used"] == 0


def test_advisor_sections_are_word_capped(db):
    """Brevity enforced structurally, not requested in a prompt."""
    from app.services import advisor_service, focus_service
    from app.vocabulary import ADVISOR_SECTION_WORD_LIMIT

    make_opportunity(db, deadline=date.today() + timedelta(days=5))
    focus_service.recompute_all(db)
    db.commit()

    response = advisor_service.ask(db, "focus_today")
    for section in response["sections"].values():
        claims = section if isinstance(section, list) else [section]
        for claim in claims:
            if isinstance(claim, dict) and claim.get("text"):
                assert len(claim["text"].split()) <= ADVISOR_SECTION_WORD_LIMIT + 1


def test_every_advisor_claim_carries_its_kind(db):
    from app.services import advisor_service, focus_service

    make_opportunity(db, deadline=date.today() + timedelta(days=10))
    focus_service.recompute_all(db)
    db.commit()

    response = advisor_service.ask(db, "focus_today")
    for section in response["sections"].values():
        claims = section if isinstance(section, list) else [section]
        for claim in claims:
            if isinstance(claim, dict) and claim.get("text"):
                assert claim["kind"] in {
                    "verified_fact", "ai_interpretation", "assumption",
                    "prediction", "recommendation",
                }
                assert claim["kind_label"]


def test_advisor_says_when_it_cannot_answer(db):
    """Better than a thin answer — the first confidently-wrong response
    costs more trust than a dozen honest refusals."""
    from app.services import advisor_service

    response = advisor_service.ask(db, "focus_today")
    assert response["answerable"] is False
    assert response["unanswerable_reason"]


def test_advisor_rejects_unknown_questions(db):
    from app.services import advisor_service

    response = advisor_service.ask(db, "what is the meaning of life")
    assert response["answerable"] is False
    assert "unknown question" in response["unanswerable_reason"].lower()


# ======================================================== decision journal

def test_decision_recorded_with_frozen_snapshot(db):
    """Reading the live opportunity later would show today's evidence, not
    what was known at the time."""
    import json

    from app.services import focus_service, journal_service

    opp = make_opportunity(db, deadline=date.today() + timedelta(days=30))
    focus_service.recompute_all(db)
    db.commit()

    entry = journal_service.record_decision(
        db, opportunity_id=opp.id, decision="pursue", response="accepted",
        recommended_decision="pursue", recommendation_rationale="Qualified, tier 1 evidence",
        owner_name="Tom Wood",
    )
    db.commit()

    assert entry.evidence_snapshot
    assert json.loads(entry.evidence_snapshot)[0]["tier"] == "tier_1"
    assert entry.scores_snapshot
    assert entry.focus_score_at_decision is not None
    assert entry.profile_version is None   # no profile yet — honest


def test_journal_records_disagreement_with_recommendation(db):
    from app.services import journal_service

    opp = make_opportunity(db)
    journal_service.record_decision(
        db, opportunity_id=opp.id, decision="decline", response="rejected",
        recommended_decision="pursue",
    )
    db.commit()

    entries = journal_service.journal_entries(db)
    assert entries[0]["agreed_with_recommendation"] is False
    assert entries[0]["response"] == "rejected"


def test_turnaround_measured(db):
    from app.services import journal_service

    opp = make_opportunity(db)
    entry = journal_service.record_decision(
        db, opportunity_id=opp.id, decision="pursue", response="accepted",
        recommended_decision="pursue",
        recommended_at=utcnow() - timedelta(hours=6),
    )
    db.commit()

    assert entry.turnaround_hours is not None
    assert 5.5 < entry.turnaround_hours < 6.5


def test_outcome_closes_the_loop(db):
    from app.services import journal_service

    opp = make_opportunity(db)
    entry = journal_service.record_decision(
        db, opportunity_id=opp.id, decision="pursue", response="accepted",
        recommended_decision="pursue",
    )
    db.commit()

    journal_service.record_outcome(
        db, entry.id, status="lost", recommendation_was_correct=False,
        failed_assumption="Assumed a local partner would be available",
        lessons_learned="Verify partner availability before recommending pursuit",
    )
    db.commit()

    recorded = journal_service.journal_entries(db)[0]
    assert recorded["outcome"]["status"] == "lost"
    assert recorded["outcome"]["recommendation_was_correct"] is False
    assert recorded["outcome"]["failed_assumption"]


def test_outcome_auto_detected_from_stage(db):
    from app.services import journal_service

    opp = make_opportunity(db)
    journal_service.record_decision(
        db, opportunity_id=opp.id, decision="pursue", response="accepted",
        recommended_decision="pursue",
    )
    db.commit()

    opp.stage = Stage.WON
    db.commit()

    updated = journal_service.detect_outcomes_from_stage(db)
    db.commit()

    assert updated == 1
    assert journal_service.journal_entries(db)[0]["outcome"]["status"] == "won"


def test_kpis_measure_decisions_not_usage(db):
    from app.services import journal_service

    opp = make_opportunity(db)
    journal_service.record_decision(db, opportunity_id=opp.id, decision="pursue",
                                    response="accepted", recommended_decision="pursue")
    journal_service.record_decision(db, opportunity_id=opp.id, decision="decline",
                                    response="rejected", recommended_decision="pursue")
    db.commit()

    kpis = journal_service.executive_kpis(db)
    assert kpis["decisions"]["total"] == 2
    assert kpis["decisions"]["pursued"] == 1
    assert kpis["decisions"]["declined"] == 1
    assert kpis["recommendation_effectiveness"]["acceptance_rate_percent"] == 50.0
    for excluded in ("logins", "sessions", "page_views"):
        assert excluded in kpis["excluded_by_design"]
        assert excluded not in kpis


def test_learning_loop_refuses_to_adjust_on_small_sample(db):
    """A loop that swings on three results would amplify noise while
    carrying the authority of having learned something."""
    from app.services import journal_service

    opp = make_opportunity(db)
    for i in range(3):
        entry = journal_service.record_decision(
            db, opportunity_id=opp.id, decision="pursue", response="accepted",
            recommended_decision="pursue",
        )
        journal_service.record_outcome(db, entry.id, status="won",
                                       recommendation_was_correct=True)
    db.commit()

    accuracy = journal_service.compute_accuracy(db)
    db.commit()

    assert accuracy.outcomes_recorded == 3
    assert accuracy.accuracy_rate == 1.0
    assert accuracy.confidence_adjustment is None, "must not adjust below the sample floor"

    summary = journal_service.learning_summary(db)
    assert summary["sample_sufficient"] is False
    assert "amplify noise" in summary["note"]


def test_learning_loop_adjusts_once_sample_is_sufficient(db):
    from app.services import journal_service
    from app.services.journal_service import MAX_CONFIDENCE_ADJUSTMENT, MIN_SAMPLE_FOR_LEARNING

    opp = make_opportunity(db)
    for i in range(MIN_SAMPLE_FOR_LEARNING + 2):
        entry = journal_service.record_decision(
            db, opportunity_id=opp.id, decision="pursue", response="accepted",
            recommended_decision="pursue",
        )
        journal_service.record_outcome(db, entry.id, status="won",
                                       recommendation_was_correct=True)
    db.commit()

    accuracy = journal_service.compute_accuracy(db)
    db.commit()

    assert accuracy.confidence_adjustment is not None
    assert abs(accuracy.confidence_adjustment) <= MAX_CONFIDENCE_ADJUSTMENT
    assert journal_service.learning_summary(db)["sample_sufficient"] is True


def test_learning_loop_names_recurring_failure(db):
    """A percentage says there is a problem; a pattern says what it is."""
    from app.services import journal_service

    opp = make_opportunity(db)
    for _ in range(4):
        entry = journal_service.record_decision(
            db, opportunity_id=opp.id, decision="pursue", response="accepted",
            recommended_decision="pursue",
        )
        journal_service.record_outcome(
            db, entry.id, status="lost", recommendation_was_correct=False,
            failed_assumption="Local partner availability was assumed",
        )
    db.commit()

    accuracy = journal_service.compute_accuracy(db)
    assert accuracy.common_failure_pattern
    assert "local partner" in accuracy.common_failure_pattern.lower()


# ============================================================= vocabulary

def test_vocabulary_distinguishes_the_two_scores():
    from app.vocabulary import SCORE_TERMS

    focus = SCORE_TERMS["executive_focus"]
    priority = SCORE_TERMS["pursuit_priority"]
    assert focus["question"] != priority["question"]
    assert "today" in focus["question"].lower()
    assert "Focus Score" in focus["never"]


def test_claim_kinds_cover_the_full_spectrum():
    from app.vocabulary import CLAIM_KIND_ORDER

    assert CLAIM_KIND_ORDER == [
        "verified_fact", "ai_interpretation", "assumption",
        "prediction", "recommendation",
    ]


# ============================================ engineering quality (sprint 1)

def test_briefing_survives_a_failing_section(db, monkeypatch):
    """The briefing is the landing page. One malformed row in market
    intelligence must not take down priorities, risks and everything else
    — a degraded section is recoverable, a blank page is not."""
    from app.services import briefing_service

    def explode(*args, **kwargs):
        raise RuntimeError("simulated data fault")

    monkeypatch.setattr(briefing_service, "market_intelligence", explode)
    briefing = briefing_service.build_briefing(db)

    assert briefing["sections"]["5_market_intelligence"] == []   # degraded
    assert "1_executive_summary" in briefing["sections"]          # others survive
    assert "6_executive_risks" in briefing["sections"]


def test_failing_summary_degrades_with_a_message(db, monkeypatch):
    from app.services import briefing_service

    monkeypatch.setattr(
        briefing_service, "executive_summary",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fault")),
    )
    briefing = briefing_service.build_briefing(db)
    summary = briefing["sections"]["1_executive_summary"]

    # Reports its own failure rather than looking like "nothing to report".
    assert "could not be prepared" in summary["headline"]
    assert summary["is_complete"] is False


def test_briefing_reports_generation_time(db):
    from app.services import briefing_service

    briefing = briefing_service.build_briefing(db)
    assert "generation_ms" in briefing
    assert isinstance(briefing["generation_ms"], int)


def test_card_queries_do_not_scale_with_card_count(db):
    """Regression guard for the N+1 that made the briefing issue roughly
    forty round trips for five cards, against a 1.5s budget."""
    import ast
    import inspect

    from app.services import briefing_service

    source = inspect.getsource(briefing_service.todays_priorities)
    tree = ast.parse(source.replace("def todays_priorities", "def f", 1))
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
            names = [e.id for e in node.target.elts if isinstance(e, ast.Name)]
            if names == ["opp", "focus"]:
                queries = sum(
                    1 for n in ast.walk(node)
                    if isinstance(n, ast.Attribute) and n.attr == "query"
                )
                assert queries == 0, f"{queries} queries inside the card loop"


def test_commercial_impact_expressed_in_money(db):
    """A movement in points is abstract; the same movement in money is a
    decision input."""
    from app.models_phase2 import CommercialValue
    from app.services import change_detector

    opp = make_opportunity(db, deadline=date.today() + timedelta(days=30))
    db.add(
        CommercialValue(
            opportunity_id=opp.id, published_contract_value=3_000_000.0,
            currency="USD", value_status="published_contract_value",
        )
    )
    db.commit()

    change_detector.record_score_change(db, opp.id, "win_probability", 70, 100)
    change_detector.record_score_change(db, opp.id, "win_probability", 58, 100)
    db.commit()

    result = change_detector.what_changed_for_opportunity(db, opp.id)
    impact = result["commercial_impact"]

    assert impact is not None
    assert impact["direction"] == "loss"
    assert impact["delta"] == -360000     # 3m x 12 points
    assert "USD" in impact["basis"]
    assert impact["is_estimate"] is False


def test_commercial_impact_absent_without_a_value(db):
    """No value means no honest impact figure — better silent than invented."""
    from app.services import change_detector

    opp = make_opportunity(db)
    change_detector.record_score_change(db, opp.id, "win_probability", 70, 100)
    change_detector.record_score_change(db, opp.id, "win_probability", 55, 100)
    db.commit()

    result = change_detector.what_changed_for_opportunity(db, opp.id)
    assert result["commercial_impact"] is None

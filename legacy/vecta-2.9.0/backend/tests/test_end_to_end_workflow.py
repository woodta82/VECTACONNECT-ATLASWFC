"""End-to-end business workflow — RC1.

One opportunity, traced through the complete commercial lifecycle across
every service built in Sprints 1–5:

    1. Opportunity identified          (AI fixture → service layer)
    2. Qualification completed         (owner answers the gate)
    3. Relationship intelligence built (stakeholders, engagements, health)
    4. Executive recommendation        (five models → scenarios → advice)
    5. Decision recorded               (journal, with frozen reasoning)
    6. Outcome captured                (won/lost)
    7. Organisational learning         (accuracy loop, memory)

**Why this test is the most valuable one in the suite.** The unit tests
verify each engine in isolation, and each passes on its own terms. This is
the only test that proves they compose — that the Commercial Profile
actually reaches the scoring path, that qualification actually lifts the
priority cap, that a decision actually becomes learning. Integration
failures live precisely in the gaps between components that individually
work.

Offline: no AI key, no network. The AI response is a fixture.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.database import Base, SessionLocal, engine
from app.models import Contact, Opportunity, Stage
from app.regions import Region, Vertical
from app.timeutils import utcnow

FIXTURES = Path(__file__).parent / "fixtures"


def stub_validator(url: str) -> str:
    """Deterministic offline URL validation — the transport is stubbed,
    the enforcement path is identical to production."""
    return "valid"


@pytest.fixture(autouse=True)
def fresh_db():
    import app.models  # noqa: F401  (registers every table)

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


@pytest.fixture
def commercial_profile(db):
    """VECTA defined. Everything downstream is evaluated against this —
    without it the models fall back to generic defaults."""
    from app.services import profile_service

    profile = profile_service.create_version(
        db,
        {
            "strategic_objectives": "Lead coach education delivery across MENA",
            "growth_priorities": "Government and federation programmes",
            "min_viable_contract_value": 2_000_000,
            "target_contract_value": 5_000_000,
            "target_gross_margin": 32.0,
            "delivery_capacity_fte": 14.0,
            "current_workload_pct": 68.0,
            "risk_appetite": "balanced",
        },
        reason="Initial commercial profile",
        sections={
            "regions": [
                {"region": "mena", "market": "Saudi Arabia", "tier": 1,
                 "rationale": "Primary launchpad"},
            ],
            "capabilities": [
                {"capability": "Coach education", "strength": 88, "specialist_count": 4,
                 "is_specialist_scarce": False, "evidence_note": "Delivered in 6 markets"},
            ],
            "weightings": [
                {"dimension": "strategic_alignment", "weight": 0.40},
                {"dimension": "commercial_attractiveness", "weight": 0.25},
                {"dimension": "win_probability", "weight": 0.25},
                {"dimension": "inverse_risk", "weight": 0.10},
            ],
            "accounts": [
                {"organisation_name": "Saudi Ministry of Sport", "account_type": "government",
                 "tier": 1, "objective": "Long-term pathway partner", "owner_name": "Tom Wood"},
            ],
        },
    )
    db.commit()
    return profile


class TestCompleteBusinessWorkflow:
    """The full lifecycle, in order. Each stage asserts the state the next
    one depends on."""

    def test_stage_1_opportunity_identified(self, db, commercial_profile):
        """AI fixture → strict schema → service layer → scored opportunity."""
        from app.models_phase2 import (
            OpportunityEvidence, PursuitPriority, QualificationAssessment, ScoreAssessment,
        )
        from app.scanner.scan_runner_v2 import process_ai_response

        raw = (FIXTURES / "scan_valid.json").read_text()
        result = process_ai_response(db, raw, url_validator=stub_validator)
        db.commit()

        assert result["created"] == 1
        assert result["parse_failures"] == 0

        opp = db.query(Opportunity).first()
        assert opp.classification == "confirmed_opportunity"
        assert opp.summary and opp.summary.strip()

        # Evidence persisted with claim linkage
        evidence = db.query(OpportunityEvidence).filter_by(opportunity_id=opp.id).all()
        assert any(e.source_tier == "tier_1" for e in evidence)
        assert all(e.url_validation_status == "valid" for e in evidence)

        # Four dimensions scored, stamped with the profile that produced them
        scores = db.query(ScoreAssessment).filter_by(opportunity_id=opp.id).all()
        assert len(scores) == 4
        assert all(s.profile_version == commercial_profile.version for s in scores)

        # The profile's weighting reached the live calculation
        priority = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
        assert priority.weights_used["strategic_alignment"] == 0.40

        assert db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()

    def test_stage_2_qualification_completed(self, db, commercial_profile):
        """Owner answers the gate; the priority cap lifts."""
        from app.models_phase2 import PursuitPriority, QualificationAssessment
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import opportunity_service as svc
        from app.taxonomy import QUALIFICATION_ITEMS

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()

        # Force the blocked state an unreviewed opportunity starts in
        svc.persist_qualification(
            db, opp.id,
            {i["key"]: {"answer": "unknown"} for i in QUALIFICATION_ITEMS},
            classification=opp.classification, deadline=opp.deadline,
        )
        svc._recalculate_priority(db, opp.id, "verification_required")
        db.commit()

        blocked = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
        assert blocked.qualification_restricted is True
        with pytest.raises(svc.ServiceRuleViolation):
            svc.assert_can_enter_active_pipeline(db, opp)

        # The gate must state what unblocks it — never a dead end
        actions = svc.qualification_next_actions(db, opp.id)
        assert actions and all(a["action"] and a["detail"] for a in actions)

        # Owner completes it
        result = svc.answer_qualification_items(
            db, opp.id,
            {i["key"]: {"answer": "yes", "explanation": "Confirmed from the notice."}
             for i in QUALIFICATION_ITEMS},
        )
        db.commit()

        assert result["state"] == "qualified"
        lifted = db.query(PursuitPriority).filter_by(opportunity_id=opp.id).first()
        assert lifted.qualification_restricted is False
        assert lifted.final_score > blocked.final_score
        svc.assert_can_enter_active_pipeline(db, opp)   # no longer raises

    def test_stage_3_relationship_intelligence_developed(self, db, commercial_profile):
        """Stakeholders mapped, engagements logged, health and momentum computed."""
        from app.models_relationship import (
            Engagement, OpportunityStakeholder, RelationshipHealth, Stakeholder,
        )
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import relationship_service

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()

        buyer = Stakeholder(
            full_name="Deputy Minister Al-Rashid", role_title="Deputy Minister",
            organisation_name="Saudi Ministry of Sport", stakeholder_type="economic_buyer",
            decision_authority="final", posture="neutral", region="mena",
            market="Saudi Arabia", relationship_owner="Tom Wood",
        )
        technical = Stakeholder(
            full_name="Dr Haddad", role_title="Technical Director",
            organisation_name="Saudi Ministry of Sport",
            stakeholder_type="technical_influencer", decision_authority="advisory",
            posture="champion", region="mena", relationship_owner="Tom Wood",
        )
        db.add_all([buyer, technical])
        db.commit()

        for s in (buyer, technical):
            db.add(OpportunityStakeholder(opportunity_id=opp.id, stakeholder_id=s.id,
                                          posture=s.posture))

        # Only the technical influencer has been engaged
        db.add(Engagement(
            stakeholder_id=technical.id, opportunity_id=opp.id, engagement_type="meeting",
            occurred_at=utcnow() - timedelta(days=12),
            summary="Briefed on comparable national delivery", outcome="positive",
            was_initiated_by_vecta=True, received_response=True,
        ))
        technical.last_engagement_at = utcnow() - timedelta(days=12)
        db.commit()

        result = relationship_service.recompute_all(db)
        db.commit()
        assert result["computed"] == 2

        health = {
            h.stakeholder_id: h for h in db.query(RelationshipHealth).all()
        }
        # Engaged champion is healthier than an unengaged economic buyer
        assert health[technical.id].score > health[buyer.id].score

        # The buyer is the material gap despite scoring lower on health
        matters = relationship_service.who_matters_most(db, limit=2)
        assert matters[0]["stakeholder_id"] == buyer.id
        assert matters[0]["importance"] > matters[1]["importance"]

    def test_stage_4_executive_recommendation_generated(self, db, commercial_profile):
        """Five models compose into a ranked, evidence-backed recommendation."""
        from app.intelligence_pipeline import (
            build_recommendation, score_recommendation_quality, weigh_evidence,
        )
        from app.readiness_index import (
            assumption_load_factor, compute_confidence, data_completeness_factor,
            evidence_quality_factor, historical_accuracy_factor, model_certainty_factor,
        )
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import focus_service
        from app.taxonomy import QUALIFICATION_ITEMS
        from app.services import opportunity_service as svc

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()
        svc.answer_qualification_items(
            db, opp.id, {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
        )
        db.commit()

        focus_service.recompute_all(db)
        db.commit()

        from app.models_memory import ExecutiveFocus

        focus = db.query(ExecutiveFocus).filter_by(opportunity_id=opp.id).first()
        assert focus is not None
        assert focus.explanation

        evidence = weigh_evidence([
            {"kind": "tier_1_source", "is_verified": True},
            {"kind": "official_announcement", "is_verified": True},
        ])
        assert evidence["is_sufficient"]

        confidence = compute_confidence({
            "evidence_quality": evidence_quality_factor(2, 2, 2),
            "data_completeness": data_completeness_factor(100, 16, 16, 2),
            "historical_accuracy": historical_accuracy_factor(None, 0),
            "assumption_load": assumption_load_factor(1),
            "model_certainty": model_certainty_factor(5, 5, 0),
        })
        assert confidence["should_advise"] is True

        recommendation = build_recommendation(
            action="Approach the economic buyer before consultation closes",
            because="No decision-maker contact on a qualified Tier 1 opportunity",
            impact="high", effort="low", evidence=evidence, confidence=confidence,
            models=["EFS", "RCI", "DCS"], owner="Tom Wood",
            due=date.today() + timedelta(days=7),
            subject_id=opp.id, subject_title=opp.title,
        )

        # Every recommendation states why, and cites its models
        assert recommendation["because"]
        assert {m["code"] for m in recommendation["intelligence_models"]} == {"EFS", "RCI", "DCS"}

        quality = score_recommendation_quality(
            recommendation, subject_focus_score=focus.score
        )
        assert quality["below_threshold"] is False

    def test_stage_5_decision_recorded(self, db, commercial_profile):
        """The journal freezes the reasoning at decision time."""
        from app.models_journal import DecisionJournalEntry
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import focus_service, journal_service

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()
        focus_service.recompute_all(db)
        db.commit()

        entry = journal_service.record_decision(
            db, opportunity_id=opp.id, decision="pursue", response="accepted",
            recommended_decision="pursue",
            recommendation_rationale="Qualified, Tier 1 evidence, tier 1 market",
            recommendation_confidence="high", owner_name="Tom Wood",
            expected_outcome="Shortlisted at prequalification",
            recommended_at=utcnow() - timedelta(hours=4),
        )
        db.commit()

        # Frozen snapshot — reading the live opportunity later would show
        # today's evidence, not what was known at the time
        assert entry.evidence_snapshot
        assert json.loads(entry.evidence_snapshot)[0]["tier"] == "tier_1"
        assert entry.scores_snapshot
        assert entry.focus_score_at_decision is not None
        assert entry.profile_version == commercial_profile.version
        assert 3.5 < entry.turnaround_hours < 4.5

        assert db.query(DecisionJournalEntry).count() == 1

    def test_stage_6_outcome_captured(self, db, commercial_profile):
        """Won/lost closes the loop the recommendation opened."""
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import focus_service, journal_service

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()
        focus_service.recompute_all(db)
        db.commit()

        entry = journal_service.record_decision(
            db, opportunity_id=opp.id, decision="pursue", response="accepted",
            recommended_decision="pursue", owner_name="Tom Wood",
        )
        db.commit()

        opp.stage = Stage.WON
        db.commit()
        updated = journal_service.detect_outcomes_from_stage(db)
        db.commit()
        assert updated == 1

        journal_service.record_outcome(
            db, entry.id, status="won", recommendation_was_correct=True,
            actual_value=4_200_000,
            lessons_learned="Early technical engagement shaped the requirements.",
        )
        db.commit()

        recorded = journal_service.journal_entries(db)[0]
        assert recorded["outcome"]["status"] == "won"
        assert recorded["outcome"]["recommendation_was_correct"] is True
        assert recorded["outcome"]["lessons_learned"]

    def test_stage_7_organisational_learning_updated(self, db, commercial_profile):
        """Outcomes feed accuracy; accuracy feeds future confidence."""
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import journal_service
        from app.services.journal_service import MIN_SAMPLE_FOR_LEARNING

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()

        # Below the sample floor: reports but does not adjust
        for _ in range(3):
            entry = journal_service.record_decision(
                db, opportunity_id=opp.id, decision="pursue", response="accepted",
                recommended_decision="pursue",
            )
            journal_service.record_outcome(db, entry.id, status="won",
                                           recommendation_was_correct=True)
        db.commit()

        early = journal_service.compute_accuracy(db)
        db.commit()
        assert early.accuracy_rate == 1.0
        assert early.confidence_adjustment is None
        assert journal_service.learning_summary(db)["sample_sufficient"] is False

        # Above the floor: adjustment becomes active
        for _ in range(MIN_SAMPLE_FOR_LEARNING):
            entry = journal_service.record_decision(
                db, opportunity_id=opp.id, decision="pursue", response="accepted",
                recommended_decision="pursue",
            )
            journal_service.record_outcome(db, entry.id, status="won",
                                           recommendation_was_correct=True)
        db.commit()

        mature = journal_service.compute_accuracy(db)
        db.commit()
        assert mature.confidence_adjustment is not None
        assert journal_service.learning_summary(db)["sample_sufficient"] is True

        kpis = journal_service.executive_kpis(db)
        assert kpis["decisions"]["total"] >= MIN_SAMPLE_FOR_LEARNING + 3
        assert kpis["recommendation_effectiveness"]["sample_sufficient"] is True


class TestExecutiveExperienceEndToEnd:
    """The CEO test: can the four questions be answered in one read?"""

    @pytest.fixture
    def working_pipeline(self, db, commercial_profile):
        from app.models_relationship import Engagement, OpportunityStakeholder, Stakeholder
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import focus_service, relationship_service

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()
        opp = db.query(Opportunity).first()

        buyer = Stakeholder(
            full_name="Deputy Minister Al-Rashid", stakeholder_type="economic_buyer",
            decision_authority="final", organisation_name="Saudi Ministry of Sport",
            region="mena", relationship_owner="Tom Wood",
        )
        db.add(buyer)
        db.commit()
        db.add(OpportunityStakeholder(opportunity_id=opp.id, stakeholder_id=buyer.id))
        db.commit()

        focus_service.recompute_all(db)
        relationship_service.recompute_all(db)
        db.commit()
        return opp

    def test_briefing_answers_the_four_questions(self, db, working_pipeline):
        from app.services import briefing_service

        briefing = briefing_service.build_briefing(db)
        sections = briefing["sections"]

        # What changed?
        assert "3_what_changed" in sections
        # What matters?
        assert "2_todays_priorities" in sections
        # What decisions require attention?
        assert sections["1_executive_summary"]["headline"]
        # Which relationships need action?
        assert "4_relationship_watchlist" in sections
        # And it costs nothing
        assert briefing["ai_calls_used"] == 0

    def test_briefing_survives_a_failing_section(self, db, working_pipeline, monkeypatch):
        """The landing page must degrade, never blank."""
        from app.services import briefing_service

        monkeypatch.setattr(
            briefing_service, "market_intelligence",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fault")),
        )
        briefing = briefing_service.build_briefing(db)
        assert briefing["sections"]["5_market_intelligence"] == []
        assert briefing["sections"]["2_todays_priorities"] is not None

    def test_decision_card_is_decidable_without_navigation(self, db, working_pipeline):
        """The test of whether the card carries enough."""
        from app.services import briefing_service

        cards = briefing_service.todays_priorities(db, limit=1)
        assert cards
        card = cards[0]

        for field in (
            "recommended_decision", "why_this_matters", "confidence", "focus_score",
            "risk", "opportunity_cost_of_waiting", "recommended_next_action",
            "target_date", "supporting_evidence", "required_relationships",
        ):
            assert field in card, f"card missing {field}"

        # Recommendation renders before metrics
        keys = list(card.keys())
        assert keys.index("recommended_decision") < keys.index("strategic_alignment")

    def test_advisor_answers_with_citations_and_confidence(self, db, working_pipeline):
        from app.services import advisor_service

        response = advisor_service.ask(db, "focus_today")
        assert list(response["sections"].keys())[0] == "1_recommendation"
        assert response["intelligence_models"]
        assert response["ai_calls_used"] == 0

    def test_relationship_questions_answerable(self, db, working_pipeline):
        from app.services import relationship_service

        assert relationship_service.who_matters_most(db)
        assert relationship_service.who_are_we_missing(db) is not None
        assert relationship_service.where_to_invest_time(db) is not None
        coverage = relationship_service.compute_coverage_index(db, working_pipeline.id)
        assert coverage["available"]
        assert coverage["explanation"]
        assert coverage["pursuit_recommendation"]["rationale"]


class TestWorkflowIntegrity:
    """Guards on properties that span components — where integration
    failures actually live."""

    def test_profile_change_does_not_rewrite_scored_history(self, db, commercial_profile):
        from app.models_phase2 import ScoreAssessment
        from app.scanner.scan_runner_v2 import process_ai_response
        from app.services import profile_service

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()

        before = {s.dimension: s.score for s in db.query(ScoreAssessment).all()}
        profile_service.create_version(db, {"min_viable_contract_value": 5_000_000},
                                       reason="Raised the floor")
        profile_service.mark_scores_stale(db)
        db.commit()

        after = {s.dimension: (s.score, s.is_stale) for s in db.query(ScoreAssessment).all()}
        for dimension, score in before.items():
            assert after[dimension][0] == score, "a profile change must not rewrite history"
            assert after[dimension][1] is True

    def test_predictions_never_enter_the_opportunity_pipeline(self, db):
        """Structural guard — predictions live in their own table."""
        import app.models  # noqa: F401

        assert "opportunities" in Base.metadata.tables
        opportunity_columns = set(Base.metadata.tables["opportunities"].columns.keys())
        assert "predicted_type" not in opportunity_columns
        assert "time_horizon_months_min" not in opportunity_columns

    def test_every_persisted_score_carries_its_profile_version(self, db, commercial_profile):
        from app.models_phase2 import PursuitPriority, ScoreAssessment
        from app.scanner.scan_runner_v2 import process_ai_response

        process_ai_response(db, (FIXTURES / "scan_valid.json").read_text(),
                            url_validator=stub_validator)
        db.commit()

        assert all(
            s.profile_version == commercial_profile.version
            for s in db.query(ScoreAssessment).all()
        )
        assert all(
            p.profile_version == commercial_profile.version
            for p in db.query(PursuitPriority).all()
        )

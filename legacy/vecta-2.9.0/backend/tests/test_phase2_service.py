"""Phase 2 service-layer and model-registration tests.

These exist because the previous verification method — grepping for
import strings and confirming the target names existed somewhere in the
package — could not detect that `from . import evidence` inside
`app/services/` resolves to the wrong package. Everything here performs a
REAL import and REAL database writes.

Runs on SQLite with no AI dependency and no network.
"""
import importlib

import pytest
from sqlalchemy import inspect

from app.database import Base, SessionLocal, engine
from app.models import Opportunity
from app.regions import Region, Vertical
from app.timeutils import utcnow


# ------------------------------------------------------- import safety

def test_opportunity_service_imports():
    """The regression test for the blocking ImportError. If the relative
    imports are wrong this raises, and no other test in this module can
    run either."""
    module = importlib.import_module("app.services.opportunity_service")
    assert module is not None
    for attr in (
        "persist_evidence",
        "persist_scores",
        "persist_pursuit_priority",
        "persist_qualification",
        "enforce_classification_evidence",
        "assert_can_enter_active_pipeline",
        "record_override",
        "record_parse_failure",
    ):
        assert hasattr(module, attr), f"service is missing {attr}"


def test_service_actually_bound_to_the_engines():
    """Proves the service holds references to the real engine modules —
    not that the text 'scoring_v2' appears in the file."""
    svc = importlib.import_module("app.services.opportunity_service")
    assert svc.scoring_engine.__name__.endswith("scoring_v2")
    assert svc.qualification_engine.__name__.endswith("qualification")
    assert svc.evidence_engine.__name__.endswith("evidence")
    assert callable(svc.scoring_engine.compute_dimension)
    assert callable(svc.qualification_engine.evaluate_qualification)
    assert callable(svc.evidence_engine.validate_confirmed_opportunity)


def test_all_backend_relative_imports_resolve():
    """Runs the resolver over every module, so a wrong-package-root import
    anywhere fails the suite rather than only at runtime."""
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(backend / "tools" / "verify_imports.py")],
        capture_output=True, text=True, cwd=str(backend),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# -------------------------------------------------- model registration

PHASE2_TABLES = {
    "opportunity_evidence",
    "evidence_claims",
    "opportunity_analysis_items",
    "score_assessments",
    "score_factors",
    "pursuit_priorities",
    "qualification_assessments",
    "qualification_checklist_items",
    "qualification_blockers",
    "qualification_overrides",
    "commercial_values",
    "ai_parse_failures",
    "legacy_opportunity_data",
    "override_audits",
    "opportunity_contributing_verticals",
    "opportunity_secondary_commercial_types",
    "opportunity_routes_to_market",
}


def test_phase2_models_registered_on_metadata():
    """Defining models in a separate file does NOT register them — the
    module has to be imported. This asserts that actually happened."""
    import app.models  # noqa: F401  (triggers the models_phase2 import)

    registered = set(Base.metadata.tables.keys())
    missing = PHASE2_TABLES - registered
    assert not missing, f"Phase 2 tables missing from metadata: {sorted(missing)}"


def test_phase2_columns_on_opportunity():
    import app.models  # noqa: F401

    cols = set(Base.metadata.tables["opportunities"].columns.keys())
    for col in (
        "classification",
        "classification_rationale",
        "primary_vertical",
        "vertical_rationale",
        "primary_commercial_type",
        "last_verified_at",
        "verification_confidence",
        "requires_human_review",
        "human_review_reason",
    ):
        assert col in cols, f"opportunities.{col} not registered"


# --------------------------------------------------------- fixtures

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


@pytest.fixture
def opportunity(db):
    opp = Opportunity(
        title="Test Federation Coach Education Tender 2027",
        summary="Open tender for a national coach education delivery partner.",
        vertical=Vertical.PATHWAYS,
        region=Region.MENA,
        classification="unverified_lead",
        primary_vertical="pathways",
    )
    db.add(opp)
    db.commit()
    return opp


def _tier1(**over):
    base = {
        "url": "https://gov.example/tender/123",
        "source_tier": "tier_1",
        "claims_supported": ["opportunity_existence", "live_status"],
        "publication_date": "2026-06-01",
        "url_validation_status": "valid",
        "is_official_source": True,
    }
    base.update(over)
    return base


# ------------------------------------------------- persistence smoke

def test_evidence_and_claims_persist(db, opportunity):
    from app.models_phase2 import EvidenceClaim, OpportunityEvidence
    from app.services import opportunity_service as svc

    svc.persist_evidence(db, opportunity.id, [_tier1()])
    db.commit()

    rows = db.query(OpportunityEvidence).filter_by(opportunity_id=opportunity.id).all()
    assert len(rows) == 1
    assert rows[0].source_tier == "tier_1"
    claims = {c.claim_type for c in db.query(EvidenceClaim).filter_by(evidence_id=rows[0].id).all()}
    assert claims == {"opportunity_existence", "live_status"}


def test_evidence_without_claims_is_rejected(db, opportunity):
    from app.services import opportunity_service as svc

    with pytest.raises(ValueError):
        svc.persist_evidence(db, opportunity.id, [_tier1(claims_supported=[])])


def test_scores_and_factors_persist(db, opportunity):
    from app.models_phase2 import ScoreAssessment, ScoreFactor
    from app.services import opportunity_service as svc

    computed = svc.persist_scores(
        db,
        opportunity.id,
        {
            "strategic_alignment": {"primary_vertical_fit": 90, "geographic_priority": 80},
            "commercial_attractiveness": {"potential_revenue": 70},
            "win_probability": {"eligibility": 60},
            "risk": {"financial_exposure": 30},
        },
    )
    db.commit()

    assessments = db.query(ScoreAssessment).filter_by(opportunity_id=opportunity.id).all()
    assert len(assessments) == 4  # one row per dimension
    assert {a.dimension for a in assessments} == set(computed.keys())

    strategic = next(a for a in assessments if a.dimension == "strategic_alignment")
    factors = db.query(ScoreFactor).filter_by(assessment_id=strategic.id).all()
    assert len(factors) == 9  # every factor stored, scored or not
    assert sum(1 for f in factors if f.scored) == 2


def test_risk_not_established_persisted_when_coverage_low(db, opportunity):
    from app.models_phase2 import ScoreAssessment
    from app.services import opportunity_service as svc

    svc.persist_scores(
        db, opportunity.id,
        {"strategic_alignment": {}, "commercial_attractiveness": {},
         "win_probability": {}, "risk": {"financial_exposure": 10}},
    )
    db.commit()

    risk = db.query(ScoreAssessment).filter_by(opportunity_id=opportunity.id, dimension="risk").first()
    assert risk.risk_established is False  # a low number from thin data must not read as low risk
    assert risk.coverage_percent < 80


def test_qualification_persists_items_and_blockers(db, opportunity):
    from app.models_phase2 import (
        QualificationAssessment,
        QualificationBlocker,
        QualificationChecklistItem,
    )
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    answers = {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    answers["basic_eligibility_met"] = {"answer": "no", "explanation": "Local entity required"}

    result = svc.persist_qualification(
        db, opportunity.id, answers, classification="confirmed_opportunity", deadline=None
    )
    db.commit()

    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity.id).first()
    assert assessment.state == "disqualified"       # absolute bar
    assert assessment.has_absolute_disqualifier is True
    assert result["state"] == assessment.state

    items = db.query(QualificationChecklistItem).filter_by(assessment_id=assessment.id).all()
    assert len(items) == len(QUALIFICATION_ITEMS)   # full checklist stored

    blockers = db.query(QualificationBlocker).filter_by(assessment_id=assessment.id).all()
    assert any(b.failure_type == "absolute_disqualifier" for b in blockers)


def test_remediable_blocker_is_conditional_not_disqualified(db, opportunity):
    from app.models_phase2 import QualificationAssessment
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    answers = {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    answers["local_entity_understood"] = {"answer": "no"}

    svc.persist_qualification(db, opportunity.id, answers, classification=None, deadline=None)
    db.commit()

    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity.id).first()
    assert assessment.state == "conditionally_qualified"
    assert assessment.has_absolute_disqualifier is False


def test_pursuit_priority_persists_with_restrictions(db, opportunity):
    from app.models_phase2 import PursuitPriority
    from app.services import opportunity_service as svc
    from app.scoring_v2 import DIMENSIONS

    full = {d: {f["key"]: 90 for f in info["factors"]} for d, info in DIMENSIONS.items()}
    full["risk"] = {f["key"]: 10 for f in DIMENSIONS["risk"]["factors"]}

    computed = svc.persist_scores(db, opportunity.id, full)
    svc.persist_pursuit_priority(db, opportunity.id, computed, qualification_state="not_assessed")
    db.commit()

    priority = db.query(PursuitPriority).filter_by(opportunity_id=opportunity.id).first()
    assert priority is not None
    assert priority.uncapped_score >= 85          # would have been Immediate
    assert priority.final_score <= 54             # capped: not qualified
    assert priority.qualification_restricted is True
    assert priority.restriction_explanation      # never a silent cap


def test_confirmed_opportunity_downgraded_without_evidence(db, opportunity):
    from app.services import opportunity_service as svc

    opportunity.classification = "confirmed_opportunity"
    db.commit()

    note = svc.enforce_classification_evidence(db, opportunity)
    db.commit()

    assert note is not None
    assert opportunity.classification == "unverified_lead"
    assert opportunity.requires_human_review is True
    assert "evidence requirements not met" in note.lower()


def test_confirmed_opportunity_allowed_with_full_evidence(db, opportunity):
    from app.services import opportunity_service as svc

    svc.persist_evidence(db, opportunity.id, [_tier1()])
    opportunity.classification = "confirmed_opportunity"
    opportunity.last_verified_at = utcnow()
    opportunity.verification_confidence = "high"
    db.commit()

    note = svc.enforce_classification_evidence(db, opportunity)
    db.commit()

    assert note is None
    assert opportunity.classification == "confirmed_opportunity"


def test_pipeline_entry_blocked_until_qualified(db, opportunity):
    """Isolates the QUALIFICATION rule. The fixture is an unverified_lead,
    which the gate blocks on classification, so it is promoted first —
    otherwise this would pass for the wrong reason."""
    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    opportunity.classification = "confirmed_opportunity"
    db.commit()

    with pytest.raises(svc.ServiceRuleViolation) as exc:
        svc.assert_can_enter_active_pipeline(db, opportunity)
    assert any("qualification state" in f.lower() for f in exc.value.failures)

    answers = {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    svc.persist_qualification(
        db, opportunity.id, answers, classification="confirmed_opportunity", deadline=None
    )
    db.commit()

    svc.assert_can_enter_active_pipeline(db, opportunity)  # no longer raises


def test_pipeline_entry_blocked_by_passed_deadline(db, opportunity):
    """Isolates the DEADLINE rule: everything else satisfied, deadline gone."""
    from datetime import date, timedelta

    from app.services import opportunity_service as svc
    from app.taxonomy import QUALIFICATION_ITEMS

    opportunity.classification = "confirmed_opportunity"
    answers = {i["key"]: {"answer": "yes"} for i in QUALIFICATION_ITEMS}
    svc.persist_qualification(
        db, opportunity.id, answers, classification="confirmed_opportunity", deadline=None
    )
    opportunity.deadline = date.today() - timedelta(days=1)
    db.commit()

    with pytest.raises(svc.ServiceRuleViolation) as exc:
        svc.assert_can_enter_active_pipeline(db, opportunity)
    assert "deadline passed" in " ".join(exc.value.failures).lower()


def test_pipeline_gate_reports_all_blocking_reasons(db, opportunity):
    """The gate must surface every objection at once, not drip-feed them.
    Here: non-pipeline classification AND passed deadline AND unassessed
    qualification — all three should appear."""
    from datetime import date, timedelta

    from app.services import opportunity_service as svc

    opportunity.classification = "unverified_lead"
    opportunity.deadline = date.today() - timedelta(days=1)
    db.commit()

    with pytest.raises(svc.ServiceRuleViolation) as exc:
        svc.assert_can_enter_active_pipeline(db, opportunity)

    joined = " ".join(exc.value.failures).lower()
    assert "not an actionable opportunity" in joined
    assert "deadline passed" in joined
    assert "qualification state" in joined
    assert len(exc.value.failures) >= 3


def test_override_requires_reason_and_preserves_original(db, opportunity):
    from app.models_phase2 import OverrideAudit, ScoreAssessment
    from app.services import opportunity_service as svc

    svc.persist_scores(db, opportunity.id, {"strategic_alignment": {"primary_vertical_fit": 40}})
    db.commit()

    with pytest.raises(svc.ServiceRuleViolation):
        svc.record_override(db, opportunity.id, "score.strategic_alignment", 40, 90, reason="")

    svc.override_score(db, opportunity.id, "strategic_alignment", 90, reason="Verified with the buyer")
    db.commit()

    assessment = db.query(ScoreAssessment).filter_by(
        opportunity_id=opportunity.id, dimension="strategic_alignment"
    ).first()
    assert assessment.manual_score == 90
    assert assessment.ai_score == 40          # original preserved, never overwritten
    assert assessment.override_reason

    audit = db.query(OverrideAudit).filter_by(opportunity_id=opportunity.id).first()
    assert audit.original_value == "40" and audit.updated_value == "90"


def test_parse_failure_persisted_without_creating_opportunity(db):
    from app.models_phase2 import AIParseFailure
    from app.services import opportunity_service as svc

    before = db.query(Opportunity).count()
    raw = '{"records": [{"title": "broken"}]}'
    svc.record_parse_failure(db, raw, [{"field": "classification", "message": "Field required"}])
    db.commit()

    failure = db.query(AIParseFailure).first()
    assert failure.parse_status == "parsing_failed"
    assert failure.raw_response == raw          # verbatim, for retry
    assert failure.validation_errors["errors"]
    assert db.query(Opportunity).count() == before  # no partial opportunity

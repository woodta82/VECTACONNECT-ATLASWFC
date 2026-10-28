"""Commercial Profile tests — Phase 3.1.

The critical test here is `test_profile_change_does_not_rewrite_history`.
Everything else is mechanics; that one protects the property that makes
past decisions defensible.
"""
import pytest

from app.database import Base, SessionLocal, engine
from app.models import Opportunity
from app.regions import Region, Vertical


@pytest.fixture(autouse=True)
def fresh_db():
    import app.models  # noqa: F401  (registers phase2 + profile tables)

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


# ------------------------------------------------------- registration

PROFILE_TABLES = {
    "commercial_profile",
    "profile_priority_region",
    "profile_priority_account",
    "profile_target_type",
    "profile_capability",
    "profile_partner",
    "profile_exclusion",
    "profile_route_preference",
    "profile_weighting",
    "profile_factor_anchor",
    "profile_change_log",
}


def test_profile_tables_registered():
    import app.models  # noqa: F401

    missing = PROFILE_TABLES - set(Base.metadata.tables.keys())
    assert not missing, f"profile tables missing from metadata: {sorted(missing)}"


def test_profile_version_columns_on_phase2_tables():
    import app.models  # noqa: F401

    scores = set(Base.metadata.tables["score_assessments"].columns.keys())
    assert "profile_version" in scores
    assert "is_stale" in scores
    assert "profile_version" in set(Base.metadata.tables["pursuit_priorities"].columns.keys())


# ---------------------------------------------------------- versioning

def test_first_version_created(db):
    from app.services import profile_service as ps

    profile = ps.create_version(
        db, {"strategic_objectives": "Grow MENA coach education"}, reason="Initial profile"
    )
    db.commit()

    assert profile.version == 1
    assert profile.is_active is True
    assert ps.active_version(db) == 1


def test_editing_creates_new_version_and_supersedes(db):
    from app.models_profile import CommercialProfile
    from app.services import profile_service as ps

    ps.create_version(db, {"min_viable_contract_value": 1_000_000}, reason="Initial")
    db.commit()
    ps.create_version(db, {"min_viable_contract_value": 2_000_000}, reason="Raised the floor")
    db.commit()

    versions = db.query(CommercialProfile).order_by(CommercialProfile.version).all()
    assert len(versions) == 2
    assert versions[0].is_active is False and versions[0].superseded_at is not None
    assert versions[1].is_active is True
    # The old version is preserved exactly, not edited.
    assert versions[0].min_viable_contract_value == 1_000_000
    assert versions[1].min_viable_contract_value == 2_000_000


def test_version_requires_a_reason(db):
    from app.services import profile_service as ps

    with pytest.raises(ps.ProfileError):
        ps.create_version(db, {"strategic_objectives": "x"}, reason="")


def test_change_log_records_field_level_history(db):
    from app.models_profile import ProfileChangeLog
    from app.services import profile_service as ps

    ps.create_version(db, {"min_viable_contract_value": 1_000_000}, reason="Initial")
    db.commit()
    ps.create_version(
        db, {"min_viable_contract_value": 2_500_000}, reason="Focus on larger contracts"
    )
    db.commit()

    log = db.query(ProfileChangeLog).all()
    entry = next(e for e in log if e.field_path == "min_viable_contract_value")
    assert entry.from_version == 1 and entry.to_version == 2
    assert entry.previous_value == "1000000.0" or entry.previous_value == "1000000"
    assert entry.reason == "Focus on larger contracts"


def test_omitted_sections_carry_forward(db):
    """Editing one section must not silently blank the others — the
    commonest way versioned-config systems lose data."""
    from app.models_profile import ProfileCapability, ProfilePriorityRegion
    from app.services import profile_service as ps

    ps.create_version(
        db, {}, reason="Initial",
        sections={
            "regions": [{"region": "mena", "market": None, "tier": 1, "rationale": "Launchpad"}],
            "capabilities": [{"capability": "Coach education", "strength": 85,
                              "specialist_count": 3, "is_specialist_scarce": True,
                              "evidence_note": None}],
        },
    )
    db.commit()

    # Change only the regions.
    v2 = ps.create_version(
        db, {}, reason="Added UK",
        sections={"regions": [
            {"region": "mena", "market": None, "tier": 1, "rationale": "Launchpad"},
            {"region": "uk_ireland", "market": None, "tier": 1, "rationale": "Home market"},
        ]},
    )
    db.commit()

    assert db.query(ProfilePriorityRegion).filter_by(profile_id=v2.id).count() == 2
    # Capabilities were not mentioned and must survive.
    assert db.query(ProfileCapability).filter_by(profile_id=v2.id).count() == 1


# ------------------------------------------------------------ weights

def test_weights_must_sum_to_one(db):
    from app.services import profile_service as ps

    failures = ps.validate_weights(
        {"strategic_alignment": 0.5, "commercial_attractiveness": 0.2,
         "win_probability": 0.1, "inverse_risk": 0.1}
    )
    assert failures and "sum to 1.0" in failures[0]


def test_unknown_dimension_rejected(db):
    from app.services import profile_service as ps

    failures = ps.validate_weights({"strategic_alignment": 0.5, "vibes": 0.5})
    assert any("Unknown scoring dimensions" in f for f in failures)


def test_invalid_weights_block_version_creation(db):
    from app.models_profile import CommercialProfile
    from app.services import profile_service as ps

    with pytest.raises(ps.ProfileError):
        ps.create_version(
            db, {}, reason="Bad weights",
            sections={"weightings": [
                {"dimension": "strategic_alignment", "weight": 0.9},
                {"dimension": "inverse_risk", "weight": 0.9},
            ]},
        )
    assert db.query(CommercialProfile).count() == 0


def test_no_profile_falls_back_to_documented_defaults(db):
    from app.scoring_v2 import DEFAULT_PRIORITY_WEIGHTS
    from app.services import profile_service as ps

    assert ps.priority_weights(db) == DEFAULT_PRIORITY_WEIGHTS


def test_profile_weights_override_defaults(db):
    from app.services import profile_service as ps

    ps.create_version(
        db, {}, reason="Weight strategy higher",
        sections={"weightings": [
            {"dimension": "strategic_alignment", "weight": 0.50},
            {"dimension": "commercial_attractiveness", "weight": 0.20},
            {"dimension": "win_probability", "weight": 0.20},
            {"dimension": "inverse_risk", "weight": 0.10},
        ]},
    )
    db.commit()

    weights = ps.priority_weights(db)
    assert weights["strategic_alignment"] == 0.50
    assert abs(sum(weights.values()) - 1.0) < 0.001


# ------------------------------------------- scoring integration (live)

@pytest.fixture
def scored_opportunity(db):
    from app.scoring_v2 import DIMENSIONS
    from app.services import opportunity_service as svc

    opp = Opportunity(
        title="Profile Integration Test Opportunity",
        summary="Testing that profile weights reach the live scoring path.",
        vertical=Vertical.PATHWAYS, region=Region.MENA,
        classification="confirmed_opportunity", primary_vertical="pathways",
    )
    db.add(opp)
    db.commit()

    factors = {d: {f["key"]: 90 for f in info["factors"]} for d, info in DIMENSIONS.items()}
    factors["risk"] = {f["key"]: 20 for f in DIMENSIONS["risk"]["factors"]}
    computed = svc.persist_scores(db, opp.id, factors)
    svc.persist_pursuit_priority(db, opp.id, computed, qualification_state="qualified")
    db.commit()
    return opp


def test_priority_uses_profile_weights_and_stamps_version(db, scored_opportunity):
    from app.models_phase2 import PursuitPriority, ScoreAssessment
    from app.services import opportunity_service as svc
    from app.services import profile_service as ps
    from app.scoring_v2 import DIMENSIONS

    before = db.query(PursuitPriority).filter_by(opportunity_id=scored_opportunity.id).first()
    assert before.profile_version is None      # scored before any profile existed
    assert before.weights_used["strategic_alignment"] == 0.35

    ps.create_version(
        db, {}, reason="Strategy-led weighting",
        sections={"weightings": [
            {"dimension": "strategic_alignment", "weight": 0.55},
            {"dimension": "commercial_attractiveness", "weight": 0.20},
            {"dimension": "win_probability", "weight": 0.15},
            {"dimension": "inverse_risk", "weight": 0.10},
        ]},
    )
    db.commit()

    factors = {d: {f["key"]: 90 for f in info["factors"]} for d, info in DIMENSIONS.items()}
    factors["risk"] = {f["key"]: 20 for f in DIMENSIONS["risk"]["factors"]}
    computed = svc.persist_scores(db, scored_opportunity.id, factors)
    svc.persist_pursuit_priority(db, scored_opportunity.id, computed, qualification_state="qualified")
    db.commit()

    after = db.query(PursuitPriority).filter_by(opportunity_id=scored_opportunity.id).first()
    assert after.weights_used["strategic_alignment"] == 0.55   # profile weight reached scoring
    assert after.profile_version == 1                          # and was stamped

    scores = db.query(ScoreAssessment).filter_by(opportunity_id=scored_opportunity.id).all()
    assert all(s.profile_version == 1 for s in scores)
    assert all(s.is_stale is False for s in scores)


def test_profile_change_does_not_rewrite_history(db, scored_opportunity):
    """THE critical property. A profile edit must never mutate an existing
    score — otherwise "why did we decline that in March?" becomes
    unanswerable, because the criteria moved underneath the record."""
    from app.models_phase2 import ScoreAssessment
    from app.services import profile_service as ps

    before = {
        s.dimension: (s.score, s.coverage_percent)
        for s in db.query(ScoreAssessment).filter_by(opportunity_id=scored_opportunity.id).all()
    }
    assert before

    ps.create_version(db, {"strategic_objectives": "Completely different strategy"},
                      reason="Strategic pivot")
    marked = ps.mark_scores_stale(db)
    db.commit()

    after = {
        s.dimension: (s.score, s.coverage_percent, s.is_stale)
        for s in db.query(ScoreAssessment).filter_by(opportunity_id=scored_opportunity.id).all()
    }

    assert marked == len(before)
    for dimension, (score, coverage) in before.items():
        assert after[dimension][0] == score, "score value must not change"
        assert after[dimension][1] == coverage, "coverage must not change"
        assert after[dimension][2] is True, "but it must be flagged stale"


def test_stale_count_reported(db, scored_opportunity):
    from app.services import profile_service as ps

    assert ps.stale_score_count(db) == 0
    ps.create_version(db, {}, reason="change")
    ps.mark_scores_stale(db)
    db.commit()
    assert ps.stale_score_count(db) == 4


# ------------------------------------------------------- completeness

def test_completeness_zero_without_profile(db):
    from app.services import profile_service as ps

    result = ps.completeness(db)
    assert result["percent"] == 0
    assert result["version"] is None
    assert all(not s["complete"] for s in result["sections"])
    assert all(s["fallback"] for s in result["sections"])


def test_completeness_names_the_fallback(db):
    """The main adoption risk is a half-filled profile that looks
    authoritative. Incompleteness must be visible and the fallback named."""
    from app.services import profile_service as ps

    ps.create_version(
        db,
        {"strategic_objectives": "Grow MENA", "growth_priorities": "Coach education",
         "min_viable_contract_value": 2_000_000, "target_contract_value": 5_000_000},
        reason="Partial profile",
        sections={"regions": [{"region": "mena", "market": None, "tier": 1, "rationale": None}]},
    )
    db.commit()

    result = ps.completeness(db)
    assert 0 < result["percent"] < 100
    by_key = {s["key"]: s for s in result["sections"]}
    assert by_key["strategic"]["complete"] is True
    assert by_key["markets"]["complete"] is True
    assert by_key["capabilities"]["complete"] is False
    assert "Capability gaps cannot be identified" in by_key["capabilities"]["fallback"]
    assert by_key["exclusions"]["fallback"]


# ------------------------------------------------- decision-layer queries

def test_exclusion_matching(db):
    from app.services import profile_service as ps

    ps.create_version(
        db, {}, reason="Exclusions",
        sections={"exclusions": [
            {"exclusion_type": "sector", "value": "gambling", "reason": "Board policy"},
            {"exclusion_type": "commercial_type", "value": "sponsorship", "reason": "Out of scope"},
        ]},
    )
    db.commit()

    excluded, reason = ps.is_excluded(db, sector="Gambling")
    assert excluded and "Board policy" in reason
    excluded, _ = ps.is_excluded(db, sector="Football")
    assert not excluded


def test_region_tier_lookup(db):
    from app.services import profile_service as ps

    ps.create_version(
        db, {}, reason="Markets",
        sections={"regions": [
            {"region": "mena", "market": "Saudi Arabia", "tier": 1, "rationale": None},
            {"region": "africa", "market": None, "tier": 3, "rationale": None},
        ]},
    )
    db.commit()

    assert ps.region_tier(db, "mena", "Saudi Arabia") == 1
    assert ps.region_tier(db, "africa") == 3
    assert ps.region_tier(db, "americas") is None   # no view is not low priority


def test_value_threshold(db):
    from app.services import profile_service as ps

    ps.create_version(db, {"min_viable_contract_value": 2_000_000}, reason="Floor")
    db.commit()

    ok, _ = ps.meets_value_threshold(db, 5_000_000)
    assert ok
    ok, reason = ps.meets_value_threshold(db, 1_200_000)
    assert not ok and "Below minimum viable" in reason


def test_capacity_status(db):
    from app.services import profile_service as ps

    assert ps.capacity_status(db)["known"] is False

    ps.create_version(db, {"delivery_capacity_fte": 12.0, "current_workload_pct": 85.0},
                      reason="Capacity")
    db.commit()

    status = ps.capacity_status(db)
    assert status["known"] and status["strained"] is True
    assert "85% utilised" in status["label"]


def test_scarce_capabilities_and_local_partner(db):
    from app.services import profile_service as ps

    ps.create_version(
        db, {}, reason="Capabilities and partners",
        sections={
            "capabilities": [
                {"capability": "Coach education", "strength": 85, "specialist_count": 2,
                 "is_specialist_scarce": True, "evidence_note": None},
                {"capability": "Media production", "strength": 70, "specialist_count": 8,
                 "is_specialist_scarce": False, "evidence_note": None},
            ],
            "partners": [
                {"partner_name": "Gulf Sports Partners", "capability": "Local entity",
                 "regions": "mena", "relationship_strength": 70,
                 "provides_local_entity": True, "is_active": True},
            ],
        },
    )
    db.commit()

    assert ps.scarce_capabilities(db) == ["Coach education"]
    partner = ps.partner_for_local_entity(db, "mena")
    assert partner is not None and partner.partner_name == "Gulf Sports Partners"

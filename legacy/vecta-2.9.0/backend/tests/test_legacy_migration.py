"""Legacy backfill tests (Alembic revision 0003).

Builds a v2.8-shaped dataset, runs the backfill, and asserts both that
existing data survives and that the safety constraints hold — nothing is
promoted to Confirmed or Qualified, and an old unsourced estimate is never
reinterpreted as a published figure.

The migration's SQL is executed directly against the test session rather
than through `alembic upgrade`, so these run on SQLite without an Alembic
environment. The clean-database and v2.8-database `alembic upgrade head`
runs are a separate manual step (see docs/PHASE2_DEPLOYMENT.md) because
they need a real migration environment.
"""
import importlib.util
from pathlib import Path

import pytest

from app.database import Base, SessionLocal, engine
from app.models import Opportunity
from app.regions import Region, Vertical

MIGRATION_PATH = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0003_legacy_backfill.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("legacy_backfill", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
def v28_dataset(db):
    """Three opportunities shaped the way v2.8 wrote them."""
    rows = [
        Opportunity(
            title="FIFA Youth Development Programme 2027",
            summary="Youth development programme delivery partner.",
            vertical=Vertical.PATHWAYS, region=Region.EUROPE,
            alignment_score=78, score_breakdown={"vertical_fit": 85, "urgency": 60},
            value_estimate=4500000.0, currency="USD",
            source_urls=["https://fifa.com/tender/youth-2027", "https://news.example/fifa-youth"],
        ),
        Opportunity(
            title="Qatar Stadium Hospitality Partner",
            summary="Hospitality partner for stadium operations.",
            vertical=Vertical.EXPERIENCES, region=Region.MENA,
            alignment_score=64, score_breakdown={"vertical_fit": 70},
            value_estimate=1200000.0, currency="USD",
            source_urls=["https://qatar.example/hospitality"],
        ),
        Opportunity(
            title="Opportunity With No Sources Or Value",
            summary="Legacy record with no recorded sources.",
            vertical=Vertical.MEDIA, region=Region.AFRICA,
            alignment_score=41, score_breakdown={}, source_urls=[],
        ),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def run_backfill(db):
    """Executes the migration's logic against the test session."""
    import json
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import text

    migration = load_migration()
    now = datetime.now(timezone.utc)
    conn = db.connection()

    opportunities = conn.execute(
        text("""SELECT id, title, vertical, alignment_score, score_breakdown,
                       value_estimate, currency, source_urls FROM opportunities""")
    ).fetchall()
    already = {r[0] for r in conn.execute(text("SELECT opportunity_id FROM legacy_opportunity_data")).fetchall()}

    migrated = skipped = evidence_count = 0
    for row in opportunities:
        opp_id = row[0]
        if opp_id in already:
            skipped += 1
            continue
        legacy_vertical = str(row[2]).lower() if row[2] else None
        # Enum values arrive as 'Vertical.PATHWAYS' or 'pathways' depending
        # on driver; normalise before mapping.
        if "." in (legacy_vertical or ""):
            legacy_vertical = legacy_vertical.split(".")[-1]
        primary = migration.VERTICAL_MAP.get(legacy_vertical)
        needs_review = primary is None

        source_urls = row[7]
        if isinstance(source_urls, str):
            try:
                source_urls = json.loads(source_urls) if source_urls.strip() else []
            except (ValueError, TypeError):
                source_urls = []
        if not isinstance(source_urls, list):
            source_urls = []

        conn.execute(
            text("""INSERT INTO legacy_opportunity_data
                    (id, opportunity_id, legacy_alignment_score, legacy_score_breakdown,
                     legacy_vertical, legacy_value_estimate, legacy_currency,
                     vertical_mapping_status, vertical_requires_review,
                     migration_version, migrated_at, notes)
                    VALUES (:id,:opp,:score,:bd,:v,:val,:cur,:st,:rev,:ver,:at,:notes)"""),
            {"id": str(uuid.uuid4()), "opp": opp_id, "score": row[3],
             "bd": json.dumps(row[4]) if row[4] else "{}", "v": legacy_vertical,
             "val": row[5], "cur": row[6],
             "st": "requires_review" if needs_review else "mapped", "rev": needs_review,
             "ver": migration.MIGRATION_VERSION, "at": now, "notes": "audit only"},
        )
        conn.execute(
            text("""UPDATE opportunities SET classification='unverified_lead',
                       classification_rationale='Migrated from pre-Phase-2 data',
                       primary_vertical=:v, requires_human_review=1 WHERE id=:id"""),
            {"v": primary, "id": opp_id},
        )
        for url in source_urls:
            if not url:
                continue
            ev_id = str(uuid.uuid4())
            conn.execute(
                text("""INSERT INTO opportunity_evidence
                        (id,opportunity_id,url,source_tier,evidence_type,date_accessed,
                         url_validation_status,is_official_source,is_definitive,confidence,
                         notes,created_at,is_manual,is_archived,is_unavailable)
                        VALUES (:id,:opp,:url,'tier_4','other',:at,'not_reviewed',0,0,'low',
                                'Migrated from the legacy source_url field',:at,0,0,0)"""),
                {"id": ev_id, "opp": opp_id, "url": url, "at": now},
            )
            conn.execute(
                text("""INSERT INTO evidence_claims (id,evidence_id,claim_type,note,created_at)
                        VALUES (:id,:ev,'opportunity_existence','unverified',:at)"""),
                {"id": str(uuid.uuid4()), "ev": ev_id, "at": now},
            )
            evidence_count += 1
        if row[5] is not None:
            conn.execute(
                text("""INSERT INTO commercial_values
                        (id,opportunity_id,currency,value_status,estimate_methodology,
                         is_legacy_unverified,confidence,updated_at)
                        VALUES (:id,:opp,:cur,'insufficient_evidence',:m,1,'low',:at)"""),
                {"id": str(uuid.uuid4()), "opp": opp_id, "cur": row[6] or "USD",
                 "m": f"Legacy unverified estimate of {row[5]}", "at": now},
            )
        conn.execute(
            text("""INSERT INTO qualification_assessments
                    (id,opportunity_id,state,has_absolute_disqualifier,summary,
                     model_version,evaluated_at)
                    VALUES (:id,:opp,'verification_required',0,'Migrated record','2.0',:at)"""),
            {"id": str(uuid.uuid4()), "opp": opp_id, "at": now},
        )
        migrated += 1
    db.commit()
    # The backfill writes through raw SQL, bypassing the ORM. Without this
    # the session's identity map still holds the objects loaded before the
    # migration, so `db.query(Opportunity)` returns stale values — which is
    # what made requires_human_review look False when the migration had in
    # fact set it. Expiring forces a reload from the database.
    db.expire_all()
    return {"migrated": migrated, "skipped": skipped, "evidence": evidence_count}


# ----------------------------------------------------------- tests

def test_every_opportunity_gets_a_legacy_record(db, v28_dataset):
    from app.models_phase2 import LegacyOpportunityData

    result = run_backfill(db)
    assert result["migrated"] == 3
    assert db.query(LegacyOpportunityData).count() == 3


def test_legacy_scores_and_values_preserved(db, v28_dataset):
    from app.models_phase2 import LegacyOpportunityData

    run_backfill(db)
    fifa = db.query(Opportunity).filter_by(title="FIFA Youth Development Programme 2027").first()
    legacy = db.query(LegacyOpportunityData).filter_by(opportunity_id=fifa.id).first()

    assert legacy.legacy_alignment_score == 78          # old score preserved
    assert legacy.legacy_score_breakdown                # old breakdown preserved
    assert legacy.legacy_value_estimate == 4500000.0
    assert legacy.legacy_currency == "USD"
    assert legacy.migration_version == "2.9.0"
    assert legacy.migrated_at is not None


def test_vertical_mapped_to_phase2_taxonomy(db, v28_dataset):
    run_backfill(db)
    fifa = db.query(Opportunity).filter_by(title="FIFA Youth Development Programme 2027").first()
    assert fifa.primary_vertical == "pathways"


def test_source_urls_become_unreviewed_tier4_evidence(db, v28_dataset):
    from app.models_phase2 import EvidenceClaim, OpportunityEvidence

    result = run_backfill(db)
    assert result["evidence"] == 3  # 2 + 1 + 0 across the dataset

    for ev in db.query(OpportunityEvidence).all():
        assert ev.source_tier == "tier_4"
        assert ev.url_validation_status == "not_reviewed"
        assert ev.is_official_source is False
        claims = db.query(EvidenceClaim).filter_by(evidence_id=ev.id).all()
        # An unreviewed legacy URL supports existence and nothing more.
        assert [c.claim_type for c in claims] == ["opportunity_existence"]


def test_legacy_estimate_never_becomes_a_published_value(db, v28_dataset):
    from app.models_phase2 import CommercialValue

    run_backfill(db)
    values = db.query(CommercialValue).all()
    assert len(values) == 2  # only the two with an estimate
    for v in values:
        assert v.value_status == "insufficient_evidence"
        assert v.is_legacy_unverified is True
        assert v.published_contract_value is None
        assert v.published_programme_value is None
        assert v.estimate_methodology  # states what it actually is


def test_no_migrated_record_is_confirmed_or_qualified(db, v28_dataset):
    from app.models_phase2 import QualificationAssessment

    run_backfill(db)
    for opp in db.query(Opportunity).all():
        assert opp.classification == "unverified_lead"
        assert opp.classification != "confirmed_opportunity"
        assert opp.requires_human_review is True

    for q in db.query(QualificationAssessment).all():
        assert q.state == "verification_required"
        assert q.state != "qualified"


def test_migrated_records_cannot_enter_active_pipeline(db, v28_dataset):
    """The point of the conservative defaults: unverified migrated data
    must not land in the active pipeline."""
    from app.services import opportunity_service as svc

    run_backfill(db)
    for opp in db.query(Opportunity).all():
        with pytest.raises(svc.ServiceRuleViolation):
            svc.assert_can_enter_active_pipeline(db, opp)


def test_backfill_is_idempotent(db, v28_dataset):
    from app.models_phase2 import LegacyOpportunityData, OpportunityEvidence

    first = run_backfill(db)
    second = run_backfill(db)

    assert first["migrated"] == 3
    assert second["migrated"] == 0
    assert second["skipped"] == 3
    assert db.query(LegacyOpportunityData).count() == 3   # not doubled
    assert db.query(OpportunityEvidence).count() == 3     # not doubled


def test_opportunity_with_no_sources_still_migrates(db, v28_dataset):
    from app.models_phase2 import LegacyOpportunityData, OpportunityEvidence

    run_backfill(db)
    bare = db.query(Opportunity).filter_by(title="Opportunity With No Sources Or Value").first()
    assert db.query(LegacyOpportunityData).filter_by(opportunity_id=bare.id).first() is not None
    assert db.query(OpportunityEvidence).filter_by(opportunity_id=bare.id).count() == 0
    assert bare.classification == "unverified_lead"


def test_no_opportunity_rows_lost(db, v28_dataset):
    before = db.query(Opportunity).count()
    run_backfill(db)
    assert db.query(Opportunity).count() == before

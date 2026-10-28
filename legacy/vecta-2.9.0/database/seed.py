"""Seed data for first-run testing — a handful of demo organisations,
opportunities and users spanning different verticals, regions and pipeline
stages, so the Control Panel and Opportunities pages have something to show
before the first Global Scanner cycle completes.

Run from the backend directory with the virtualenv active:

    python -m database.seed

(or, from repo root: cd backend && python ../database/seed.py — see
docs/SETUP.md).
"""
import sys
from datetime import date, timedelta
from pathlib import Path

# Make the backend app importable when run as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Opportunity, Organisation, OrgType, Stage  # noqa: E402
from app.regions import Region, Vertical  # noqa: E402


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ATLAS is single-login: no users, roles or accounts are seeded.
        # The authorised credential is created separately and securely by
        # seed_auth_credential() on backend startup — never here.
        if db.query(Organisation).count() > 0:
            print("Seed data already present — skipping.")
            return

        f1 = Organisation(name="Abu Dhabi Grand Prix", org_type=OrgType.VENUE, region=Region.MENA, market="UAE")
        fifa = Organisation(name="FIFA", org_type=OrgType.FEDERATION, region=Region.EUROPE, market="Switzerland")
        saudi_gov = Organisation(name="Saudi Ministry of Sport", org_type=OrgType.GOVERNMENT, region=Region.MENA, market="Saudi Arabia")
        db.add_all([f1, fifa, saudi_gov])
        db.flush()

        demo_opportunities = [
            Opportunity(
                organisation_id=f1.id,
                title="F1 Abu Dhabi Grand Prix — Hospitality Partner Tender 2027",
                summary="Premium hospitality and activation tender for the 2027 Abu Dhabi Grand Prix weekend, seeking a delivery partner for VIP suites and paddock club experiences.",
                vertical=Vertical.EXPERIENCES,
                region=Region.MENA,
                market="UAE",
                value_estimate=2_400_000,
                currency="GBP",
                deadline=date.today() + timedelta(days=10),
                source_urls=["https://example.com/f1-abu-dhabi-tender"],
                alignment_score=86,
                score_breakdown={
                    "vertical_fit": 95,
                    "commercial_value": 90,
                    "regional_relevance": 100,
                    "deliverability": 60,
                    "loop_value": 70,
                },
                priority=True,
                stage=Stage.QUALIFIED,
            ),
            Opportunity(
                organisation_id=fifa.id,
                title="FIFA Regional Media Distribution RFP — MENA & South Asia",
                summary="Open RFP for digital and broadcast distribution rights across MENA and South Asia territories for an upcoming tournament cycle.",
                vertical=Vertical.MEDIA,
                region=Region.MENA,
                market="Regional",
                value_estimate=1_100_000,
                currency="GBP",
                deadline=date.today() + timedelta(days=45),
                source_urls=["https://example.com/fifa-media-rfp"],
                alignment_score=74,
                score_breakdown={
                    "vertical_fit": 85,
                    "commercial_value": 75,
                    "regional_relevance": 80,
                    "deliverability": 55,
                    "loop_value": 60,
                },
                priority=True,
                stage=Stage.DISCOVERED,
            ),
            Opportunity(
                organisation_id=saudi_gov.id,
                title="Saudi Grassroots Football Pathways Programme — Education Partner",
                summary="Government-backed grassroots development programme seeking an education and pathways delivery partner across five regions.",
                vertical=Vertical.PATHWAYS,
                region=Region.MENA,
                market="Saudi Arabia",
                value_estimate=650_000,
                currency="GBP",
                deadline=date.today() + timedelta(days=90),
                source_urls=["https://example.com/saudi-pathways"],
                alignment_score=61,
                score_breakdown={
                    "vertical_fit": 90,
                    "commercial_value": 50,
                    "regional_relevance": 100,
                    "deliverability": 40,
                    "loop_value": 50,
                },
                priority=False,
                stage=Stage.DISCOVERED,
            ),
        ]
        db.add_all(demo_opportunities)
        db.commit()
        print(f"Seeded {len(demo_opportunities)} opportunities, 3 organisations, 2 users.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

"""Relationship Intelligence API — Sprint 2.

Endpoints are named for the executive question they answer, not for the
resource they expose. `/relationships/where-to-invest` is a question;
`/stakeholders?sort=health` is a table, and would put the work of
answering back on the reader.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models_relationship import Stakeholder
from ..services import relationship_service as svc

logger = logging.getLogger("atlas.api.relationships")

router = APIRouter(prefix="/relationships", tags=["relationships"])


def _safe(name: str, fn, fallback):
    """Runs one query in isolation.

    The production readiness review found 0 of 12 endpoints here with
    error handling. Relationship intelligence sits inside the executive
    briefing, so an unhandled exception in one query takes down the
    landing page — the same failure the briefing's section isolation
    exists to prevent, one layer lower.

    A degraded answer is recoverable; a 500 on the morning read is not.
    """
    try:
        return fn()
    except Exception:  # noqa: BLE001 — one query must not break the surface
        logger.exception("Relationship query '%s' failed", name)
        return fallback


# ─────────────────────── the six executive questions ───────────────────────

@router.get("/who-matters")
def who_matters(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Q1 — ranked by commercial consequence, not familiarity."""
    return _safe("who_matters", lambda: svc.who_matters_most(db, limit=limit), [])


@router.get("/gaps")
def gaps(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Q2 — who we are missing on live opportunities."""
    return _safe("gaps", lambda: svc.who_are_we_missing(db, limit=limit), [])


@router.get("/improving")
def improving(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Q3 — where investment is working."""
    return _safe("improving", lambda: svc.improving_relationships(db, limit=limit), [])


@router.get("/at-risk")
def at_risk(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Q4 — declining or critical, by commercial consequence."""
    return _safe("at_risk", lambda: svc.relationships_at_risk(db, limit=limit), [])


@router.get("/where-to-invest")
def where_to_invest(limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    """Q5 — where an hour of executive time changes an outcome."""
    return _safe("where_to_invest", lambda: svc.where_to_invest_time(db, limit=limit), [])


@router.get("/impact/{opportunity_id}")
def impact(opportunity_id: str, db: Session = Depends(get_db)):
    """Q6 — how relationships affect this pursuit's odds."""
    try:
        result = svc.relationship_impact_on_success(db, opportunity_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Relationship impact failed for %s", opportunity_id)
        raise HTTPException(500, "Could not compute relationship impact") from exc
    if not result.get("available"):
        raise HTTPException(404, result.get("reason", "Not found"))
    return result


# ───────────────────────────── supporting views ─────────────────────────────

@router.get("/graph")
def graph(opportunity_id: str | None = Query(None), db: Session = Depends(get_db)):
    """Influence network as data. Layout is a presentation concern and is
    deliberately not computed here."""
    return _safe("graph", lambda: svc.influence_graph(db, opportunity_id=opportunity_id),
                 {"nodes": [], "edges": [], "stakeholder_count": 0, "unknown_count": 0})


@router.get("/timeline/{stakeholder_id}")
def timeline(stakeholder_id: str, db: Session = Depends(get_db)):
    """Engagements and milestones merged, plus the health series."""
    if db.get(Stakeholder, stakeholder_id) is None:
        raise HTTPException(404, "Stakeholder not found")
    return _safe("timeline", lambda: svc.relationship_timeline(db, stakeholder_id),
                 {"stakeholder_id": stakeholder_id, "items": [], "health_series": []})


@router.get("/introductions/{stakeholder_id}")
def introductions(stakeholder_id: str, db: Session = Depends(get_db)):
    """Warm routes to someone VECTA does not yet know."""
    if db.get(Stakeholder, stakeholder_id) is None:
        raise HTTPException(404, "Stakeholder not found")
    return {"paths": _safe("introductions",
                           lambda: svc.find_introduction_paths(db, stakeholder_id), [])}


@router.post("/recompute")
def recompute(db: Session = Depends(get_db)):
    """Recomputes health and momentum across every stakeholder.

    Explicit rather than on-read: it walks the full stakeholder set, which
    does not belong inside a page load.
    """
    try:
        result = svc.recompute_all(db)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Relationship recompute failed")
        raise HTTPException(500, "Recompute failed — no changes were saved") from exc
    return result


# ───────────────────── Relationship Coverage Index (2.1) ─────────────────────

@router.get("/coverage/{opportunity_id}")
def coverage(opportunity_id: str, db: Session = Depends(get_db)):
    """RCI for one opportunity.

    Always names the gap TYPE — intelligence, execution or relationship —
    because "we don't know who they are" and "we know but haven't called"
    require completely different responses.
    """
    try:
        result = svc.compute_coverage_index(db, opportunity_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Coverage index failed for %s", opportunity_id)
        raise HTTPException(500, "Could not compute relationship coverage") from exc
    if not result.get("available"):
        raise HTTPException(404, result.get("reason", "Not found"))
    return result


@router.get("/exposure")
def exposure(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Where we are exposed across the pipeline — high focus, thin coverage."""
    return _safe("exposure", lambda: svc.coverage_across_pipeline(db, limit=limit), [])

"""Executive Briefing API — Phase 3.1.

The Briefing is the home screen and must feel instant. `GET /briefing`
returns all seven sections from stored, computed data — **zero AI calls,
zero cost** — so it can be opened as often as you like.

Focus recomputation is a separate, explicit endpoint rather than
happening on read: recomputing across the pipeline inside a page load
would break the 1.5-second budget the Briefing is designed around.
"""
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Opportunity
from ..services import briefing_service, change_detector, focus_service
from ..timeutils import as_aware, utcnow

logger = logging.getLogger("atlas.api.briefing")

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("")
def get_briefing(
    since: str | None = Query(None, description="ISO timestamp; defaults to 24h ago"),
    priorities: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """The full seven-section briefing."""
    since_dt = None
    if since:
        try:
            since_dt = as_aware(datetime.fromisoformat(since))
        except ValueError:
            since_dt = None

    # Time-based changes are detected on read: a deadline crossing 30 days
    # is a genuine change that no write triggers. Deduplicated internally,
    # so opening the briefing repeatedly does not duplicate entries.
    change_detector.detect_time_based_changes(db)
    db.commit()

    result = briefing_service.build_briefing(db, since=since_dt, priority_limit=priorities)

    # Record the open. This is the pilot's adoption metric — the only one
    # of the ten V1.0 success criteria ATLAS could not previously measure,
    # and the one that matters most, since the other nine can all be
    # satisfied by a platform nobody opens.
    try:
        from ..models_journal import BriefingView

        summary = result["sections"].get("1_executive_summary", {})
        db.add(
            BriefingView(
                view_date=date.today(),
                generation_ms=result.get("generation_ms"),
                priorities_shown=len(result["sections"].get("2_todays_priorities", [])),
                changes_shown=len(result["sections"].get("3_what_changed", [])),
                decisions_awaiting=summary.get("counts", {}).get("act_now", 0),
                was_complete=bool(summary.get("is_complete")),
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 — measurement must never break the briefing
        db.rollback()
        logger.exception("Could not record briefing view")

    return result


@router.get("/changes")
def get_changes(
    since: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    since_dt = None
    if since:
        try:
            since_dt = as_aware(datetime.fromisoformat(since))
        except ValueError:
            since_dt = None
    since_dt = since_dt or (utcnow() - timedelta(days=1))
    return {
        "since": since_dt.isoformat(),
        "changes": briefing_service.what_changed(db, since_dt, limit=limit),
        "summary": change_detector.change_summary(db, since_dt),
    }


@router.get("/priorities")
def get_priorities(limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    """Decision Cards only — used by the Decisions screen."""
    return briefing_service.todays_priorities(db, limit=limit)


@router.post("/recompute-focus")
def recompute_focus(db: Session = Depends(get_db)):
    """Recomputes Executive Focus across the pipeline.

    Explicit rather than automatic on read. Still free — no AI calls — but
    it walks every opportunity, which does not belong inside a page load.
    """
    result = focus_service.recompute_all(db)
    db.commit()
    return result


# ------------------------------------------------- Executive AI Advisor

@router.get("/advisor/questions")
def advisor_questions(db: Session = Depends(get_db)):
    """The questions the advisor can answer, each flagged with whether the
    data supports it. The UI must not offer one that would return empty."""
    from ..services import advisor_service

    return advisor_service.available_questions(db)


@router.get("/advisor/{question_key}")
def advisor_answer(
    question_key: str,
    since: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """A six-section advisory response.

    Computed from stored data — no AI call, no cost, instant. Scope is
    restricted to the known question set by design.
    """
    from ..services import advisor_service

    since_dt = None
    if since:
        try:
            since_dt = as_aware(datetime.fromisoformat(since))
        except ValueError:
            since_dt = None
    return advisor_service.ask(db, question_key, since=since_dt)


@router.get("/opportunity/{opportunity_id}/what-changed")
def opportunity_what_changed(opportunity_id: str, db: Session = Depends(get_db)):
    """Strategic Memory for one opportunity: then versus now.

    Previous recommendation, previous Executive Focus, previous win
    probability, previous qualification state — plus a plain-language
    summary of what moved.
    """
    return change_detector.what_changed_for_opportunity(db, opportunity_id)


# --------------------------------------------------- recording decisions

class DecisionIn(BaseModel):
    """A decision recorded from a Decision Card.

    `response` distinguishes accepting ATLAS's recommendation from
    overriding it — the difference is the learning signal, and collapsing
    them would lose the only feedback the advisor gets.
    """

    decision: str            # pursue | decline | defer | verify | monitor
    response: str            # accepted | edited | rejected | deferred
    recommended_decision: str
    recommendation_rationale: str | None = None
    recommendation_confidence: str | None = None
    note: str | None = None
    owner_name: str | None = None
    expected_outcome: str | None = None
    recommended_at: str | None = None

    # Pilot feedback — optional. A required field would be answered
    # carelessly, and careless data is worse than absent data.
    usefulness_rating: int | None = None        # 1-5
    confidence_rating: int | None = None        # 1-5
    would_have_reached_alone: bool | None = None
    friction_note: str | None = None


@router.post("/opportunity/{opportunity_id}/decide")
def record_decision(opportunity_id: str, body: DecisionIn, db: Session = Depends(get_db)):
    """Records an executive decision against an opportunity.

    Without this the dashboard is a reading surface: it can recommend but
    not receive a decision, which makes it passive monitoring rather than
    an operating tool. The journal entry also freezes the reasoning, so
    the recommendation becomes checkable against the eventual outcome.
    """
    from ..services import focus_service, journal_service

    recommended_at = None
    if body.recommended_at:
        try:
            recommended_at = as_aware(datetime.fromisoformat(body.recommended_at))
        except ValueError:
            recommended_at = None

    try:
        entry = journal_service.record_decision(
            db,
            opportunity_id=opportunity_id,
            decision=body.decision,
            response=body.response,
            recommended_decision=body.recommended_decision,
            recommendation_rationale=body.recommendation_rationale,
            recommendation_confidence=body.recommendation_confidence,
            decision_note=body.note,
            owner_name=body.owner_name,
            expected_outcome=body.expected_outcome,
            recommended_at=recommended_at,
            usefulness_rating=body.usefulness_rating,
            confidence_rating=body.confidence_rating,
            would_have_reached_alone=body.would_have_reached_alone,
            friction_note=body.friction_note,
        )
    except journal_service.JournalError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))

    # A decided opportunity should leave the focus list — attention has
    # been spent, and it should not reappear tomorrow as though untouched.
    opp = db.get(Opportunity, opportunity_id)
    if opp is not None:
        result = focus_service.compute_for_opportunity(db, opp)
        focus_service.persist_focus(db, opp, result)

    db.commit()
    return {
        "recorded": True,
        "entry_id": entry.id,
        "decision": entry.decision,
        "agreed_with_recommendation": entry.decision == entry.recommended_decision,
        "turnaround_hours": entry.turnaround_hours,
    }


@router.get("/kpis")
def executive_kpis(db: Session = Depends(get_db)):
    """KPIs measuring decision effectiveness, not system usage."""
    from ..services import journal_service

    return journal_service.executive_kpis(db)

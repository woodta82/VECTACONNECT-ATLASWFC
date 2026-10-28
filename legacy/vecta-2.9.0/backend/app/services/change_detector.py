"""Change detection — Phase 3.1.

Populates `change_event`, which is the only thing the Briefing's "what
changed" section reads. **No AI calls.** Two sources of change:

1. **Data comparison** — a score moved, qualification changed, evidence
   was added.
2. **Time elapsed** — a deadline crossed 30 days, an opportunity went 14
   days without movement, an assumption passed its review date.

The second is what makes a daily briefing viable under manual-only AI
cost. Most of what changes overnight is not new intelligence; it is time
acting on data ATLAS already holds. A deadline moving from 31 days to 30
is a genuine change in what deserves attention, and it costs nothing to
detect.

**Materiality is the discipline.** Without a threshold this becomes an
activity log — the exact noise the Briefing exists to replace. A score
moving 2 points is not news; 12 points is.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Opportunity
from ..models_memory import (
    AssumptionLedger,
    ChangeEvent,
    ChangeEventType,
    Materiality,
    ScoreHistory,
)
from ..models_phase2 import (
    CommercialValue,
    OpportunityEvidence,
    PursuitPriority,
    QualificationAssessment,
    ScoreAssessment,
)
from ..timeutils import as_aware, utcnow

# Thresholds. Set high enough that the feed stays readable — an executive
# who sees twelve items every morning stops reading it by Thursday.
SCORE_DELTA_THRESHOLD = 10          # points
PRIORITY_DELTA_THRESHOLD = 8
FOCUS_DELTA_THRESHOLD = 15
STALE_DAYS = 14
DEADLINE_ALERT_DAYS = (30, 14, 7, 2)


def record(db: Session, *, subject_type: str, event_type: str, summary: str,
           opportunity_id: str | None = None, subject_id: str | None = None,
           materiality: str = Materiality.MEDIUM.value, detail: str | None = None,
           previous_value: str | None = None, new_value: str | None = None,
           delta: float | None = None, triggered_by: str = "system",
           profile_version: int | None = None) -> ChangeEvent:
    """Writes one change event. Deduplicated by the callers below, which
    check whether the same event already exists for the same day."""
    event = ChangeEvent(
        subject_type=subject_type,
        subject_id=subject_id or opportunity_id,
        opportunity_id=opportunity_id,
        event_type=event_type,
        materiality=materiality,
        summary=summary,
        detail=detail,
        previous_value=previous_value,
        new_value=new_value,
        delta=delta,
        triggered_by=triggered_by,
        profile_version=profile_version,
    )
    db.add(event)
    db.flush()
    return event


def _already_recorded_today(db: Session, opportunity_id: str, event_type: str) -> bool:
    """Prevents the same time-based event firing on every page load.

    Without this, opening the Briefing three times before lunch would
    produce three identical "deadline approaching" entries.
    """
    since = utcnow() - timedelta(hours=20)
    return (
        db.query(ChangeEvent)
        .filter(
            ChangeEvent.opportunity_id == opportunity_id,
            ChangeEvent.event_type == event_type,
            ChangeEvent.occurred_at >= since,
        )
        .first()
        is not None
    )


# --------------------------------------------------- data-comparison changes

def record_score_change(db: Session, opportunity_id: str, dimension: str,
                        new_score: int, coverage_percent: int,
                        reason: str = "rescore", note: str | None = None,
                        profile_version: int | None = None) -> ChangeEvent | None:
    """Snapshots the score and records a change event if the move is
    material. Returns None for immaterial moves — the history row is still
    written, so the delta remains reconstructable even when it did not
    warrant an executive's attention."""
    previous = (
        db.query(ScoreHistory)
        .filter_by(opportunity_id=opportunity_id, dimension=dimension)
        .order_by(ScoreHistory.recorded_at.desc())
        .first()
    )
    delta = (new_score - previous.score) if previous else None

    db.add(
        ScoreHistory(
            opportunity_id=opportunity_id,
            dimension=dimension,
            score=new_score,
            coverage_percent=coverage_percent,
            delta_from_previous=delta,
            change_reason=reason,
            change_note=note,
            profile_version=profile_version,
        )
    )
    db.flush()

    if delta is None or abs(delta) < SCORE_DELTA_THRESHOLD:
        return None

    opp = db.get(Opportunity, opportunity_id)
    direction = "rose" if delta > 0 else "fell"
    label = dimension.replace("_", " ").title()
    return record(
        db,
        subject_type="opportunity",
        opportunity_id=opportunity_id,
        event_type=ChangeEventType.SCORE_CHANGED.value,
        materiality=Materiality.HIGH.value if abs(delta) >= 20 else Materiality.MEDIUM.value,
        summary=f"{label} {direction} {abs(delta)} points",
        detail=note or f"{opp.title if opp else opportunity_id}: {previous.score} → {new_score}",
        previous_value=str(previous.score),
        new_value=str(new_score),
        delta=float(delta),
        profile_version=profile_version,
    )


def record_qualification_change(db: Session, opportunity_id: str, previous_state: str | None,
                                new_state: str, reason: str | None = None) -> ChangeEvent | None:
    if previous_state == new_state:
        return None

    # A move into or out of pipeline eligibility is always high materiality:
    # it changes what VECTA can actually do.
    pipeline_states = {"qualified", "conditionally_qualified"}
    crossed = (previous_state in pipeline_states) != (new_state in pipeline_states)

    return record(
        db,
        subject_type="opportunity",
        opportunity_id=opportunity_id,
        event_type=ChangeEventType.QUALIFICATION_CHANGED.value,
        materiality=Materiality.HIGH.value if crossed else Materiality.MEDIUM.value,
        summary=f"Qualification: {(previous_state or 'not assessed').replace('_',' ')} → {new_state.replace('_',' ')}",
        detail=reason,
        previous_value=previous_state,
        new_value=new_state,
    )


def record_classification_change(db: Session, opportunity_id: str, previous: str | None,
                                 new: str, reason: str | None = None) -> ChangeEvent | None:
    if previous == new:
        return None
    upgraded = new == "confirmed_opportunity"
    return record(
        db,
        subject_type="opportunity",
        opportunity_id=opportunity_id,
        event_type=ChangeEventType.CLASSIFICATION_CHANGED.value,
        materiality=Materiality.HIGH.value if upgraded else Materiality.MEDIUM.value,
        summary=f"Classification: {(previous or 'none').replace('_',' ')} → {new.replace('_',' ')}",
        detail=reason,
        previous_value=previous,
        new_value=new,
    )


def record_new_opportunity(db: Session, opportunity: Opportunity) -> ChangeEvent:
    confirmed = opportunity.classification == "confirmed_opportunity"
    return record(
        db,
        subject_type="opportunity",
        opportunity_id=opportunity.id,
        event_type=ChangeEventType.OPPORTUNITY_CREATED.value,
        materiality=Materiality.HIGH.value if confirmed else Materiality.MEDIUM.value,
        summary=f"New {(opportunity.classification or 'opportunity').replace('_',' ')}: {opportunity.title}",
        detail=opportunity.summary,
        new_value=opportunity.classification,
    )


# ------------------------------------------------------ time-elapsed changes

def detect_time_based_changes(db: Session, today: date | None = None) -> list[ChangeEvent]:
    """Changes caused by nothing happening.

    This is where a daily briefing gets its content without spending
    anything: deadlines approaching, work going stale, assumptions falling
    due for review.
    """
    today = today or date.today()
    events: list[ChangeEvent] = []
    events += _detect_deadline_alerts(db, today)
    events += _detect_stale_opportunities(db, today)
    events += _detect_overdue_assumptions(db, today)
    return events


def _detect_deadline_alerts(db: Session, today: date) -> list[ChangeEvent]:
    events: list[ChangeEvent] = []
    horizon = today + timedelta(days=max(DEADLINE_ALERT_DAYS))

    rows = (
        db.query(Opportunity)
        .filter(Opportunity.deadline.is_not(None), Opportunity.deadline >= today,
                Opportunity.deadline <= horizon)
        .all()
    )
    for opp in rows:
        days = (opp.deadline - today).days
        threshold = next((d for d in DEADLINE_ALERT_DAYS if days == d), None)
        if threshold is None:
            continue
        if _already_recorded_today(db, opp.id, ChangeEventType.DEADLINE_APPROACHING.value):
            continue
        events.append(
            record(
                db,
                subject_type="opportunity",
                opportunity_id=opp.id,
                event_type=ChangeEventType.DEADLINE_APPROACHING.value,
                materiality=Materiality.HIGH.value if days <= 7 else Materiality.MEDIUM.value,
                summary=f"{days} days to deadline: {opp.title}",
                detail=f"Deadline {opp.deadline.isoformat()}",
                new_value=str(days),
                delta=float(days),
                triggered_by="time_elapsed",
            )
        )
    return events


def _detect_stale_opportunities(db: Session, today: date) -> list[ChangeEvent]:
    """The quiet killer.

    Opportunities rarely fail loudly — they lapse. Nothing else in ATLAS
    notices an opportunity that simply stopped moving, so this is the only
    mechanism that catches it.
    """
    events: list[ChangeEvent] = []
    cutoff = utcnow() - timedelta(days=STALE_DAYS)

    qualified = (
        db.query(Opportunity, QualificationAssessment)
        .join(QualificationAssessment, QualificationAssessment.opportunity_id == Opportunity.id)
        .filter(QualificationAssessment.state.in_(["qualified", "conditionally_qualified"]))
        .all()
    )
    for opp, _ in qualified:
        updated = as_aware(opp.updated_at) if opp.updated_at else None
        if updated is None or updated > cutoff:
            continue
        if _already_recorded_today(db, opp.id, ChangeEventType.WENT_STALE.value):
            continue
        days = (utcnow() - updated).days
        events.append(
            record(
                db,
                subject_type="opportunity",
                opportunity_id=opp.id,
                event_type=ChangeEventType.WENT_STALE.value,
                materiality=Materiality.HIGH.value,
                summary=f"No movement for {days} days: {opp.title}",
                detail="Qualified opportunity with no activity — at risk of lapsing through inaction.",
                new_value=str(days),
                delta=float(days),
                triggered_by="time_elapsed",
            )
        )
    return events


def _detect_overdue_assumptions(db: Session, today: date) -> list[ChangeEvent]:
    """An assumption past its review date is a recommendation resting on
    something nobody has re-checked."""
    events: list[ChangeEvent] = []
    now = utcnow()
    rows = (
        db.query(AssumptionLedger)
        .filter(
            AssumptionLedger.status == "active",
            AssumptionLedger.affects_recommendation.is_(True),
            AssumptionLedger.review_due_at.is_not(None),
            AssumptionLedger.review_due_at < now,
        )
        .all()
    )
    for assumption in rows:
        if _already_recorded_today(db, assumption.opportunity_id,
                                   ChangeEventType.ASSUMPTION_INVALIDATED.value):
            continue
        overdue = (now - as_aware(assumption.review_due_at)).days
        events.append(
            record(
                db,
                subject_type="opportunity",
                opportunity_id=assumption.opportunity_id,
                subject_id=assumption.id,
                event_type=ChangeEventType.ASSUMPTION_INVALIDATED.value,
                materiality=Materiality.HIGH.value,
                summary=f"Assumption review overdue by {overdue} days",
                detail=assumption.assumption_text,
                triggered_by="time_elapsed",
            )
        )
    return events


# --------------------------------------------------------------- reading

def changes_since(db: Session, since: datetime | None = None,
                  min_materiality: str = Materiality.MEDIUM.value,
                  limit: int = 50) -> list[ChangeEvent]:
    """Material changes for the Briefing. Defaults to the last 24 hours
    and excludes low-materiality noise."""
    since = since or (utcnow() - timedelta(days=1))
    allowed = (
        [Materiality.HIGH.value]
        if min_materiality == Materiality.HIGH.value
        else [Materiality.HIGH.value, Materiality.MEDIUM.value]
    )
    return (
        db.query(ChangeEvent)
        .filter(ChangeEvent.occurred_at >= since, ChangeEvent.materiality.in_(allowed))
        .order_by(ChangeEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )


def change_summary(db: Session, since: datetime | None = None) -> dict:
    """Counts for the Briefing header — the "what changed" line an
    executive reads before anything else."""
    events = changes_since(db, since, min_materiality=Materiality.MEDIUM.value, limit=500)
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
    return {
        "total": len(events),
        "high_materiality": sum(1 for e in events if e.materiality == Materiality.HIGH.value),
        "by_type": by_type,
        "since": (since or (utcnow() - timedelta(days=1))).isoformat(),
    }


# ------------------------------------------- strategic memory comparison

def what_changed_for_opportunity(db: Session, opportunity_id: str) -> dict:
    """Then-versus-now for one opportunity.

    Executives care about movement, not state. "Win probability 65" is
    inert; "65, down from 77 since the last review" is a decision trigger.
    This assembles the comparison the Decision Card and detail page show
    under "What changed".

    Reads only stored history — no recomputation, no AI call.
    """
    from ..models_journal import DecisionJournalEntry
    from ..models_memory import ExecutiveFocus

    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        return {"available": False, "reason": "Opportunity not found"}

    # --- scores: current vs the previous recorded snapshot -------------
    dimensions: dict[str, dict] = {}
    for dimension in ("strategic_alignment", "commercial_attractiveness",
                      "win_probability", "risk"):
        history = (
            db.query(ScoreHistory)
            .filter_by(opportunity_id=opportunity_id, dimension=dimension)
            .order_by(ScoreHistory.recorded_at.desc())
            .limit(2)
            .all()
        )
        current = db.query(ScoreAssessment).filter_by(
            opportunity_id=opportunity_id, dimension=dimension
        ).first()
        if current is None:
            continue

        previous = history[1].score if len(history) > 1 else None
        delta = (current.score - previous) if previous is not None else None
        dimensions[dimension] = {
            "current": current.score,
            "previous": previous,
            "delta": delta,
            "direction": "up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else "unchanged",
            "changed_at": history[0].recorded_at.isoformat() if history else None,
            "change_reason": history[0].change_reason if history else None,
            # Risk suppression must survive this layer too.
            "suppressed": current.dimension == "risk" and current.risk_established is False,
        }

    # --- executive focus ----------------------------------------------
    focus = db.query(ExecutiveFocus).filter_by(opportunity_id=opportunity_id).first()
    focus_change = None
    if focus:
        focus_change = {
            "current": focus.score,
            "previous": focus.previous_score,
            "delta": focus.delta,
            "band": focus.band_label,
            "direction": "up" if (focus.delta or 0) > 0 else "down" if (focus.delta or 0) < 0 else "unchanged",
        }

    # --- qualification --------------------------------------------------
    qualification_events = (
        db.query(ChangeEvent)
        .filter_by(opportunity_id=opportunity_id, event_type=ChangeEventType.QUALIFICATION_CHANGED.value)
        .order_by(ChangeEvent.occurred_at.desc())
        .limit(1)
        .all()
    )
    current_qualification = (
        db.query(QualificationAssessment).filter_by(opportunity_id=opportunity_id).first()
    )
    qualification_change = None
    if current_qualification:
        last = qualification_events[0] if qualification_events else None
        qualification_change = {
            "current": current_qualification.state,
            "previous": last.previous_value if last else None,
            "changed_at": last.occurred_at.isoformat() if last and last.occurred_at else None,
        }

    # --- previous recommendation ---------------------------------------
    last_decision = (
        db.query(DecisionJournalEntry)
        .filter_by(opportunity_id=opportunity_id)
        .order_by(DecisionJournalEntry.decided_at.desc())
        .first()
    )
    previous_recommendation = None
    if last_decision:
        previous_recommendation = {
            "recommended": last_decision.recommended_decision,
            "decided": last_decision.decision,
            "response": last_decision.response,
            "decided_at": last_decision.decided_at.isoformat() if last_decision.decided_at else None,
            "focus_at_decision": last_decision.focus_score_at_decision,
            "win_probability_at_decision": last_decision.win_probability_at_decision,
            "agreed": last_decision.decision == last_decision.recommended_decision,
        }

    # --- expected commercial impact --------------------------------------
    # A score movement in points is abstract. "Win probability fell 12
    # points" tells an executive nothing about what it costs; "fell 12
    # points — about $360k of expected value" is a commercial statement
    # they can weigh against other calls on their time.
    #
    # Expected value = commercial value x win probability. Only computed
    # where a value actually exists, and explicitly labelled as an
    # estimate where the underlying value is one.
    commercial_impact = None
    value_row = db.query(CommercialValue).filter_by(opportunity_id=opportunity_id).first()
    win = dimensions.get("win_probability")

    if value_row and win and win.get("delta"):
        base_value = (
            value_row.published_contract_value
            or value_row.estimated_vecta_revenue
            or (
                (value_row.estimated_contract_min + value_row.estimated_contract_max) / 2
                if value_row.estimated_contract_min and value_row.estimated_contract_max
                else None
            )
        )
        if base_value:
            previous_ev = base_value * ((win["previous"] or 0) / 100)
            current_ev = base_value * (win["current"] / 100)
            delta_ev = current_ev - previous_ev
            is_estimate = value_row.value_status == "estimated_range"
            commercial_impact = {
                "previous_expected_value": round(previous_ev),
                "current_expected_value": round(current_ev),
                "delta": round(delta_ev),
                "currency": value_row.currency,
                "direction": "gain" if delta_ev > 0 else "loss",
                "is_estimate": is_estimate,
                "basis": (
                    f"{value_row.currency} {round(abs(delta_ev)):,} "
                    f"{'gained' if delta_ev > 0 else 'lost'} in expected value "
                    f"({win['previous']}% → {win['current']}% win probability"
                    f"{' on an estimated value' if is_estimate else ''})."
                ),
            }

    # --- plain-language summary -----------------------------------------
    lines: list[str] = []
    for dimension, data in dimensions.items():
        if data["delta"] and abs(data["delta"]) >= SCORE_DELTA_THRESHOLD:
            label = dimension.replace("_", " ").title()
            lines.append(f"{label} {data['direction']} {abs(data['delta'])} points")
    if focus_change and focus_change["delta"] and abs(focus_change["delta"]) >= 10:
        lines.append(
            f"Executive Focus {focus_change['direction']} {abs(focus_change['delta'])} points"
        )
    if qualification_change and qualification_change["previous"]:
        lines.append(
            f"Qualification moved to {qualification_change['current'].replace('_',' ')}"
        )
    if commercial_impact:
        lines.append(commercial_impact["basis"].rstrip("."))

    return {
        "available": True,
        "opportunity_id": opportunity_id,
        "summary": "; ".join(lines) if lines else "No material change since the last review.",
        "has_changes": bool(lines),
        "scores": dimensions,
        "executive_focus": focus_change,
        "qualification": qualification_change,
        "previous_recommendation": previous_recommendation,
        "commercial_impact": commercial_impact,
        "recent_events": [
            {
                "event_type": e.event_type,
                "summary": e.summary,
                "materiality": e.materiality,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            }
            for e in db.query(ChangeEvent)
            .filter_by(opportunity_id=opportunity_id)
            .order_by(ChangeEvent.occurred_at.desc())
            .limit(5)
            .all()
        ],
    }

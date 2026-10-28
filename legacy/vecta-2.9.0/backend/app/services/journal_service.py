"""Decision Journal, Executive KPIs and the AI Learning Loop — Phase 3.1.

Three related concerns:

1. **Recording decisions with their reasoning**, frozen at decision time.
2. **KPIs that measure decision effectiveness**, not system usage. Login
   counts and page views tell you nothing about whether VECTA is deciding
   better.
3. **A learning loop** that compares recommendation → decision → outcome.

On the learning loop, one deliberate constraint: confidence adjustments
require a **minimum sample** and are **capped**. A loop that swings on
three results would amplify noise and produce confident nonsense — which
is worse than no learning at all, because it would carry the authority of
having "learned". Slow and evidenced beats responsive and wrong.
"""
from __future__ import annotations

import logging

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Opportunity, Stage
from ..models_journal import (
    DecisionJournalEntry,
    DecisionOutcome,
    DecisionResponse,
    OutcomeStatus,
    RecommendationAccuracy,
    WeeklyReviewLog,
)
from ..models_memory import ExecutiveFocus
from ..models_phase2 import (
    CommercialValue,
    OpportunityAnalysisItem,
    OpportunityEvidence,
    QualificationAssessment,
    ScoreAssessment,
)
from ..timeutils import as_aware, utcnow
from . import profile_service

logger = logging.getLogger("atlas.journal")


# Learning-loop guardrails.
MIN_SAMPLE_FOR_LEARNING = 10        # below this, report but do not adjust
MAX_CONFIDENCE_ADJUSTMENT = 0.15    # never move confidence more than 15%


class JournalError(Exception):
    pass


# ---------------------------------------------------------- recording

def record_decision(db: Session, *, opportunity_id: str | None, decision: str,
                    response: str, recommended_decision: str,
                    recommendation_rationale: str | None = None,
                    recommendation_confidence: str | None = None,
                    decision_note: str | None = None, owner_name: str | None = None,
                    expected_outcome: str | None = None,
                    expected_decision_date: date | None = None,
                    recommended_at: datetime | None = None,
                    usefulness_rating: int | None = None,
                    confidence_rating: int | None = None,
                    would_have_reached_alone: bool | None = None,
                    friction_note: str | None = None) -> DecisionJournalEntry:
    """Records a decision with a frozen snapshot of the reasoning.

    The snapshot is the whole point. Referencing the live opportunity
    would show today's evidence when the entry is read in six months, not
    what was actually known when the decision was made — which would make
    the journal useless for learning anything.
    """
    if not decision or not response:
        raise JournalError("A journal entry requires both a decision and a response.")

    opp = db.get(Opportunity, opportunity_id) if opportunity_id else None

    scores = {}
    focus = None
    qualification = None
    value = None
    evidence_summary = None
    assumptions = []

    if opp:
        scores = {
            s.dimension: {"score": s.score, "coverage": s.coverage_percent,
                          "risk_established": s.risk_established}
            for s in db.query(ScoreAssessment).filter_by(opportunity_id=opp.id).all()
        }
        focus = db.query(ExecutiveFocus).filter_by(opportunity_id=opp.id).first()
        qualification = db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()
        value = db.query(CommercialValue).filter_by(opportunity_id=opp.id).first()

        evidence = db.query(OpportunityEvidence).filter_by(opportunity_id=opp.id).all()
        evidence_summary = [
            {"url": e.url, "tier": e.source_tier, "publisher": e.publisher,
             "validation": e.url_validation_status}
            for e in evidence
        ]
        assumptions = [
            a.content
            for a in db.query(OpportunityAnalysisItem)
            .filter_by(opportunity_id=opp.id, item_type="assumption")
            .all()
        ]

    turnaround = None
    if recommended_at:
        turnaround = round((utcnow() - as_aware(recommended_at)).total_seconds() / 3600, 2)

    entry = DecisionJournalEntry(
        opportunity_id=opportunity_id,
        opportunity_title=opp.title if opp else None,
        recommended_decision=recommended_decision,
        recommendation_rationale=recommendation_rationale,
        recommendation_confidence=recommendation_confidence,
        decision=decision,
        response=response,
        decision_note=decision_note,
        owner_name=owner_name or (opp.owner_name if opp else None),
        evidence_snapshot=json.dumps(evidence_summary) if evidence_summary else None,
        assumptions_snapshot=json.dumps(assumptions) if assumptions else None,
        scores_snapshot=json.dumps(scores) if scores else None,
        focus_score_at_decision=focus.score if focus else None,
        win_probability_at_decision=(scores.get("win_probability") or {}).get("score"),
        risk_at_decision=(scores.get("risk") or {}).get("score"),
        qualification_at_decision=qualification.state if qualification else None,
        expected_outcome=expected_outcome,
        expected_value=(
            value.published_contract_value or value.estimated_vecta_revenue if value else None
        ),
        expected_decision_date=expected_decision_date,
        profile_version=profile_service.active_version(db),
        focus_model_version=focus.model_version if focus else None,
        recommended_at=recommended_at,
        turnaround_hours=turnaround,
        usefulness_rating=usefulness_rating,
        confidence_rating=confidence_rating,
        would_have_reached_alone=would_have_reached_alone,
        friction_note=friction_note,
    )
    db.add(entry)
    db.flush()

    db.add(DecisionOutcome(entry_id=entry.id, status=OutcomeStatus.PENDING.value))
    db.flush()
    return entry


def record_outcome(db: Session, entry_id: str, *, status: str,
                   actual_outcome: str | None = None, actual_value: float | None = None,
                   recommendation_was_correct: bool | None = None,
                   correctness_note: str | None = None,
                   failed_assumption: str | None = None,
                   lessons_learned: str | None = None) -> DecisionOutcome:
    """Closes the loop. Without this the journal is a diary, not a
    learning system."""
    entry = db.get(DecisionJournalEntry, entry_id)
    if entry is None:
        raise JournalError("Journal entry not found.")

    outcome = db.query(DecisionOutcome).filter_by(entry_id=entry_id).first()
    if outcome is None:
        outcome = DecisionOutcome(entry_id=entry_id)
        db.add(outcome)

    outcome.status = status
    outcome.actual_outcome = actual_outcome
    outcome.actual_value = actual_value
    outcome.recommendation_was_correct = recommendation_was_correct
    outcome.correctness_note = correctness_note
    outcome.failed_assumption = failed_assumption
    outcome.lessons_learned = lessons_learned
    outcome.days_to_outcome = (utcnow() - as_aware(entry.decided_at)).days
    outcome.recorded_at = utcnow()
    db.flush()
    return outcome


def detect_outcomes_from_stage(db: Session) -> int:
    """Auto-records outcomes when an opportunity reaches Won or Lost.

    Reduces the manual burden — an outcome nobody records is a learning
    signal lost, and asking someone to remember is asking them to fail.
    The correctness judgement remains manual, because "did the
    recommendation prove right" is not the same as "did we win".
    """
    pending = (
        db.query(DecisionJournalEntry, DecisionOutcome, Opportunity)
        .join(DecisionOutcome, DecisionOutcome.entry_id == DecisionJournalEntry.id)
        .join(Opportunity, Opportunity.id == DecisionJournalEntry.opportunity_id)
        .filter(DecisionOutcome.status == OutcomeStatus.PENDING.value)
        .all()
    )
    updated = 0
    for entry, outcome, opp in pending:
        if opp.stage == Stage.WON:
            outcome.status = OutcomeStatus.WON.value
        elif opp.stage == Stage.LOST:
            outcome.status = OutcomeStatus.LOST.value
        else:
            continue
        outcome.actual_outcome = f"Opportunity reached {opp.stage.value}"
        outcome.days_to_outcome = (utcnow() - as_aware(entry.decided_at)).days
        outcome.recorded_at = utcnow()
        updated += 1
    db.flush()
    return updated


# ----------------------------------------------------------- reading

def journal_entries(db: Session, *, opportunity_id: str | None = None,
                    since: datetime | None = None, limit: int = 50) -> list[dict]:
    query = db.query(DecisionJournalEntry)
    if opportunity_id:
        query = query.filter(DecisionJournalEntry.opportunity_id == opportunity_id)
    if since:
        query = query.filter(DecisionJournalEntry.decided_at >= since)

    out = []
    for entry in query.order_by(DecisionJournalEntry.decided_at.desc()).limit(limit).all():
        outcome = db.query(DecisionOutcome).filter_by(entry_id=entry.id).first()
        out.append(
            {
                "id": entry.id,
                "opportunity_id": entry.opportunity_id,
                "opportunity_title": entry.opportunity_title,
                "recommended_decision": entry.recommended_decision,
                "decision": entry.decision,
                "response": entry.response,
                "agreed_with_recommendation": entry.decision == entry.recommended_decision,
                "decision_note": entry.decision_note,
                "owner": entry.owner_name,
                "decided_at": entry.decided_at.isoformat() if entry.decided_at else None,
                "turnaround_hours": entry.turnaround_hours,
                "at_decision": {
                    "focus_score": entry.focus_score_at_decision,
                    "win_probability": entry.win_probability_at_decision,
                    "risk": entry.risk_at_decision,
                    "qualification": entry.qualification_at_decision,
                },
                "expected_outcome": entry.expected_outcome,
                "outcome": {
                    "status": outcome.status if outcome else "pending",
                    "actual_outcome": outcome.actual_outcome if outcome else None,
                    "recommendation_was_correct": outcome.recommendation_was_correct if outcome else None,
                    "failed_assumption": outcome.failed_assumption if outcome else None,
                    "lessons_learned": outcome.lessons_learned if outcome else None,
                    "days_to_outcome": outcome.days_to_outcome if outcome else None,
                }
                if outcome
                else None,
                "profile_version": entry.profile_version,
            }
        )
    return out


# ------------------------------------------------------- executive KPIs

def executive_kpis(db: Session, since: datetime | None = None) -> dict:
    """KPIs that measure decision-making, not system usage.

    Deliberately excludes logins, sessions and page views. Those measure
    whether someone opened the software, which is not the objective —
    ATLAS is meant to make decisions faster and better, and these are the
    measures of that.
    """
    since = since or (utcnow() - timedelta(days=90))
    entries = (
        db.query(DecisionJournalEntry)
        .filter(DecisionJournalEntry.decided_at >= since)
        .all()
    )
    entry_ids = [e.id for e in entries]
    outcomes = (
        db.query(DecisionOutcome).filter(DecisionOutcome.entry_id.in_(entry_ids)).all()
        if entry_ids else []
    )
    by_entry = {o.entry_id: o for o in outcomes}

    pursued = sum(1 for e in entries if e.decision.startswith("pursue") or e.decision == "lead")
    declined = sum(1 for e in entries if e.decision == "decline")
    deferred = sum(1 for e in entries if e.decision == "defer")

    won = sum(1 for o in outcomes if o.status == OutcomeStatus.WON.value)
    lost = sum(1 for o in outcomes if o.status == OutcomeStatus.LOST.value)
    lapsed = sum(1 for o in outcomes if o.status == OutcomeStatus.LAPSED.value)

    accepted = sum(1 for e in entries if e.response == DecisionResponse.ACCEPTED.value)
    edited = sum(1 for e in entries if e.response == DecisionResponse.EDITED.value)
    rejected = sum(1 for e in entries if e.response == DecisionResponse.REJECTED.value)

    turnarounds = [e.turnaround_hours for e in entries if e.turnaround_hours is not None]

    # Qualification conversion: of everything assessed, how much reached a
    # state where it could actually be pursued.
    assessed = db.query(QualificationAssessment).count()
    qualified = (
        db.query(QualificationAssessment)
        .filter(QualificationAssessment.state.in_(["qualified", "conditionally_qualified"]))
        .count()
    )

    active_focus = (
        db.query(func.avg(ExecutiveFocus.score))
        .filter(ExecutiveFocus.is_actionable.is_(True))
        .scalar()
    )

    scored_outcomes = [o for o in outcomes if o.recommendation_was_correct is not None]
    correct = sum(1 for o in scored_outcomes if o.recommendation_was_correct)

    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator * 100, 1) if denominator else None

    return {
        "period_start": since.isoformat(),
        "period_end": utcnow().isoformat(),
        "decisions": {
            "total": len(entries),
            "pursued": pursued,
            "declined": declined,
            "deferred": deferred,
        },
        "outcomes": {
            "won": won,
            "lost": lost,
            "lapsed": lapsed,
            "pending": sum(1 for o in outcomes if o.status == OutcomeStatus.PENDING.value),
            "win_rate_percent": rate(won, won + lost),
        },
        "recommendation_effectiveness": {
            "acceptance_rate_percent": rate(accepted, len(entries)),
            "edit_rate_percent": rate(edited, len(entries)),
            "rejection_rate_percent": rate(rejected, len(entries)),
            "accuracy_percent": rate(correct, len(scored_outcomes)),
            "outcomes_scored": len(scored_outcomes),
            # Stated explicitly so a rate computed from four results is not
            # mistaken for a trend.
            "sample_sufficient": len(scored_outcomes) >= MIN_SAMPLE_FOR_LEARNING,
        },
        "decision_speed": {
            "mean_turnaround_hours": round(sum(turnarounds) / len(turnarounds), 1)
            if turnarounds else None,
            "decisions_with_turnaround": len(turnarounds),
        },
        "pipeline_quality": {
            "qualification_conversion_percent": rate(qualified, assessed),
            "assessed": assessed,
            "qualified": qualified,
            "mean_focus_of_active_pursuits": round(active_focus, 1) if active_focus else None,
        },
        "adoption": _adoption_metrics(db, since),
        "executive_feedback": _feedback_metrics(entries),
        # Deliberately absent: session length, click paths, time-in-app.
        # Briefing opens are counted because "is this worth opening every
        # morning" is the product's central question; how long someone
        # stares at a screen is not.
        "excluded_by_design": ["session_length", "click_paths", "time_in_app"],
    }


def _feedback_metrics(entries: list) -> dict:
    """The subjective half of the pilot.

    `independent_value_rate` is the one to watch. A recommendation the
    executive would have reached unaided is agreement without value — a
    platform scoring 90% acceptance on advice its user already knew has
    measured its own redundancy, not its usefulness.
    """
    useful = [e.usefulness_rating for e in entries if e.usefulness_rating is not None]
    trust = [e.confidence_rating for e in entries if e.confidence_rating is not None]
    alone = [e.would_have_reached_alone for e in entries
             if e.would_have_reached_alone is not None]
    friction = [e.friction_note for e in entries if e.friction_note]

    if not useful and not trust and not alone:
        return {
            "rated_decisions": 0,
            "note": "No feedback captured — subjective measures unavailable",
        }

    independent = sum(1 for a in alone if not a)
    return {
        "rated_decisions": len(useful),
        "mean_usefulness": round(sum(useful) / len(useful), 1) if useful else None,
        "mean_confidence": round(sum(trust) / len(trust), 1) if trust else None,
        "independent_value_rate": (
            round(independent / len(alone) * 100, 1) if alone else None
        ),
        "friction_reports": len(friction),
        "friction_notes": friction[:10],
        "note": (
            "ATLAS is surfacing conclusions the owner would not have reached alone"
            if alone and independent / len(alone) >= 0.4
            else "Most recommendations confirm what the owner already knew — "
                 "useful reassurance, but limited independent value"
        ),
    }


def _adoption_metrics(db: Session, since: datetime) -> dict:
    """Is the briefing actually being opened?

    The V1.0 exit review named this the metric that matters, because every
    other measure can be satisfied by a platform nobody uses.
    """
    from ..models_journal import BriefingView

    views = (
        db.query(BriefingView)
        .filter(BriefingView.viewed_at >= since)
        .order_by(BriefingView.viewed_at.asc())
        .all()
    )
    if not views:
        return {
            "briefing_opens": 0,
            "distinct_days": 0,
            "working_day_coverage_percent": None,
            "note": "No briefing opens recorded — adoption cannot be assessed",
        }

    days = {v.view_date for v in views}

    # Working days elapsed in the period, so weekends do not depress the rate.
    start, end = since.date(), date.today()
    working_days = sum(
        1 for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    )
    with_content = [v for v in views if not v.was_complete]
    gen_times = [v.generation_ms for v in views if v.generation_ms is not None]

    return {
        "briefing_opens": len(views),
        "distinct_days": len(days),
        "working_days_in_period": working_days,
        "working_day_coverage_percent": (
            round(len(days) / working_days * 100, 1) if working_days else None
        ),
        "opens_with_something_to_report": len(with_content),
        "mean_generation_ms": (
            round(sum(gen_times) / len(gen_times)) if gen_times else None
        ),
        "exceeded_budget_count": sum(1 for t in gen_times if t > 1500),
        "note": (
            "Opened on most working days — the briefing is part of the routine"
            if working_days and len(days) / working_days >= 0.8
            else "Opened irregularly — the briefing has not become habitual"
        ),
    }


# --------------------------------------------------------- learning loop

def compute_accuracy(db: Session, period_days: int = 180,
                     decision_type: str | None = None) -> RecommendationAccuracy:
    """Compares recommendation → decision → outcome and records the signal.

    Confidence is adjusted only above `MIN_SAMPLE_FOR_LEARNING` and never
    by more than `MAX_CONFIDENCE_ADJUSTMENT`. A loop that swings on a
    handful of results would amplify noise while carrying the authority of
    having learned something — worse than not learning at all.
    """
    end = utcnow().date()
    start = end - timedelta(days=period_days)

    query = (
        db.query(DecisionJournalEntry, DecisionOutcome)
        .join(DecisionOutcome, DecisionOutcome.entry_id == DecisionJournalEntry.id)
        .filter(DecisionJournalEntry.decided_at >= datetime.combine(start, datetime.min.time()))
    )
    if decision_type:
        query = query.filter(DecisionJournalEntry.recommended_decision == decision_type)
    rows = query.all()

    total = len(rows)
    scored = [(e, o) for e, o in rows if o.recommendation_was_correct is not None]
    correct = sum(1 for _, o in scored if o.recommendation_was_correct)
    incorrect = len(scored) - correct

    accepted = sum(1 for e, _ in rows if e.response == DecisionResponse.ACCEPTED.value)
    edited = sum(1 for e, _ in rows if e.response == DecisionResponse.EDITED.value)
    turnarounds = [e.turnaround_hours for e, _ in rows if e.turnaround_hours is not None]

    accuracy = (correct / len(scored)) if scored else None

    # Name the recurring failure, where one exists. This is the actual
    # input to improving recommendations — a percentage tells you there is
    # a problem, a pattern tells you what it is.
    failures = [o.failed_assumption for _, o in scored
                if o.recommendation_was_correct is False and o.failed_assumption]
    pattern = None
    if len(failures) >= 3:
        counts: dict[str, int] = {}
        for f in failures:
            key = f.strip().lower()[:60]
            counts[key] = counts.get(key, 0) + 1
        top, count = max(counts.items(), key=lambda kv: kv[1])
        if count >= 2:
            pattern = f"Recurring failed assumption ({count} occurrences): {top}"

    adjustment = None
    if accuracy is not None and len(scored) >= MIN_SAMPLE_FOR_LEARNING:
        raw = accuracy - 0.7        # 70% baseline expectation
        adjustment = max(-MAX_CONFIDENCE_ADJUSTMENT, min(MAX_CONFIDENCE_ADJUSTMENT, raw))

    record = RecommendationAccuracy(
        period_start=start,
        period_end=end,
        decision_type=decision_type,
        total_decisions=total,
        outcomes_recorded=len(scored),
        correct=correct,
        incorrect=incorrect,
        accuracy_rate=round(accuracy, 3) if accuracy is not None else None,
        acceptance_rate=round(accepted / total, 3) if total else None,
        edit_rate=round(edited / total, 3) if total else None,
        mean_turnaround_hours=round(sum(turnarounds) / len(turnarounds), 2) if turnarounds else None,
        common_failure_pattern=pattern,
        confidence_adjustment=adjustment,
    )
    db.add(record)
    db.flush()
    return record


def learning_summary(db: Session) -> dict:
    """What the loop has learned, and whether it is yet entitled to say so."""
    latest = (
        db.query(RecommendationAccuracy)
        .filter(RecommendationAccuracy.decision_type.is_(None))
        .order_by(RecommendationAccuracy.computed_at.desc())
        .first()
    )
    if latest is None:
        return {
            "available": False,
            "reason": "No accuracy has been computed yet.",
            "sample_size": 0,
        }

    sufficient = latest.outcomes_recorded >= MIN_SAMPLE_FOR_LEARNING
    return {
        "available": True,
        "sample_size": latest.outcomes_recorded,
        "sample_sufficient": sufficient,
        "accuracy_percent": round(latest.accuracy_rate * 100, 1) if latest.accuracy_rate else None,
        "acceptance_rate_percent": round(latest.acceptance_rate * 100, 1) if latest.acceptance_rate else None,
        "edit_rate_percent": round(latest.edit_rate * 100, 1) if latest.edit_rate else None,
        "common_failure_pattern": latest.common_failure_pattern,
        "confidence_adjustment": latest.confidence_adjustment if sufficient else None,
        "note": (
            "Confidence is being adjusted based on outcome evidence."
            if sufficient
            else f"Reporting only — {MIN_SAMPLE_FOR_LEARNING} scored outcomes needed before "
                 "confidence is adjusted. Adjusting on a smaller sample would amplify noise."
        ),
        "computed_at": latest.computed_at.isoformat() if latest.computed_at else None,
    }

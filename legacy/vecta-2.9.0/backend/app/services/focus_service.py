"""Executive Focus computation — Phase 3.1.

Gathers the eight Focus Score inputs from stored data and persists the
result, so the Briefing can sort by it without recomputing on every
request. The Briefing has a 1.5-second budget; recomputing focus for a
hundred opportunities inside that budget is not realistic.

**No AI calls.** Every input is already in the database.
"""
from __future__ import annotations

import logging

import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import focus_score as engine
from ..models import Contact, Opportunity
from ..models_memory import ChangeEvent, ChangeEventType, ExecutiveFocus, Materiality
from ..models_phase2 import (
    CommercialValue,
    OpportunityEvidence,
    PursuitPriority,
    QualificationAssessment,
    QualificationBlocker,
    QualificationChecklistItem,
    ScoreAssessment,
)
from ..timeutils import as_aware, utcnow
from . import profile_service

logger = logging.getLogger("atlas.focus")


# Stages at which the outcome is out of VECTA's hands. Focus is suppressed
# here — however attractive the opportunity, attention this week changes
# nothing.
NON_ACTIONABLE_STAGES = {"submitted", "evaluation", "won", "lost"}


def _score_map(db: Session, opportunity_id: str) -> dict[str, ScoreAssessment]:
    return {
        s.dimension: s
        for s in db.query(ScoreAssessment).filter_by(opportunity_id=opportunity_id).all()
    }


def _actionability(db: Session, opp: Opportunity,
                   qualification: QualificationAssessment | None) -> tuple[bool, str | None]:
    """Can executive attention still change the outcome?

    This is the single most important judgement in the Focus Score. Get it
    wrong in one direction and the dashboard fills with work already done;
    wrong in the other and genuinely urgent items are hidden.
    """
    stage = opp.stage.value if opp.stage else None
    if stage in NON_ACTIONABLE_STAGES:
        return False, f"Stage '{stage}' — outcome no longer influenced by executive action"

    if qualification and qualification.state == "disqualified":
        return False, "Disqualified — attention cannot change the outcome"

    if opp.deadline and opp.deadline < date.today():
        return False, f"Deadline passed ({opp.deadline.isoformat()})"

    if opp.classification in ("market_signal", "intelligence_watch"):
        return False, f"{(opp.classification or '').replace('_',' ').title()} — not an actionable opportunity"

    return True, None


def compute_for_opportunity(db: Session, opp: Opportunity) -> dict:
    """Assembles the eight components from stored data."""
    scores = _score_map(db, opp.id)
    qualification = (
        db.query(QualificationAssessment).filter_by(opportunity_id=opp.id).first()
    )
    value = db.query(CommercialValue).filter_by(opportunity_id=opp.id).first()
    evidence = db.query(OpportunityEvidence).filter_by(opportunity_id=opp.id).all()

    profile = profile_service.get_active_profile(db)
    min_viable = profile.min_viable_contract_value if profile else None
    target = profile.target_contract_value if profile else None

    # --- qualification detail -------------------------------------------
    unanswered = 0
    remediable = 0
    if qualification:
        unanswered = (
            db.query(QualificationChecklistItem)
            .filter_by(assessment_id=qualification.id, answer="unknown", is_mandatory=True)
            .count()
        )
        remediable = (
            db.query(QualificationBlocker)
            .filter_by(assessment_id=qualification.id, failure_type="remediable_blocker",
                       is_resolved=False)
            .count()
        )

    # --- relationships ---------------------------------------------------
    # Phase 3.1 reads what exists today. The full stakeholder model lands
    # in 3.2; this is the extension point, and it degrades honestly rather
    # than pretending the data is present.
    contacts = db.query(Contact).filter_by(opportunity_id=opp.id).all()
    has_decision_maker = any(
        (c.role or "").lower().find(kw) >= 0
        for c in contacts
        for kw in ("director", "minister", "head", "chief", "secretary general")
    )
    has_procurement = any((c.role or "").lower().find("procure") >= 0 for c in contacts)
    strongest = max((c.relevance_score or 0 for c in contacts), default=None)
    days_since_engagement = None
    if opp.updated_at:
        days_since_engagement = (utcnow() - as_aware(opp.updated_at)).days

    # --- capacity --------------------------------------------------------
    capacity = profile_service.capacity_status(db)
    scarce = profile_service.scarce_capabilities(db)
    uses_scarce = bool(scarce) and any(
        s.lower() in (opp.title or "").lower() or s.lower() in (opp.summary or "").lower()
        for s in scarce
    )

    # --- evidence --------------------------------------------------------
    tier_1 = sum(1 for e in evidence if e.source_tier == "tier_1")
    validated = sum(1 for e in evidence if e.url_validation_status in ("valid", "archived"))

    # --- monetary value --------------------------------------------------
    monetary = None
    if value:
        monetary = (
            value.published_contract_value
            or value.estimated_vecta_revenue
            or (
                (value.estimated_contract_min + value.estimated_contract_max) / 2
                if value.estimated_contract_min and value.estimated_contract_max
                else None
            )
        )

    strategic = scores.get("strategic_alignment")
    win = scores.get("win_probability")

    components = {
        "strategic_alignment": {
            "score": strategic.score if strategic else 0,
            "note": f"Strategic alignment {strategic.score}" if strategic else "Not scored",
        },
        "commercial_value": engine.commercial_value_component(monetary, min_viable, target),
        "win_probability": {
            "score": win.score if win else 0,
            "note": f"Win probability {win.score}" if win else "Not scored",
        },
        "urgency": engine.urgency_component(opp.deadline),
        "relationship_readiness": engine.relationship_readiness_component(
            has_decision_maker=has_decision_maker,
            has_procurement=has_procurement,
            strongest_relationship=strongest,
            introduction_available=False,   # 3.2 supplies this
            days_since_engagement=days_since_engagement,
        ),
        "qualification": engine.qualification_component(
            qualification.state if qualification else None,
            unanswered_mandatory=unanswered,
            remediable_blockers=remediable,
        ),
        "evidence_quality": engine.evidence_quality_component(
            tier_1_count=tier_1,
            validated_count=validated,
            total_evidence=len(evidence),
            requires_review=bool(opp.requires_human_review),
        ),
        "delivery_capacity": engine.delivery_capacity_component(
            capacity_strained=capacity.get("strained", False),
            uses_scarce_capability=uses_scarce,
            competing_pursuits=0,           # 3.4 supplies this
        ),
    }

    actionable, suppression = _actionability(db, opp, qualification)
    return engine.compute_focus_score(
        components, is_actionable=actionable, suppression_reason=suppression
    )


def persist_focus(db: Session, opp: Opportunity, result: dict) -> ExecutiveFocus:
    """Stores the score and records a change event if it moved materially."""
    existing = db.query(ExecutiveFocus).filter_by(opportunity_id=opp.id).first()
    previous = existing.score if existing else None
    delta = (result["score"] - previous) if previous is not None else None

    if existing:
        db.delete(existing)
        db.flush()

    row = ExecutiveFocus(
        opportunity_id=opp.id,
        score=result["score"],
        raw_score=result["raw_score"],
        band=result["band"],
        band_label=result["band_label"],
        is_actionable=result["is_actionable"],
        suppression_reason=result["suppression_reason"],
        primary_drivers=", ".join(result["primary_drivers"]),
        explanation=engine.explain(result),
        contributions_json=json.dumps(result["contributions"]),
        previous_score=previous,
        delta=delta,
        profile_version=profile_service.active_version(db),
        model_version=result["model_version"],
    )
    db.add(row)
    db.flush()

    if delta is not None and abs(delta) >= 15:
        from .change_detector import record

        record(
            db,
            subject_type="opportunity",
            opportunity_id=opp.id,
            event_type=ChangeEventType.FOCUS_CHANGED.value,
            materiality=Materiality.HIGH.value if abs(delta) >= 25 else Materiality.MEDIUM.value,
            summary=f"Focus {'rose' if delta > 0 else 'fell'} {abs(delta)} points — {result['band_label']}",
            detail=row.explanation,
            previous_value=str(previous),
            new_value=str(result["score"]),
            delta=float(delta),
        )
    return row


def recompute_all(db: Session, limit: int | None = None) -> dict:
    """Recomputes focus across the pipeline.

    Called after a scan, a profile change, or on a scheduled basis. Not on
    every page load — the Briefing reads the stored value.
    """
    query = db.query(Opportunity)
    if limit:
        query = query.limit(limit)

    computed = 0
    actionable = 0
    for opp in query.all():
        result = compute_for_opportunity(db, opp)
        persist_focus(db, opp, result)
        computed += 1
        if result["is_actionable"]:
            actionable += 1
    db.flush()
    return {"computed": computed, "actionable": actionable,
            "suppressed": computed - actionable}


def top_focus(db: Session, limit: int = 5) -> list[tuple[Opportunity, ExecutiveFocus]]:
    """The Briefing's "today's priorities". Suppressed items are excluded
    entirely — an opportunity awaiting evaluation should not occupy a slot
    in a list of five."""
    rows = (
        db.query(Opportunity, ExecutiveFocus)
        .join(ExecutiveFocus, ExecutiveFocus.opportunity_id == Opportunity.id)
        .filter(ExecutiveFocus.is_actionable.is_(True))
        .order_by(ExecutiveFocus.score.desc())
        .limit(limit)
        .all()
    )
    return rows

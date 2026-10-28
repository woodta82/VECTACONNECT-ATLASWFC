from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Opportunity, OpportunityActivity, Organisation, Stage
from ..schemas import BulkStageUpdate, OpportunityActivityOut, OpportunityOut, OpportunityOwnerUpdate, OpportunityStageUpdate
from ..timeutils import utcnow_naive

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _enrich(db: Session, opps: list[Opportunity]) -> list[Opportunity]:
    org_ids = {o.organisation_id for o in opps if o.organisation_id}
    orgs = {o.id: o.name for o in db.scalars(select(Organisation).where(Organisation.id.in_(org_ids)))} if org_ids else {}
    for o in opps:
        o.organisation_name = orgs.get(o.organisation_id)
    return opps


def _log_stage_change(db: Session, opportunity_id: str, old_stage: str, new_stage: str, reason: str | None) -> None:
    detail = f"Stage changed from {old_stage} to {new_stage}"
    if reason:
        detail += f" — {reason}"
    db.add(OpportunityActivity(opportunity_id=opportunity_id, event_type="stage_change", detail=detail))


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    q: str | None = None,
    stage: str | None = None,
    vertical: str | None = None,
    region: str | None = None,
    priority_only: bool = False,
    sort: str = "score",
    days_back: int | None = None,
    db: Session = Depends(get_db),
):
    """`sort=score` (default) orders by VECTA Alignment Score, highest
    first — used for the Priority Opportunities view. `sort=recent` orders
    by date submitted, newest first — used for the Latest Opportunities
    view. `days_back` restricts to opportunities discovered within that
    many days (e.g. 7 for a rolling weekly window)."""
    query = select(Opportunity)
    if sort == "recent":
        query = query.order_by(Opportunity.created_at.desc())
    else:
        query = query.order_by(Opportunity.alignment_score.desc(), Opportunity.created_at.desc())
    if q:
        like = f"%{q.strip()}%"
        query = query.where((Opportunity.title.ilike(like)) | (Opportunity.summary.ilike(like)))
    if stage:
        query = query.where(Opportunity.stage == stage)
    if vertical:
        query = query.where(Opportunity.vertical == vertical)
    if region:
        query = query.where(Opportunity.region == region)
    if priority_only:
        query = query.where(Opportunity.priority.is_(True))
    if days_back is not None:
        cutoff = utcnow_naive() - timedelta(days=days_back)
        query = query.where(Opportunity.created_at >= cutoff)
    opps = db.scalars(query).all()
    return _enrich(db, list(opps))


@router.patch("/bulk/stage", response_model=list[OpportunityOut])
def bulk_update_stage(body: BulkStageUpdate, db: Session = Depends(get_db)):
    """Move multiple opportunities to the same stage in one call — powers
    the Opportunities table's bulk-select action bar. Registered before
    the single-opportunity `/{opportunity_id}/stage` route so the literal
    path `bulk/stage` doesn't get swallowed by that dynamic route."""
    opps = db.scalars(select(Opportunity).where(Opportunity.id.in_(body.opportunity_ids))).all()
    for opp in opps:
        if opp.stage != body.stage:
            _log_stage_change(db, opp.id, opp.stage.value, body.stage, None)
            opp.stage = body.stage
    db.commit()
    return _enrich(db, list(opps))


@router.get("/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    return _enrich(db, [opp])[0]


@router.get("/{opportunity_id}/activity", response_model=list[OpportunityActivityOut])
def get_activity(opportunity_id: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(OpportunityActivity)
        .where(OpportunityActivity.opportunity_id == opportunity_id)
        .order_by(OpportunityActivity.created_at.desc())
    ).all()


@router.get("/{opportunity_id}/similar", response_model=list[OpportunityOut])
def get_similar(opportunity_id: str, db: Session = Depends(get_db)):
    """Related opportunities — same organisation first (the strongest
    signal: literally the same counterpart), then same vertical + region
    as a fallback. Helps spot near-duplicates (e.g. several F1 Abu Dhabi
    hospitality tenders) that would otherwise double-count as separate
    pipeline value when they're really the same relationship."""
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "Opportunity not found")

    results: list[Opportunity] = []
    seen_ids = {opp.id}

    if opp.organisation_id:
        same_org = db.scalars(
            select(Opportunity)
            .where(Opportunity.organisation_id == opp.organisation_id, Opportunity.id != opp.id)
            .order_by(Opportunity.alignment_score.desc())
            .limit(5)
        ).all()
        for o in same_org:
            if o.id not in seen_ids:
                results.append(o)
                seen_ids.add(o.id)

    if len(results) < 5 and opp.vertical and opp.region:
        same_segment = db.scalars(
            select(Opportunity)
            .where(
                Opportunity.vertical == opp.vertical,
                Opportunity.region == opp.region,
                Opportunity.id != opp.id,
            )
            .order_by(Opportunity.alignment_score.desc())
            .limit(5)
        ).all()
        for o in same_segment:
            if o.id not in seen_ids and len(results) < 5:
                results.append(o)
                seen_ids.add(o.id)

    return _enrich(db, results)


@router.patch("/{opportunity_id}/stage", response_model=OpportunityOut)
def update_stage(opportunity_id: str, body: OpportunityStageUpdate, db: Session = Depends(get_db)):
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    if opp.stage != body.stage:
        _log_stage_change(db, opp.id, opp.stage.value, body.stage, body.outcome_reason)
        opp.stage = body.stage
    if body.stage in (Stage.WON.value, Stage.LOST.value) and body.outcome_reason:
        opp.outcome_reason = body.outcome_reason
    db.commit()
    return opp


@router.patch("/{opportunity_id}/owner", response_model=OpportunityOut)
def update_owner(opportunity_id: str, body: OpportunityOwnerUpdate, db: Session = Depends(get_db)):
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    opp.owner_id = body.owner_id
    db.commit()
    return opp


# ---------------------------------------------------------- Phase 2 (v2.9)

@router.get("/{opportunity_id}/phase2")
def get_opportunity_phase2(opportunity_id: str, db: Session = Depends(get_db)):
    """Full Phase 2 model for the detail page.

    Returned as a plain dict rather than a Pydantic response_model: the
    payload is assembled by the serializer, which is the single place that
    decides display labels and safety flags. Re-declaring that shape as a
    response model would create a second definition to keep in sync, and
    the failure mode is a silently dropped field.
    """
    from ..services.opportunity_serializer import serialise_opportunity

    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    return serialise_opportunity(db, opp, include_detail=True)


@router.get("/phase2/list")
def list_opportunities_phase2(
    classification: str | None = None,
    primary_vertical: str | None = None,
    qualification_state: str | None = None,
    priority_band: str | None = None,
    requires_human_review: bool | None = None,
    risk_established: bool | None = None,
    min_pursuit_priority: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Card-shaped Phase 2 records for the list page, with the material
    filters. Sorted by Pursuit Priority so the most actionable work is
    first — but note that a restricted (unqualified or low-coverage)
    opportunity is capped before it gets here, so it cannot sort above
    genuinely qualified work."""
    from ..models_phase2 import PursuitPriority, QualificationAssessment, ScoreAssessment
    from ..services.opportunity_serializer import serialise_opportunity

    query = db.query(Opportunity)
    if classification:
        query = query.filter(Opportunity.classification == classification)
    if primary_vertical:
        query = query.filter(Opportunity.primary_vertical == primary_vertical)
    if requires_human_review is not None:
        query = query.filter(Opportunity.requires_human_review == requires_human_review)
    if qualification_state:
        query = query.join(
            QualificationAssessment, QualificationAssessment.opportunity_id == Opportunity.id
        ).filter(QualificationAssessment.state == qualification_state)
    if priority_band or min_pursuit_priority is not None:
        query = query.join(PursuitPriority, PursuitPriority.opportunity_id == Opportunity.id)
        if priority_band:
            query = query.filter(PursuitPriority.band == priority_band)
        if min_pursuit_priority is not None:
            query = query.filter(PursuitPriority.final_score >= min_pursuit_priority)
    if risk_established is not None:
        query = query.join(
            ScoreAssessment,
            (ScoreAssessment.opportunity_id == Opportunity.id) & (ScoreAssessment.dimension == "risk"),
        ).filter(ScoreAssessment.risk_established == risk_established)

    rows = query.limit(limit).all()
    payloads = [serialise_opportunity(db, o, include_detail=False) for o in rows]
    payloads.sort(
        key=lambda p: (p.get("pursuit_priority") or {}).get("final_score", -1), reverse=True
    )
    return payloads


# ------------------------------------------- qualification workflow (v2.9)

class QualificationAnswerIn(BaseModel):
    answer: str  # yes | no | unknown | not_applicable
    explanation: str | None = None
    evidence_id: str | None = None


class QualificationAnswersIn(BaseModel):
    answers: dict[str, QualificationAnswerIn]


class QualificationOverrideIn(BaseModel):
    new_state: str
    reason: str
    note: str | None = None


@router.get("/{opportunity_id}/qualification")
def get_qualification(opportunity_id: str, db: Session = Depends(get_db)):
    """Current assessment plus the concrete next actions. The actions are
    the difference between a gate and a dead end."""
    from ..services import opportunity_service as service
    from ..services.opportunity_serializer import _serialise_qualification

    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "Opportunity not found")

    qualification = _serialise_qualification(db, opportunity_id)
    allowed, block_reason = True, None
    try:
        service.assert_can_enter_active_pipeline(db, opp)
    except service.ServiceRuleViolation as exc:
        allowed, block_reason = False, "; ".join(exc.failures) or str(exc)

    return {
        "qualification": qualification,
        "next_actions": service.qualification_next_actions(db, opportunity_id),
        "can_enter_pipeline": allowed,
        "pipeline_block_reason": block_reason,
    }


@router.patch("/{opportunity_id}/qualification")
def answer_qualification(
    opportunity_id: str, body: QualificationAnswersIn, db: Session = Depends(get_db)
):
    """Records answers and re-evaluates the gate immediately, so the owner
    sees the consequence of an answer rather than having to trigger a
    separate recalculation."""
    from ..services import opportunity_service as service
    from ..services.opportunity_serializer import _serialise_qualification

    try:
        service.answer_qualification_items(
            db, opportunity_id, {k: v.model_dump() for k, v in body.answers.items()}
        )
        db.commit()
    except service.ServiceRuleViolation as exc:
        db.rollback()
        raise HTTPException(400, {"message": str(exc), "failures": exc.failures})

    opp = db.get(Opportunity, opportunity_id)
    allowed, block_reason = True, None
    try:
        service.assert_can_enter_active_pipeline(db, opp)
    except service.ServiceRuleViolation as exc:
        allowed, block_reason = False, "; ".join(exc.failures) or str(exc)

    return {
        "qualification": _serialise_qualification(db, opportunity_id),
        "next_actions": service.qualification_next_actions(db, opportunity_id),
        "can_enter_pipeline": allowed,
        "pipeline_block_reason": block_reason,
    }


@router.post("/{opportunity_id}/qualification/override")
def override_qualification(
    opportunity_id: str, body: QualificationOverrideIn, db: Session = Depends(get_db)
):
    """Explicit owner override. The computed state is preserved as
    `previous_state` on the override row, so the original assessment stays
    auditable — an override records a disagreement, it does not erase what
    the gate concluded."""
    from ..services import opportunity_service as service
    from ..services.opportunity_serializer import _serialise_qualification

    try:
        service.override_qualification_state(
            db, opportunity_id, new_state=body.new_state, reason=body.reason, note=body.note
        )
        service._recalculate_priority(db, opportunity_id, body.new_state)
        db.commit()
    except (service.ServiceRuleViolation, ValueError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc))

    return {"qualification": _serialise_qualification(db, opportunity_id)}

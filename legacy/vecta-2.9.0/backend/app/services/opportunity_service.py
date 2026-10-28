"""Opportunity service layer — the single write path for Phase 2.

This is the module that makes the Phase 2 engines *live*. Everything that
creates or changes an opportunity goes through here: the scanner, the API,
and manual editing. `scoring_v2`, `qualification`, `evidence` and
`taxonomy` are all imported and executed on this path, so the rules cannot
be bypassed by writing to the ORM directly from a router.

Enforcement happens here rather than in the frontend or the AI prompt
because both can be bypassed — a prompt can be ignored by the model, and
a frontend can be sidestepped by anyone calling the API. The rules
enforced (spec §6):

  1. No Confirmed Opportunity without qualifying evidence
  2. No active-pipeline entry without an acceptable qualification state
  3. No expired opportunity entering the active pipeline
  4. No high priority bypassing insufficient score coverage
  5. No low Risk display when risk coverage is insufficient
  6. No estimated value presented as published
  7. No manual override without a reason
  8. No deletion of original AI values on override
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from .. import evidence as evidence_engine
from .. import qualification as qualification_engine
from .. import scoring_v2 as scoring_engine
from ..models import Opportunity
from ..models_phase2 import (
    AIParseFailure,
    AnalysisItemType,
    CommercialValue,
    EvidenceClaim,
    LegacyOpportunityData,
    OpportunityAnalysisItem,
    OpportunityContributingVertical,
    OpportunityEvidence,
    OpportunityRouteToMarket,
    OpportunitySecondaryCommercialType,
    OverrideAudit,
    PursuitPriority,
    QualificationAssessment,
    QualificationBlocker,
    QualificationChecklistItem,
    QualificationOverride,
    ScoreAssessment,
    ScoreFactor,
)
from ..taxonomy import (
    ACTIVE_PIPELINE_STATES,
    ESTIMATED_VALUE_STATUSES,
    QUALIFICATION_ITEMS,
    GateAnswer,
    OpportunityClassification,
    QualificationState,
)
from ..timeutils import utcnow

MIGRATION_VERSION = "2.9.0"


class ServiceRuleViolation(Exception):
    """Raised when a write would break a Phase 2 rule. Carries the specific
    failures so the API can return them rather than a generic 400."""

    def __init__(self, message: str, failures: list[str] | None = None) -> None:
        super().__init__(message)
        self.failures = failures or []


# ------------------------------------------------------------ evidence

def persist_evidence(db: Session, opportunity_id: str, records: list[dict], is_manual: bool = False) -> list[OpportunityEvidence]:
    """Writes evidence rows and their claim links. Claims are validated by
    the evidence engine first — a record supporting nothing is rejected
    rather than stored as a bare link."""
    created: list[OpportunityEvidence] = []
    for r in records:
        built = evidence_engine.new_evidence(
            url=r["url"],
            source_tier=r["source_tier"],
            claims_supported=r.get("claims_supported") or [],
            page_title=r.get("page_title"),
            publisher=r.get("publisher"),
            publication_date=r.get("publication_date"),
            no_publication_date_reason=r.get("no_publication_date_reason"),
            evidence_type=r.get("evidence_type", "other"),
            is_official_source=bool(r.get("is_official_source")),
            is_definitive=bool(r.get("is_definitive")),
            url_validation_status=r.get("url_validation_status", "not_reviewed"),
            confidence=r.get("confidence", "medium"),
            notes=r.get("notes"),
        )
        row = OpportunityEvidence(
            opportunity_id=opportunity_id,
            url=built["url"],
            page_title=built["page_title"],
            publisher=built["publisher"],
            source_tier=built["source_tier"],
            evidence_type=built["evidence_type"],
            publication_date=_parse_date(built["publication_date"]),
            no_publication_date_reason=built["no_publication_date_reason"],
            url_validation_status=built["url_validation_status"],
            last_validated_at=utcnow() if built["last_validated_at"] else None,
            is_official_source=built["is_official_source"],
            is_definitive=built["is_definitive"],
            confidence=built["confidence"],
            notes=built["notes"],
            is_manual=is_manual,
        )
        db.add(row)
        db.flush()
        for claim in built["claims_supported"]:
            db.add(EvidenceClaim(evidence_id=row.id, claim_type=claim))
        created.append(row)
    db.flush()
    return created


def evidence_as_dicts(db: Session, opportunity_id: str) -> list[dict]:
    """Shapes stored evidence into the form the evidence engine expects,
    so validation reads from the database rather than from whatever the
    caller happened to pass in."""
    rows = db.query(OpportunityEvidence).filter_by(opportunity_id=opportunity_id).all()
    out = []
    for r in rows:
        claims = [c.claim_type for c in db.query(EvidenceClaim).filter_by(evidence_id=r.id).all()]
        out.append(
            {
                "url": r.url,
                "source_tier": r.source_tier,
                "claims_supported": claims,
                "publication_date": r.publication_date.isoformat() if r.publication_date else None,
                "no_publication_date_reason": r.no_publication_date_reason,
                "url_validation_status": r.url_validation_status,
                "is_official_source": r.is_official_source,
                "is_definitive": r.is_definitive,
                "confidence": r.confidence,
            }
        )
    return out


# ------------------------------------------------------------- scoring

def persist_scores(db: Session, opportunity_id: str, factor_scores_by_dimension: dict[str, dict],
                   rationales: dict[str, dict] | None = None,
                   confidences: dict[str, str] | None = None) -> dict[str, dict]:
    """Runs the scoring engine for each dimension and stores the headline,
    coverage and every factor row. Returns the computed dimensions so the
    caller can feed them into pursuit priority without recomputing."""
    rationales = rationales or {}
    confidences = confidences or {}
    computed: dict[str, dict] = {}

    for dimension in scoring_engine.DIMENSIONS:
        factor_scores = factor_scores_by_dimension.get(dimension, {})
        result = scoring_engine.compute_dimension(dimension, factor_scores)
        computed[dimension] = result

        db.query(ScoreAssessment).filter_by(
            opportunity_id=opportunity_id, dimension=dimension
        ).delete()
        db.flush()

        assessment = ScoreAssessment(
            opportunity_id=opportunity_id,
            dimension=dimension,
            score=result["score"],
            coverage=result["coverage"],
            coverage_percent=result["coverage_percent"],
            coverage_band=result["coverage_status"],
            risk_established=result.get("risk_established") if dimension == "risk" else None,
            confidence=confidences.get(dimension),
            rationale=(rationales.get(dimension) or {}).get("_dimension"),
            ai_score=result["score"],
            model_version=result["model_version"],
            last_scored_at=utcnow(),
        )
        db.add(assessment)
        db.flush()

        for f in result["factors"]:
            db.add(
                ScoreFactor(
                    assessment_id=assessment.id,
                    factor_key=f["key"],
                    factor_label=f["label"],
                    weight=f["weight"],
                    score=f["score"],
                    scored=f["scored"],
                    rationale=(rationales.get(dimension) or {}).get(f["key"]),
                )
            )
    db.flush()
    return computed


def persist_pursuit_priority(db: Session, opportunity_id: str, computed: dict[str, dict],
                             qualification_state: str, urgency_adjustment: float = 0.0) -> dict:
    """Calculates and stores Pursuit Priority, passing coverage and the
    risk-established flag so both restrictions (§6.4 and §6.5) are applied
    at the point the number is produced — not bolted on at display time."""
    coverage = {d: r["coverage"] for d, r in computed.items()}
    stored_risk_flag = computed.get("risk", {}).get("risk_established")
    risk_established = True if stored_risk_flag is None else bool(stored_risk_flag)

    # Phase 3.1: the Commercial Profile supplies the weighting. Falls back
    # to DEFAULT_PRIORITY_WEIGHTS when no profile exists or it has none —
    # generic-but-documented beats confident-but-arbitrary.
    from . import profile_service

    weights = profile_service.priority_weights(db)
    version = profile_service.active_version(db)

    result = scoring_engine.compute_pursuit_priority(
        strategic_alignment=computed["strategic_alignment"]["score"],
        commercial_attractiveness=computed["commercial_attractiveness"]["score"],
        win_probability=computed["win_probability"]["score"],
        risk=computed["risk"]["score"],
        qualification_state=qualification_state,
        urgency_adjustment=urgency_adjustment,
        coverage=coverage,
        risk_established=risk_established,
        weights=weights,
    )

    db.query(PursuitPriority).filter_by(opportunity_id=opportunity_id).delete()
    db.flush()
    db.add(
        PursuitPriority(
            opportunity_id=opportunity_id,
            base_score=result["base_score"],
            inverse_risk=next(
                (c["value"] for c in result["contributions"] if c["component"] == "inverse_risk"), 0.0
            ),
            urgency_adjustment=result["urgency_adjustment"],
            uncapped_score=result["uncapped_score"],
            final_score=result["score"],
            band=result["band"],
            band_label=result["band_label"],
            coverage_restricted=result.get("coverage_restricted", False),
            qualification_restricted=result.get("qualification_restricted", False),
            restriction_explanation=" ".join(result.get("restrictions") or []) or None,
            weights_used=result["weights"],
            model_version=result["model_version"],
            profile_version=version,
            calculated_at=utcnow(),
        )
    )
    # Scores were just computed under this profile, so they are current.
    db.query(ScoreAssessment).filter_by(opportunity_id=opportunity_id).update(
        {ScoreAssessment.profile_version: version, ScoreAssessment.is_stale: False},
        synchronize_session=False,
    )
    db.flush()
    return result


# ------------------------------------------------------- qualification

def persist_qualification(db: Session, opportunity_id: str, answers: dict[str, dict],
                          classification: str | None, deadline: date | None,
                          has_credible_source: bool = True) -> dict:
    """Runs the qualification engine and stores the assessment, every
    checklist answer and every typed blocker."""
    deadline_passed = bool(deadline and deadline < date.today())
    result = qualification_engine.evaluate_qualification(
        items=answers,
        classification=classification,
        deadline_passed=deadline_passed,
        has_credible_source=has_credible_source,
    )

    db.query(QualificationAssessment).filter_by(opportunity_id=opportunity_id).delete()
    db.flush()

    assessment = QualificationAssessment(
        opportunity_id=opportunity_id,
        state=result["state"],
        has_absolute_disqualifier=result.get("has_absolute_disqualifier", False),
        summary="; ".join(result.get("reasons", [])[:5]) or None,
        model_version=result["model_version"],
        evaluated_at=utcnow(),
    )
    db.add(assessment)
    db.flush()

    label_for = {i["key"]: i for i in QUALIFICATION_ITEMS}
    for item in QUALIFICATION_ITEMS:
        given = answers.get(item["key"], {}) or {}
        db.add(
            QualificationChecklistItem(
                assessment_id=assessment.id,
                item_key=item["key"],
                item_label=item["label"],
                is_mandatory=item["mandatory"],
                answer=given.get("answer", "unknown"),
                explanation=given.get("explanation"),
                last_reviewed_at=utcnow() if given.get("answer") else None,
                source=given.get("source", "ai"),
            )
        )

    for finding in result.get("findings", []):
        db.add(
            QualificationBlocker(
                assessment_id=assessment.id,
                failure_type=finding["type"],
                item_key=finding.get("item_key"),
                message=finding["message"],
            )
        )
    db.flush()
    return result


# -------------------------------------------------- enforcement (§6)

def enforce_classification_evidence(db: Session, opportunity: Opportunity) -> str | None:
    """Rule 1. Runs immediately before persistence. Returns a downgrade
    note if the Confirmed claim was not supported, having already applied
    the downgrade to the opportunity."""
    records = evidence_as_dicts(db, opportunity.id)
    new_classification, note = evidence_engine.downgrade_classification_if_unsupported(
        classification=opportunity.classification or "",
        evidence_records=records,
        last_verified_at=opportunity.last_verified_at.isoformat() if opportunity.last_verified_at else None,
        confidence=opportunity.verification_confidence,
    )
    if note:
        opportunity.classification = new_classification
        opportunity.requires_human_review = True
        opportunity.human_review_reason = note
    return note


def assert_can_enter_active_pipeline(db: Session, opportunity: Opportunity) -> None:
    """Rules 2 and 3. Raises rather than returning a flag, because a caller
    that forgets to check a boolean is exactly how this rule gets bypassed.

    Deadline is evaluated by the qualification gate alongside the other
    rules so ALL objections surface together — see PIPELINE_RULE_ORDER in
    qualification.py for the documented hierarchy.
    """
    from ..models_phase2 import QualificationAssessment

    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity.id).first()
    state = assessment.state if assessment else QualificationState.NOT_ASSESSED.value
    deadline_passed = bool(opportunity.deadline and opportunity.deadline < date.today())

    allowed, reasons = qualification_engine.can_enter_active_pipeline(
        state, opportunity.classification, deadline_passed=deadline_passed
    )
    if not allowed:
        raise ServiceRuleViolation("Opportunity cannot enter the active pipeline", reasons)


def value_display_guard(commercial_value: CommercialValue | None) -> dict:
    """Rule 6. Returns display metadata so no layer has to decide for
    itself whether a figure is a published fact — the answer travels with
    the number."""
    if commercial_value is None:
        return {"is_published_fact": False, "label": "No value recorded", "show_as_range": False}
    is_estimate = commercial_value.value_status in ESTIMATED_VALUE_STATUSES
    return {
        "is_published_fact": not is_estimate and commercial_value.value_status.startswith("published"),
        "is_estimate": is_estimate,
        "show_as_range": is_estimate,
        "label": "AI estimate — not a published figure" if is_estimate else None,
        "methodology": commercial_value.estimate_methodology if is_estimate else None,
    }


def record_override(db: Session, opportunity_id: str, field_path: str, original: Any,
                    updated: Any, reason: str, model_version: str | None = None) -> OverrideAudit:
    """Rules 7 and 8. A reason is mandatory, and the original value is
    written once and never updated afterwards."""
    if not reason or not reason.strip():
        raise ServiceRuleViolation("A manual override requires a reason.", ["reason is required"])
    audit = OverrideAudit(
        opportunity_id=opportunity_id,
        field_path=field_path,
        original_value=_stringify(original),
        updated_value=_stringify(updated),
        reason=reason.strip(),
        model_version=model_version,
    )
    db.add(audit)
    db.flush()
    return audit


def override_qualification_state(db: Session, opportunity_id: str, new_state: str,
                                 reason: str, note: str | None = None) -> QualificationOverride:
    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity_id).first()
    if assessment is None:
        raise ServiceRuleViolation("No qualification assessment to override.")
    payload = qualification_engine.apply_manual_override(
        current_state=assessment.state, new_state=new_state, reason=reason, note=note
    )
    row = QualificationOverride(
        assessment_id=assessment.id,
        previous_state=payload["previous_state"],
        new_state=payload["new_state"],
        reason=payload["reason"],
        note=payload["note"],
    )
    db.add(row)
    assessment.state = new_state
    assessment.last_reviewed_at = utcnow()
    db.flush()
    return row


def override_score(db: Session, opportunity_id: str, dimension: str, manual_score: int,
                   reason: str) -> ScoreAssessment:
    """Rule 8 for scores: the AI value is preserved in `ai_score` and the
    manual value written alongside it, never over it."""
    assessment = db.query(ScoreAssessment).filter_by(
        opportunity_id=opportunity_id, dimension=dimension
    ).first()
    if assessment is None:
        raise ServiceRuleViolation(f"No {dimension} assessment to override.")

    payload = scoring_engine.build_score_override(
        dimension=dimension,
        ai_score=assessment.ai_score if assessment.ai_score is not None else assessment.score,
        manual_score=manual_score,
        reason=reason,
        timestamp=utcnow().isoformat(),
    )
    if assessment.ai_score is None:
        assessment.ai_score = assessment.score  # capture before first override
    assessment.manual_score = payload["manual_score"]
    assessment.score = payload["manual_score"]
    assessment.override_reason = payload["reason"]
    assessment.overridden_at = utcnow()

    record_override(
        db, opportunity_id, f"score.{dimension}",
        original=assessment.ai_score, updated=manual_score,
        reason=reason, model_version=assessment.model_version,
    )
    db.flush()
    return assessment


# ------------------------------------------------------ parse failures

def record_parse_failure(db: Session, raw_response: str, errors: list[dict],
                         scan_run_id: str | None = None, proposed_title: str | None = None) -> AIParseFailure:
    """A validation failure becomes a durable record — never a partially
    populated opportunity (§4)."""
    failure = AIParseFailure(
        scan_run_id=scan_run_id,
        raw_response=raw_response,
        validation_errors={"errors": errors},
        proposed_title=proposed_title,
        parse_status="parsing_failed",
    )
    db.add(failure)
    db.flush()
    return failure


# ----------------------------------------------------------- helpers

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


# ------------------------------------------------ owner qualification workflow

def answer_qualification_items(db: Session, opportunity_id: str,
                               answers: dict[str, dict]) -> dict:
    """Records the owner's answers and RE-EVALUATES the gate.

    Re-evaluation is the whole point: answering a checklist that didn't
    change the resulting state would be a form to fill in, not a decision
    tool. Existing answers are merged rather than replaced, so answering
    three items doesn't silently reset the other thirteen to unknown.
    """
    from ..models_phase2 import QualificationAssessment, QualificationChecklistItem

    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise ServiceRuleViolation("Opportunity not found.")

    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity_id).first()
    merged: dict[str, dict] = {}
    if assessment:
        for item in db.query(QualificationChecklistItem).filter_by(assessment_id=assessment.id).all():
            merged[item.item_key] = {
                "answer": item.answer,
                "explanation": item.explanation,
                "evidence_id": item.evidence_id,
                "source": item.source,
            }

    valid_answers = {a.value for a in GateAnswer}
    for key, payload in (answers or {}).items():
        answer = (payload or {}).get("answer")
        if answer is not None and answer not in valid_answers:
            raise ServiceRuleViolation(
                f"Invalid answer '{answer}' for '{key}'.",
                [f"Valid answers: {sorted(valid_answers)}"],
            )
        existing = merged.get(key, {})
        merged[key] = {
            "answer": answer or existing.get("answer", GateAnswer.UNKNOWN.value),
            "explanation": (payload or {}).get("explanation", existing.get("explanation")),
            "evidence_id": (payload or {}).get("evidence_id", existing.get("evidence_id")),
            "source": "manual",
        }

    result = persist_qualification(
        db,
        opportunity_id,
        merged,
        classification=opp.classification,
        deadline=opp.deadline,
        has_credible_source=_has_credible_source(db, opportunity_id),
    )

    # Re-run priority: the cap depends on the qualification state, so a
    # newly-qualified opportunity must stop being capped immediately.
    _recalculate_priority(db, opportunity_id, result["state"])
    db.flush()
    return result


def _has_credible_source(db: Session, opportunity_id: str) -> bool:
    from ..models_phase2 import OpportunityEvidence

    return (
        db.query(OpportunityEvidence)
        .filter(
            OpportunityEvidence.opportunity_id == opportunity_id,
            OpportunityEvidence.source_tier.in_(["tier_1", "tier_2"]),
        )
        .count()
        > 0
    )


def _recalculate_priority(db: Session, opportunity_id: str, qualification_state: str) -> None:
    """Rebuilds the priority from the stored score assessments after a
    qualification change."""
    from ..models_phase2 import ScoreAssessment, ScoreFactor

    assessments = db.query(ScoreAssessment).filter_by(opportunity_id=opportunity_id).all()
    if not assessments:
        return

    computed: dict[str, dict] = {}
    for a in assessments:
        factors = db.query(ScoreFactor).filter_by(assessment_id=a.id).all()
        computed[a.dimension] = {
            "score": a.score,
            "coverage": a.coverage,
            # Default to True when NULL: `bool(None)` is False, which would
            # wrongly apply the risk restriction to an opportunity whose
            # risk was never flagged as unestablished.
            "risk_established": (
                (a.risk_established if a.risk_established is not None else True)
                if a.dimension == "risk" else None
            ),
            "factors": [{"key": f.factor_key, "scored": f.scored, "weight": f.weight} for f in factors],
        }
    if len(computed) == 4:
        persist_pursuit_priority(db, opportunity_id, computed, qualification_state)


def qualification_next_actions(db: Session, opportunity_id: str) -> list[dict]:
    """What is actually stopping this opportunity progressing, and what
    would resolve it.

    Exists so the gate is never a dead end. A backend that blocks
    progression without saying how to unblock it is worse than no gate —
    the user has no route forward and no explanation, so the opportunity
    silently rots at 'verification required'.
    """
    from ..models_phase2 import (
        OpportunityAnalysisItem,
        QualificationAssessment,
        QualificationChecklistItem,
    )

    assessment = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity_id).first()
    if assessment is None:
        return [
            {
                "type": "assess",
                "action": "Complete the qualification checklist.",
                "detail": "This opportunity has not been assessed yet.",
                "item_key": None,
            }
        ]

    actions: list[dict] = []
    label_for = {i["key"]: i for i in QUALIFICATION_ITEMS}

    for item in db.query(QualificationChecklistItem).filter_by(assessment_id=assessment.id).all():
        if item.answer != GateAnswer.UNKNOWN.value:
            continue
        meta = label_for.get(item.item_key, {})
        actions.append(
            {
                "type": "answer_mandatory" if meta.get("mandatory") else "answer_optional",
                "action": f"Answer: {item.item_label}",
                "detail": (
                    "Mandatory — the opportunity cannot be qualified until this is resolved."
                    if meta.get("mandatory")
                    else "Optional — an unanswered item holds this at Conditionally Qualified."
                ),
                "item_key": item.item_key,
            }
        )

    for gap in (
        db.query(OpportunityAnalysisItem)
        .filter_by(opportunity_id=opportunity_id, item_type="human_verification_action")
        .all()
    ):
        if not gap.is_completed:
            actions.append(
                {
                    "type": "verification_action",
                    "action": gap.content,
                    "detail": "Recommended verification action.",
                    "item_key": None,
                }
            )

    return actions

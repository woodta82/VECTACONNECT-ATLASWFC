"""Phase 2 opportunity serialisation — the API and frontend contract.

One place decides the shape the frontend receives. Two principles:

1. **Labels travel with values.** Every coded value ships its human label
   alongside it (`classification` + `classification_label`), so the
   frontend never maintains its own copy of the taxonomy — a mapping that
   would silently go stale the first time a value is added.

2. **Safety decisions are made here, not by the consumer.** Whether a
   figure is a published fact, whether risk is established, whether a
   score is provisional — these are computed once and shipped as explicit
   flags and labels. A frontend that has to infer "is this number
   trustworthy?" from raw fields will eventually infer wrong, and the
   failure mode is a confidently-displayed misleading number.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Opportunity
from ..models_phase2 import (
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
    ScoreAssessment,
    ScoreFactor,
)
from ..scoring_v2 import DIMENSIONS
from ..taxonomy import (
    CLASSIFICATION_INFO,
    COMMERCIAL_TYPE_LABELS,
    FAILURE_TYPE_INFO,
    QUALIFICATION_STATE_LABELS,
    ROUTE_TO_MARKET_LABELS,
    SOURCE_TIER_INFO,
    VALUE_STATUS_INFO,
    VERTICAL_V2_INFO,
)
from . import opportunity_service as service


def _label(mapping: dict, key: str | None, field: str = "label") -> str | None:
    if not key:
        return None
    entry = mapping.get(key)
    if isinstance(entry, dict):
        return entry.get(field, key)
    return entry or key


def _serialise_evidence(db: Session, opportunity_id: str) -> list[dict]:
    rows = db.query(OpportunityEvidence).filter_by(opportunity_id=opportunity_id).all()
    out = []
    for r in rows:
        claims = [c.claim_type for c in db.query(EvidenceClaim).filter_by(evidence_id=r.id).all()]
        out.append(
            {
                "id": r.id,
                "url": r.url,
                "page_title": r.page_title,
                "publisher": r.publisher,
                "source_tier": r.source_tier,
                "source_tier_label": _label(SOURCE_TIER_INFO, r.source_tier),
                "evidence_type": r.evidence_type,
                "publication_date": r.publication_date.isoformat() if r.publication_date else None,
                "no_publication_date_reason": r.no_publication_date_reason,
                "url_validation_status": r.url_validation_status,
                "url_validation_label": {
                    "not_reviewed": "Not reviewed",
                    "valid": "Validated",
                    "unreachable": "Unreachable",
                    "archived": "Archived copy",
                    "invalid": "Invalid",
                }.get(r.url_validation_status, r.url_validation_status),
                "is_official_source": r.is_official_source,
                "is_definitive": r.is_definitive,
                "confidence": r.confidence,
                "claims_supported": claims,
                "is_manual": r.is_manual,
            }
        )
    return out


def _evidence_status(evidence: list[dict]) -> dict:
    """A single readable summary for the opportunity card, so the list view
    doesn't need to reason about tiers itself."""
    if not evidence:
        return {"key": "none", "label": "No evidence", "tier_1_count": 0, "validated_count": 0}
    tier1 = sum(1 for e in evidence if e["source_tier"] == "tier_1")
    validated = sum(1 for e in evidence if e["url_validation_status"] in ("valid", "archived"))
    if tier1 and validated:
        key, label = "strong", f"Tier 1 verified ({len(evidence)} sources)"
    elif tier1:
        key, label = "official_unverified", f"Tier 1, URL not reviewed ({len(evidence)})"
    elif validated:
        key, label = "secondary", f"Secondary sources verified ({len(evidence)})"
    else:
        key, label = "weak", f"Unverified sources ({len(evidence)})"
    return {"key": key, "label": label, "tier_1_count": tier1, "validated_count": validated}


def _serialise_scores(db: Session, opportunity_id: str) -> dict:
    assessments = db.query(ScoreAssessment).filter_by(opportunity_id=opportunity_id).all()
    out: dict[str, dict] = {}
    for a in assessments:
        factors = db.query(ScoreFactor).filter_by(assessment_id=a.id).all()
        is_risk = a.dimension == "risk"
        established = a.risk_established if is_risk else True

        # The display decision is made here, once.
        if is_risk and established is False:
            display_score, display_label = None, "Risk not established"
        else:
            display_score, display_label = a.score, str(a.score)

        out[a.dimension] = {
            "dimension": a.dimension,
            "label": DIMENSIONS.get(a.dimension, {}).get("label", a.dimension),
            "score": a.score,
            "display_score": display_score,
            "display_label": display_label,
            "higher_is_better": DIMENSIONS.get(a.dimension, {}).get("higher_is_better", True),
            "coverage_percent": a.coverage_percent,
            "coverage_band": a.coverage_band,
            "coverage_label": {
                "assessed": "Assessed",
                "provisional": "Provisional",
                "insufficient": "Provisional — insufficient assessment",
            }.get(a.coverage_band, a.coverage_band),
            "risk_established": established if is_risk else None,
            "confidence": a.confidence,
            "rationale": a.rationale,
            "ai_score": a.ai_score,
            "manual_score": a.manual_score,
            "is_overridden": a.manual_score is not None,
            "override_reason": a.override_reason,
            "overridden_at": a.overridden_at.isoformat() if a.overridden_at else None,
            "model_version": a.model_version,
            "last_scored_at": a.last_scored_at.isoformat() if a.last_scored_at else None,
            "factors": [
                {
                    "key": f.factor_key,
                    "label": f.factor_label,
                    "weight": f.weight,
                    "score": f.score,
                    "scored": f.scored,
                    "status_label": "Scored" if f.scored else "Not assessed",
                    "rationale": f.rationale,
                }
                for f in factors
            ],
        }
    return out


def _serialise_priority(db: Session, opportunity_id: str) -> dict | None:
    p = db.query(PursuitPriority).filter_by(opportunity_id=opportunity_id).first()
    if p is None:
        return None
    return {
        "final_score": p.final_score,
        "uncapped_score": p.uncapped_score,
        "band": p.band,
        "band_label": p.band_label,
        "base_score": p.base_score,
        "inverse_risk": p.inverse_risk,
        "urgency_adjustment": p.urgency_adjustment,
        "coverage_restricted": p.coverage_restricted,
        "qualification_restricted": p.qualification_restricted,
        "is_restricted": p.coverage_restricted or p.qualification_restricted,
        "restriction_explanation": p.restriction_explanation,
        "weights_used": p.weights_used,
        "model_version": p.model_version,
        "calculated_at": p.calculated_at.isoformat() if p.calculated_at else None,
    }


def _serialise_qualification(db: Session, opportunity_id: str) -> dict | None:
    q = db.query(QualificationAssessment).filter_by(opportunity_id=opportunity_id).first()
    if q is None:
        return {
            "state": "not_assessed",
            "state_label": QUALIFICATION_STATE_LABELS["not_assessed"],
            "checklist": [],
            "blockers": [],
        }
    items = db.query(QualificationChecklistItem).filter_by(assessment_id=q.id).all()
    blockers = db.query(QualificationBlocker).filter_by(assessment_id=q.id).all()
    return {
        "state": q.state,
        "state_label": QUALIFICATION_STATE_LABELS.get(q.state, q.state),
        "has_absolute_disqualifier": q.has_absolute_disqualifier,
        "summary": q.summary,
        "evaluated_at": q.evaluated_at.isoformat() if q.evaluated_at else None,
        "checklist": [
            {
                "item_key": i.item_key,
                "item_label": i.item_label,
                "is_mandatory": i.is_mandatory,
                "answer": i.answer,
                "answer_label": {
                    "yes": "Yes", "no": "No", "unknown": "Unknown", "not_applicable": "N/A"
                }.get(i.answer, i.answer),
                "explanation": i.explanation,
                "source": i.source,
            }
            for i in items
        ],
        "blockers": [
            {
                "failure_type": b.failure_type,
                "failure_type_label": _label(FAILURE_TYPE_INFO, b.failure_type),
                "item_key": b.item_key,
                "message": b.message,
                "is_resolved": b.is_resolved,
                "is_remediable": b.failure_type == "remediable_blocker",
            }
            for b in blockers
        ],
    }


def _serialise_commercial_value(db: Session, opportunity_id: str) -> dict | None:
    v = db.query(CommercialValue).filter_by(opportunity_id=opportunity_id).first()
    if v is None:
        return None
    guard = service.value_display_guard(v)
    return {
        "value_status": v.value_status,
        "value_status_label": _label(VALUE_STATUS_INFO, v.value_status),
        "currency": v.currency,
        "published_programme_value": v.published_programme_value,
        "published_contract_value": v.published_contract_value,
        "estimated_contract_min": v.estimated_contract_min,
        "estimated_contract_max": v.estimated_contract_max,
        "estimated_vecta_revenue": v.estimated_vecta_revenue,
        "estimate_methodology": v.estimate_methodology,
        "partner_share_assumption": v.partner_share_assumption,
        "confidence": v.confidence,
        "is_legacy_unverified": v.is_legacy_unverified,
        # Explicit safety flags — the frontend must not infer these.
        "is_published_fact": guard["is_published_fact"],
        "is_estimate": guard.get("is_estimate", False),
        "display_warning": guard.get("label"),
        "last_reviewed_at": v.last_reviewed_at.isoformat() if v.last_reviewed_at else None,
    }


def _analysis_of(db: Session, opportunity_id: str, item_type: str) -> list[dict]:
    rows = (
        db.query(OpportunityAnalysisItem)
        .filter_by(opportunity_id=opportunity_id, item_type=item_type)
        .all()
    )
    return [
        {
            "id": r.id,
            "content": r.content,
            "claim_type": r.claim_type,
            "supporting_evidence_id": r.supporting_evidence_id,
            "is_verified": r.is_verified,
            "verification_label": "Verified" if r.is_verified else "Unverified",
            "is_completed": r.is_completed,
            "source": r.source,
            "source_label": "AI" if r.source == "ai" else "Manual",
        }
        for r in rows
    ]


def serialise_opportunity(db: Session, opp: Opportunity, include_detail: bool = True) -> dict:
    """The full Phase 2 payload. `include_detail=False` returns the card
    shape for list views — same field names throughout, so the list and
    detail pages never disagree about what a field means."""
    evidence = _serialise_evidence(db, opp.id)
    contributing = db.query(OpportunityContributingVertical).filter_by(opportunity_id=opp.id).all()
    scores = _serialise_scores(db, opp.id)
    priority = _serialise_priority(db, opp.id)
    qualification = _serialise_qualification(db, opp.id)
    value = _serialise_commercial_value(db, opp.id)

    payload = {
        "id": opp.id,
        "title": opp.title,
        "summary": opp.summary,
        "organisation_id": opp.organisation_id,
        "region": opp.region.value if opp.region else None,
        "market": opp.market,
        "deadline": opp.deadline.isoformat() if opp.deadline else None,
        "stage": opp.stage.value if opp.stage else None,
        # classification
        "classification": opp.classification,
        "classification_label": _label(CLASSIFICATION_INFO, opp.classification),
        "classification_rationale": opp.classification_rationale,
        "primary_vertical": opp.primary_vertical,
        "primary_vertical_label": _label(VERTICAL_V2_INFO, opp.primary_vertical),
        "vertical_rationale": opp.vertical_rationale,
        "contributing_verticals": [
            {"vertical": c.vertical, "label": _label(VERTICAL_V2_INFO, c.vertical), "rationale": c.rationale}
            for c in contributing
        ],
        "contributing_vertical_count": len(contributing),
        "primary_commercial_type": opp.primary_commercial_type,
        "primary_commercial_type_label": COMMERCIAL_TYPE_LABELS.get(opp.primary_commercial_type),
        "routes_to_market": [
            {"route": r.route, "label": ROUTE_TO_MARKET_LABELS.get(r.route, r.route),
             "notes": r.notes, "is_satisfied": r.is_satisfied}
            for r in db.query(OpportunityRouteToMarket).filter_by(opportunity_id=opp.id).all()
        ],
        # evidence
        "evidence": evidence,
        "evidence_status": _evidence_status(evidence),
        # scores + priority + qualification + value
        "scores": scores,
        "pursuit_priority": priority,
        "qualification": qualification,
        "commercial_value": value,
        # review
        "requires_human_review": opp.requires_human_review,
        "human_review_reason": opp.human_review_reason,
        "last_verified_at": opp.last_verified_at.isoformat() if opp.last_verified_at else None,
        "verification_confidence": opp.verification_confidence,
    }

    if not include_detail:
        return payload

    payload.update(
        {
            "secondary_commercial_types": [
                {"commercial_type": s.commercial_type,
                 "label": COMMERCIAL_TYPE_LABELS.get(s.commercial_type, s.commercial_type),
                 "justification": s.justification}
                for s in db.query(OpportunitySecondaryCommercialType).filter_by(opportunity_id=opp.id).all()
            ],
            "verified_facts": _analysis_of(db, opp.id, AnalysisItemType.VERIFIED_FACT.value),
            "ai_interpretation": _analysis_of(db, opp.id, AnalysisItemType.AI_INTERPRETATION.value),
            "assumptions": _analysis_of(db, opp.id, AnalysisItemType.ASSUMPTION.value),
            "missing_information": _analysis_of(db, opp.id, AnalysisItemType.MISSING_INFORMATION.value),
            "verification_actions": _analysis_of(db, opp.id, AnalysisItemType.VERIFICATION_ACTION.value),
            "overrides": [
                {
                    "field_path": o.field_path,
                    "original_value": o.original_value,
                    "updated_value": o.updated_value,
                    "reason": o.reason,
                    "model_version": o.model_version,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in db.query(OverrideAudit).filter_by(opportunity_id=opp.id)
                .order_by(OverrideAudit.created_at.desc()).all()
            ],
            "legacy": _serialise_legacy(db, opp.id),
        }
    )
    return payload


def _serialise_legacy(db: Session, opportunity_id: str) -> dict | None:
    row = db.query(LegacyOpportunityData).filter_by(opportunity_id=opportunity_id).first()
    if row is None:
        return None
    return {
        "legacy_alignment_score": row.legacy_alignment_score,
        "legacy_score_breakdown": row.legacy_score_breakdown,
        "legacy_vertical": row.legacy_vertical,
        "legacy_value_estimate": row.legacy_value_estimate,
        "legacy_currency": row.legacy_currency,
        "vertical_mapping_status": row.vertical_mapping_status,
        "vertical_requires_review": row.vertical_requires_review,
        "migration_version": row.migration_version,
        "migrated_at": row.migrated_at.isoformat() if row.migrated_at else None,
        "notice": "Superseded by the four-dimension model — retained for audit only.",
    }

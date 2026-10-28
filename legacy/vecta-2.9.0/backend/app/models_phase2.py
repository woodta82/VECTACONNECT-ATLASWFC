"""Phase 2 persistent model (rebuild spec §2).

Deliberately normalised. Every material, filterable or auditable field is
a real column on a real table — the spec is explicit that the Phase 2
structure must not be hidden inside one uncontrolled JSON column, and it
is right: a JSON blob cannot be indexed, filtered, joined or audited, and
the whole point of Phase 2 is that scores and evidence are inspectable.

JSON is used in exactly two places, both legitimate:
  - `AIParseFailure.raw_response` — an immutable payload kept verbatim
    for diagnosis. It is evidence of what happened, not queryable data.
  - `LegacyOpportunityData.legacy_score_breakdown` — a frozen historical
    snapshot of a superseded model.

Relationship shape:
    Opportunity 1─┬─* OpportunityEvidence 1─* EvidenceClaim
                  ├─* OpportunityAnalysisItem   (facts/interpretation/assumptions/gaps/actions)
                  ├─* ScoreAssessment 1─* ScoreFactor
                  ├─1 PursuitPriority
                  ├─1 QualificationAssessment 1─┬─* QualificationChecklistItem
                  │                             └─* QualificationOverride
                  ├─1 CommercialValue
                  ├─1 LegacyOpportunityData
                  └─* OverrideAudit
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .timeutils import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------- enums

class AnalysisItemType(str, enum.Enum):
    """The four-way separation the spec requires (§8 of the Phase 2 spec):
    facts, interpretation, assumptions and gaps must never be merged into
    one summary field."""

    VERIFIED_FACT = "verified_fact"
    AI_INTERPRETATION = "ai_interpretation"
    ASSUMPTION = "assumption"
    MISSING_INFORMATION = "missing_information"
    VERIFICATION_ACTION = "human_verification_action"


class ParseStatus(str, enum.Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    PARSING_FAILED = "parsing_failed"
    RESOLVED_MANUALLY = "resolved_manually"
    RETRIED = "retried"


# ------------------------------------------------------------ evidence

class OpportunityEvidence(Base):
    """One source supporting an opportunity. Tier, validation state and
    official/definitive flags are columns because the Confirmed-Opportunity
    gate filters on them in the service layer."""

    __tablename__ = "opportunity_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )

    url: Mapped[str] = mapped_column(Text)
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_tier: Mapped[str] = mapped_column(String(16), index=True)
    evidence_type: Mapped[str] = mapped_column(String(48), default="other")

    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    no_publication_date_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_accessed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    url_validation_status: Mapped[str] = mapped_column(String(24), default="not_reviewed", index=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)

    is_official_source: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_definitive: Mapped[bool] = mapped_column(Boolean, default=False)

    confidence: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)

    claims: Mapped[list["EvidenceClaim"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )


class EvidenceClaim(Base):
    """Claim-level linkage (§5). Its own table rather than a list column
    because the central rule — "does evidence exist for THIS claim?" — is
    a query, and because a claim link is itself auditable (the owner can
    add or remove one, and that is a correction worth recording)."""

    __tablename__ = "evidence_claims"
    __table_args__ = (UniqueConstraint("evidence_id", "claim_type", name="uq_evidence_claim"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="CASCADE"), index=True
    )
    claim_type: Mapped[str] = mapped_column(String(48), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evidence: Mapped["OpportunityEvidence"] = relationship(back_populates="claims")


# ------------------------------------------------------------ analysis

class OpportunityAnalysisItem(Base):
    """Facts, interpretation, assumptions, gaps and verification actions —
    one table with a type discriminator, so they are stored separately but
    queried uniformly. A verified fact carries `supporting_evidence_id`;
    an assumption by definition does not."""

    __tablename__ = "opportunity_analysis_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)

    claim_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    supporting_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Verification actions only
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai | manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------------------------------------- scoring

class ScoreAssessment(Base):
    """One row per dimension per opportunity (four rows when fully
    assessed). Coverage and the risk-established flag are columns because
    the priority engine and the API filters both read them."""

    __tablename__ = "score_assessments"
    __table_args__ = (UniqueConstraint("opportunity_id", "dimension", name="uq_opportunity_dimension"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(32), index=True)

    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    coverage: Mapped[float] = mapped_column(Float, default=0.0)
    coverage_percent: Mapped[int] = mapped_column(Integer, default=0, index=True)
    coverage_band: Mapped[str] = mapped_column(String(24), default="insufficient", index=True)

    # Risk only: when false the UI must show "Risk not established"
    # rather than the computed number.
    risk_established: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)

    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    ai_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    model_version: Mapped[str] = mapped_column(String(16), default="2.0")
    last_scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Phase 3.1: which Commercial Profile produced this score. NULL means
    # it was scored before the profile existed — honest, not back-dated.
    # `is_stale` is set when the profile changes, WITHOUT altering the
    # score, so history stays readable against the criteria in force.
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    factors: Mapped[list["ScoreFactor"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class ScoreFactor(Base):
    """Factor-level score with its own rationale and evidence link — this
    is what makes "no score without an explanation" enforceable at the
    data layer rather than by convention."""

    __tablename__ = "score_factors"
    __table_args__ = (UniqueConstraint("assessment_id", "factor_key", name="uq_assessment_factor"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("score_assessments.id", ondelete="CASCADE"), index=True
    )
    factor_key: Mapped[str] = mapped_column(String(64), index=True)
    factor_label: Mapped[str] = mapped_column(String(128))
    weight: Mapped[float] = mapped_column(Float)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unscored
    scored: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )

    assessment: Mapped["ScoreAssessment"] = relationship(back_populates="factors")


class PursuitPriority(Base):
    """The full priority calculation, stored rather than recomputed on
    read so the displayed number always matches what the restrictions
    were evaluated against."""

    __tablename__ = "pursuit_priorities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True
    )

    base_score: Mapped[float] = mapped_column(Float, default=0.0)
    inverse_risk: Mapped[float] = mapped_column(Float, default=0.0)
    urgency_adjustment: Mapped[float] = mapped_column(Float, default=0.0)
    uncapped_score: Mapped[int] = mapped_column(Integer, default=0)
    final_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    band: Mapped[str] = mapped_column(String(24), default="low", index=True)
    band_label: Mapped[str] = mapped_column(String(48), default="Low Priority")

    coverage_restricted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    qualification_restricted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    restriction_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    weights_used: Mapped[dict] = mapped_column(JSON, default=dict)  # snapshot of the weighting
    model_version: Mapped[str] = mapped_column(String(16), default="2.0")
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------------------------------- qualification

class QualificationAssessment(Base):
    __tablename__ = "qualification_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True
    )

    state: Mapped[str] = mapped_column(String(32), default="not_assessed", index=True)
    has_absolute_disqualifier: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_version: Mapped[str] = mapped_column(String(16), default="2.0")
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["QualificationChecklistItem"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    blockers: Mapped[list["QualificationBlocker"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    overrides: Mapped[list["QualificationOverride"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class QualificationChecklistItem(Base):
    __tablename__ = "qualification_checklist_items"
    __table_args__ = (UniqueConstraint("assessment_id", "item_key", name="uq_assessment_item"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("qualification_assessments.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(64), index=True)
    item_label: Mapped[str] = mapped_column(String(128))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)

    answer: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai | manual

    assessment: Mapped["QualificationAssessment"] = relationship(back_populates="items")


class QualificationBlocker(Base):
    """Typed failures (§3 correction): absolute disqualifiers are separated
    from remediable blockers so a recoverable obstacle is never buried as
    permanent disqualification."""

    __tablename__ = "qualification_blockers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("qualification_assessments.id", ondelete="CASCADE"), index=True
    )
    failure_type: Mapped[str] = mapped_column(String(48), index=True)
    item_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessment: Mapped["QualificationAssessment"] = relationship(back_populates="blockers")


class QualificationOverride(Base):
    __tablename__ = "qualification_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("qualification_assessments.id", ondelete="CASCADE"), index=True
    )
    previous_state: Mapped[str] = mapped_column(String(32))
    new_state: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessment: Mapped["QualificationAssessment"] = relationship(back_populates="overrides")


# ---------------------------------------------------- commercial value

class CommercialValue(Base):
    """Replaces the single `value_estimate` field. Programme value and
    contract value are separate columns precisely so a national strategy's
    headline figure can never be mistaken for money available to VECTA."""

    __tablename__ = "commercial_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True
    )

    published_programme_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    published_contract_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_contract_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_contract_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_vecta_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)

    currency: Mapped[str] = mapped_column(String(8), default="USD")
    value_status: Mapped[str] = mapped_column(String(48), default="insufficient_evidence", index=True)
    estimate_methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    partner_share_assumption: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_legacy_unverified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ------------------------------------------------------- AI processing

class AIParseFailure(Base):
    """A validation failure is a first-class record, not a log line. The
    raw response is preserved verbatim so a failure can be diagnosed and
    retried without re-running (and re-paying for) the scan."""

    __tablename__ = "ai_parse_failures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_response: Mapped[str] = mapped_column(Text)  # verbatim, never parsed-and-stored
    schema_version: Mapped[str] = mapped_column(String(16), default="2.0")
    parse_status: Mapped[str] = mapped_column(String(32), default="parsing_failed", index=True)
    validation_errors: Mapped[dict] = mapped_column(JSON, default=dict)
    proposed_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ------------------------------------------------------------- legacy

class LegacyOpportunityData(Base):
    """Pre-Phase-2 values, preserved rather than overwritten (§3/§8 of the
    migration requirements). Kept in its own table so nothing in the live
    model accidentally reads a superseded score as current."""

    __tablename__ = "legacy_opportunity_data"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True
    )

    legacy_alignment_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)  # frozen snapshot
    legacy_vertical: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legacy_value_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    legacy_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    vertical_mapping_status: Mapped[str] = mapped_column(String(32), default="mapped", index=True)
    vertical_requires_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    migration_version: Mapped[str] = mapped_column(String(16))
    migrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# -------------------------------------------------------------- audit

class OverrideAudit(Base):
    """Every manual correction, in one append-only place. `original_value`
    is never updated after insert — that is what "do not delete the
    original AI value" means in practice."""

    __tablename__ = "override_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    field_path: Mapped[str] = mapped_column(String(128), index=True)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ------------------------------------------- multi-valued classification

class OpportunityContributingVertical(Base):
    """Contributing verticals (§3): an opportunity has ONE primary vertical
    (a column on Opportunity) and zero or more contributing ones. A join
    table rather than a JSON list because "show me everything VECTA
    Intelligence contributes to" must be an indexed query."""

    __tablename__ = "opportunity_contributing_verticals"
    __table_args__ = (UniqueConstraint("opportunity_id", "vertical", name="uq_opp_contributing_vertical"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    vertical: Mapped[str] = mapped_column(String(32), index=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpportunitySecondaryCommercialType(Base):
    """Secondary commercial types (§5) — one primary on Opportunity, plus
    any number of justified secondaries here."""

    __tablename__ = "opportunity_secondary_commercial_types"
    __table_args__ = (UniqueConstraint("opportunity_id", "commercial_type", name="uq_opp_secondary_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    commercial_type: Mapped[str] = mapped_column(String(48), index=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpportunityRouteToMarket(Base):
    """Route-to-market requirements (§6). Deliberately many-per-opportunity:
    an opportunity can be open competition AND local-entity-required AND
    consortium-required simultaneously, and forcing a single choice would
    destroy real information about what it takes to bid."""

    __tablename__ = "opportunity_routes_to_market"
    __table_args__ = (UniqueConstraint("opportunity_id", "route", name="uq_opp_route"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    route: Mapped[str] = mapped_column(String(48), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_satisfied: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

"""Relationship Intelligence — Sprint 2.

Turns contacts from address-book entries into intelligence profiles.

`Contact` is extended, not replaced: it holds discovery data (LinkedIn
URLs, source, relevance) and is referenced by three tables in Phase 2.
Rewriting it would be a Phase 2 change, which the foundation rules
forbid. `Stakeholder` adds the intelligence layer on top.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .timeutils import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


class StakeholderType(str, enum.Enum):
    ECONOMIC_BUYER = "economic_buyer"
    BUDGET_HOLDER = "budget_holder"
    PROGRAMME_SPONSOR = "programme_sponsor"
    PROCUREMENT_AUTHORITY = "procurement_authority"
    POLITICAL_SPONSOR = "political_sponsor"
    TECHNICAL_EVALUATOR = "technical_evaluator"
    TECHNICAL_INFLUENCER = "technical_influencer"
    ADVISER = "adviser"
    GATEKEEPER = "gatekeeper"
    INTRODUCER = "introducer"
    DELIVERY_PARTNER = "delivery_partner"
    CONSULTANT = "consultant"
    UNKNOWN = "unknown"


class StakeholderPosture(str, enum.Enum):
    """Where they stand on VECTA — distinct from how well we know them.

    A champion we rarely speak to and a blocker we speak to weekly are
    different problems, and collapsing posture into relationship strength
    would hide both.
    """

    CHAMPION = "champion"
    SUPPORTIVE = "supportive"
    NEUTRAL = "neutral"
    SCEPTICAL = "sceptical"
    BLOCKER = "blocker"
    UNKNOWN = "unknown"


class EngagementType(str, enum.Enum):
    MEETING = "meeting"
    CALL = "call"
    EMAIL = "email"
    INTRODUCTION = "introduction"
    EVENT = "event"
    COMMITMENT = "commitment"
    NOTE = "note"


class EngagementOutcome(str, enum.Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    NO_RESPONSE = "no_response"
    PENDING = "pending"


class Stakeholder(Base):
    """An intelligence profile. Every judgement column carries evidence or
    is explicitly marked inferred — the same discipline as opportunity
    scoring, because a confidently wrong influence rating misdirects
    executive time just as effectively as a wrong score."""

    __tablename__ = "stakeholders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organisation_id: Mapped[str | None] = mapped_column(
        ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    full_name: Mapped[str] = mapped_column(String(255), index=True)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organisation_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(48), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    market: Mapped[str | None] = mapped_column(String(128), nullable=True)

    stakeholder_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    decision_authority: Mapped[str] = mapped_column(String(24), default="unknown")
    posture: Mapped[str] = mapped_column(String(24), default="unknown", index=True)

    # Judgements, each with provenance.
    influence_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    influence_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_influence_inferred: Mapped[bool] = mapped_column(Boolean, default=True)

    strategic_importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trust_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    trust_basis: Mapped[str | None] = mapped_column(Text, nullable=True)

    key_interests: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    relationship_owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_engagement_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    next_engagement_due: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    next_engagement_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    confidence: Mapped[str] = mapped_column(String(16), default="low")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RelationshipEdge(Base):
    """A connection between two parties. Directional, evidenced, and
    strength-rated — the substrate for introduction paths."""

    __tablename__ = "relationship_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_type: Mapped[str] = mapped_column(String(24), index=True)  # vecta|stakeholder|partner
    from_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    to_type: Mapped[str] = mapped_column(String(24), index=True)
    to_id: Mapped[str] = mapped_column(String(36), index=True)

    edge_type: Mapped[str] = mapped_column(String(32), default="knows")
    strength: Mapped[int] = mapped_column(Integer, default=50)
    strength_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="low")

    is_vecta_relationship: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_partner_held: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )
    risk_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OpportunityStakeholder(Base):
    """Per-opportunity context. The same person can be a champion on one
    pursuit and a blocker on another."""

    __tablename__ = "opportunity_stakeholders"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "stakeholder_id", name="uq_opp_stakeholder"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    stakeholder_id: Mapped[str] = mapped_column(
        ForeignKey("stakeholders.id", ondelete="CASCADE"), index=True
    )

    role_on_opportunity: Mapped[str | None] = mapped_column(String(48), nullable=True)
    posture: Mapped[str] = mapped_column(String(24), default="unknown")
    engagement_status: Mapped[str] = mapped_column(String(24), default="not_engaged", index=True)
    relevance: Mapped[int] = mapped_column(Integer, default=50)

    last_engagement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Engagement(Base):
    """A single interaction. The timeline is built from these, and the
    Health Score is computed from them — so recording one is what keeps a
    relationship measurable rather than remembered."""

    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    stakeholder_id: Mapped[str] = mapped_column(
        ForeignKey("stakeholders.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    engagement_type: Mapped[str] = mapped_column(String(24), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcome: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    was_initiated_by_vecta: Mapped[bool] = mapped_column(Boolean, default=True)
    received_response: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    commitment_made: Mapped[str | None] = mapped_column(Text, nullable=True)
    commitment_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    commitment_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    follow_up_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RelationshipHealth(Base):
    """Persisted health, with history through `previous_score` so trend is
    answerable without recomputation."""

    __tablename__ = "relationship_health"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    stakeholder_id: Mapped[str] = mapped_column(
        ForeignKey("stakeholders.id", ondelete="CASCADE"), unique=True, index=True
    )

    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    band: Mapped[str] = mapped_column(String(24), default="dormant", index=True)
    band_label: Mapped[str] = mapped_column(String(32), default="Dormant")

    at_risk: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    at_risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trend_direction: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)

    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    contributions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    improvement_levers_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_version: Mapped[str] = mapped_column(String(16), default="1.0")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class IntroductionPath(Base):
    """A route to someone VECTA does not yet know. Cached, since the
    breadth-first search over edges is not worth repeating per page load."""

    __tablename__ = "introduction_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_stakeholder_id: Mapped[str] = mapped_column(
        ForeignKey("stakeholders.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True, index=True
    )

    path_json: Mapped[str] = mapped_column(Text)
    hop_count: Mapped[int] = mapped_column(Integer, default=0)
    weakest_link_strength: Mapped[int] = mapped_column(Integer, default=0)
    is_viable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    expected_win_probability_gain: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RelationshipHealthHistory(Base):
    """Append-only series of health readings.

    Momentum needs a trajectory, not a delta. `80 → 70 → 60` and
    `50 → 70 → 60` both show "down 10" from the previous reading but are
    opposite stories, and only a series can tell them apart.
    """

    __tablename__ = "relationship_health_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    stakeholder_id: Mapped[str] = mapped_column(
        ForeignKey("stakeholders.id", ondelete="CASCADE"), index=True
    )

    score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(24))
    at_risk: Mapped[bool] = mapped_column(Boolean, default=False)

    influence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trust_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    days_since_engagement: Mapped[int | None] = mapped_column(Integer, nullable=True)

    change_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_version: Mapped[str] = mapped_column(String(16), default="1.0")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class StakeholderMilestone(Base):
    """Material moments in a relationship — first meeting, introduction
    made, commitment given, sponsor change.

    Separate from `Engagement` because a milestone is what an executive
    recalls when asked "how did this relationship evolve", and burying
    four of those among two hundred emails makes the question
    unanswerable.
    """

    __tablename__ = "stakeholder_milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    stakeholder_id: Mapped[str] = mapped_column(
        ForeignKey("stakeholders.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )

    milestone_type: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    influence_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    influence_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trust_before: Mapped[str | None] = mapped_column(String(24), nullable=True)
    trust_after: Mapped[str | None] = mapped_column(String(24), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

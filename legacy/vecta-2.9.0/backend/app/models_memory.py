"""Strategic Memory — Phase 3.1.

Executives care about **movement**, not state. "Win probability is 65" is
inert. "Win probability fell 12 points because a competitor secured the
local partner we were pursuing" is a decision trigger.

Three tables:

- `change_event` — the unified feed powering "what changed since
  yesterday". Written by the computed layer, never by AI, so the Briefing
  costs nothing to produce.
- `score_history` — a snapshot per material score change, so a delta can
  always be explained rather than merely observed.
- `assumption_ledger` — assumptions with a lifecycle. This is the highest
  value of the three: an assumption invalidated *since* a decision was
  made is a reason to revisit that decision, and nothing in ATLAS
  currently surfaces it.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .timeutils import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


class Materiality(str, enum.Enum):
    """Only HIGH and MEDIUM reach the Briefing. Without a threshold the
    change feed becomes an activity log, which is the noise this is meant
    to replace."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChangeEventType(str, enum.Enum):
    OPPORTUNITY_CREATED = "opportunity_created"
    CLASSIFICATION_CHANGED = "classification_changed"
    SCORE_CHANGED = "score_changed"
    PRIORITY_CHANGED = "priority_changed"
    FOCUS_CHANGED = "focus_changed"
    QUALIFICATION_CHANGED = "qualification_changed"
    STAGE_CHANGED = "stage_changed"
    EVIDENCE_ADDED = "evidence_added"
    DEADLINE_APPROACHING = "deadline_approaching"
    WENT_STALE = "went_stale"
    ASSUMPTION_INVALIDATED = "assumption_invalidated"
    RELATIONSHIP_CHANGED = "relationship_changed"
    PROFILE_CHANGED = "profile_changed"
    RECOMMENDATION_CHANGED = "recommendation_changed"
    DECISION_RECORDED = "decision_recorded"


class AssumptionStatus(str, enum.Enum):
    ACTIVE = "active"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class ChangeEvent(Base):
    """One material change. The Briefing reads only from here."""

    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    subject_type: Mapped[str] = mapped_column(String(32), index=True)  # opportunity|profile|relationship
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True, index=True
    )

    event_type: Mapped[str] = mapped_column(String(48), index=True)
    materiality: Mapped[str] = mapped_column(String(16), default="medium", index=True)

    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)

    # `time_elapsed` matters: it is how a deadline approaching or an
    # opportunity going stale becomes a change without anything happening.
    triggered_by: Mapped[str] = mapped_column(String(24), default="system")
    # scan | profile_change | manual | time_elapsed | system

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ScoreHistory(Base):
    """Snapshot per material score change, so a delta can be explained."""

    __tablename__ = "score_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(32), index=True)

    score: Mapped[int] = mapped_column(Integer)
    coverage_percent: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    delta_from_previous: Mapped[int | None] = mapped_column(Integer, nullable=True)

    change_reason: Mapped[str] = mapped_column(String(48), default="rescore")
    # rescore | profile_change | manual_override | evidence_added | qualification_change
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str] = mapped_column(String(16), default="2.0")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AssumptionLedger(Base):
    """Assumptions with a lifecycle and a review date.

    An assumption is a claim ATLAS has not verified. Left untracked it
    silently hardens into an accepted fact, and a recommendation resting
    on it becomes indefensible without anyone noticing. `review_due_at`
    forces the question; `status` records the answer.
    """

    __tablename__ = "assumption_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    analysis_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_analysis_items.id", ondelete="SET NULL"), nullable=True
    )

    assumption_text: Mapped[str] = mapped_column(Text)
    basis: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True
    )
    invalidated_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Assumptions decay. An unreviewed assumption is a risk that grows
    # quietly, so it carries an explicit expiry for review.
    review_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    affects_recommendation: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ExecutiveFocus(Base):
    """Persisted Focus Score so the dashboard sorts without recomputing on
    every request — the Briefing has a 1.5s budget."""

    __tablename__ = "executive_focus"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True
    )

    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    raw_score: Mapped[int] = mapped_column(Integer, default=0)
    band: Mapped[str] = mapped_column(String(24), default="no_action", index=True)
    band_label: Mapped[str] = mapped_column(String(48), default="No action needed")

    is_actionable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    primary_drivers: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    contributions_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta: Mapped[int | None] = mapped_column(Integer, nullable=True)

    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str] = mapped_column(String(16), default="1.0")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

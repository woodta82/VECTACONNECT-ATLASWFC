"""Decision Journal and Executive KPIs — Phase 3.1.

The Decision Journal is the piece that turns ATLAS from a record of
commercial *activity* into a record of commercial *reasoning*.

Its value is not the log. It is that a decision made in March becomes
**falsifiable in September**: the recommendation, the evidence, the
assumptions and the expected outcome are all captured at the time, so
when the actual outcome arrives it can be compared against what was
believed. Without that, "we usually get these right" is a feeling.

This is the same discipline applied to predictions in the Phase 3
architecture — a claim that is never checked against reality is not
intelligence, it is confidence. The Journal makes recommendations
checkable.

Three tables:
  - `decision_journal_entry` — one executive decision, with its reasoning
  - `decision_outcome` — what actually happened, recorded later
  - `recommendation_accuracy` — the aggregate learning signal
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .timeutils import utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


class DecisionType(str, enum.Enum):
    PURSUE = "pursue"
    PURSUE_WITH_PARTNER = "pursue_with_partner"
    INFLUENCE_EARLY = "influence_early"
    MONITOR = "monitor"
    DEFER = "defer"
    DECLINE = "decline"
    VERIFY_FIRST = "verify_first"


class DecisionResponse(str, enum.Enum):
    """What the executive did with the recommendation.

    `edited` is the most informative value: it means the recommendation
    was directionally useful but wrong in detail, which is different from
    both acceptance and rejection and should not be collapsed into either.
    """

    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class OutcomeStatus(str, enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    WITHDREW = "withdrew"
    NOT_PURSUED = "not_pursued"
    LAPSED = "lapsed"          # decided to pursue, then nothing happened
    SUPERSEDED = "superseded"


class DecisionJournalEntry(Base):
    """One executive decision, with the reasoning that produced it.

    Append-only. A superseded decision is linked, never overwritten — the
    point is to be able to reconstruct what was believed at the time, and
    an edited record cannot do that.
    """

    __tablename__ = "decision_journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opportunity_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Title is denormalised deliberately: if the opportunity is later
    # deleted, the journal entry must remain readable.

    # --- what ATLAS recommended -----------------------------------------
    recommended_decision: Mapped[str] = mapped_column(String(48), index=True)
    recommendation_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # --- what the executive decided --------------------------------------
    decision: Mapped[str] = mapped_column(String(48), index=True)
    response: Mapped[str] = mapped_column(String(24), index=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- the reasoning, frozen at decision time --------------------------
    # These are snapshots, not references. Reading the live opportunity
    # later would show today's evidence, not what was known when the
    # decision was made — which would make the journal useless for
    # learning.
    evidence_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    scores_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    focus_score_at_decision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    win_probability_at_decision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_at_decision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualification_at_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)

    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- provenance --------------------------------------------------------
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    focus_model_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    # Turnaround: how long between ATLAS recommending and the owner
    # deciding. One of the few genuine measures of whether the platform is
    # accelerating decisions.
    recommended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turnaround_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_journal_entries.id", ondelete="SET NULL"), nullable=True
    )

    # ── Pilot feedback ────────────────────────────────────────────────
    # Two things the objective metrics cannot capture, asked at the moment
    # of decision when the answer is still honest.
    #
    # Acceptance rate says a recommendation was followed. It does not say
    # whether it was *useful* — an executive may accept a recommendation
    # they had already reached themselves, which is agreement without
    # value. And confidence is the platform's whole proposition: a correct
    # recommendation the owner did not trust has not done its job.
    #
    # Optional by design. A required field would be answered carelessly,
    # and careless data is worse than absent data.
    usefulness_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    confidence_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    would_have_reached_alone: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    friction_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcome: Mapped["DecisionOutcome"] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False
    )


class DecisionOutcome(Base):
    """What actually happened. Recorded later, often much later.

    `lessons_learned` is free text on purpose. The structured fields
    support aggregate accuracy; the prose is where the actual insight
    usually lives, and forcing it into categories would lose it.
    """

    __tablename__ = "decision_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("decision_journal_entries.id", ondelete="CASCADE"), unique=True, index=True
    )

    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    actual_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Was the recommendation right? Separate from whether the outcome was
    # good — a correct recommendation to decline still counts as correct.
    recommendation_was_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    correctness_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which assumption failed, where one did. The single most useful field
    # for improving future recommendations.
    failed_assumption: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)

    days_to_outcome: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    entry: Mapped["DecisionJournalEntry"] = relationship(back_populates="outcome")


class RecommendationAccuracy(Base):
    """Aggregate learning signal, computed periodically.

    This is what the AI Learning Loop reads. It is deliberately a computed
    aggregate rather than a live model adjustment: confidence in future
    recommendations should shift on evidence of a pattern, not on the last
    result.
    """

    __tablename__ = "recommendation_accuracy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)

    decision_type: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    # NULL = all decision types aggregated

    total_decisions: Mapped[int] = mapped_column(Integer, default=0)
    outcomes_recorded: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    incorrect: Mapped[int] = mapped_column(Integer, default=0)

    accuracy_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    acceptance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    edit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    mean_turnaround_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Where recommendations fail repeatedly, this names the pattern —
    # which is the input to improving them.
    common_failure_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_adjustment: Mapped[float | None] = mapped_column(Float, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class WeeklyReviewLog(Base):
    """Records that a weekly review happened and what it covered.

    Exists so the Friday review can report on the week honestly — "3 of 5
    reviews completed" is more useful than a rhythm the platform assumes
    was followed.
    """

    __tablename__ = "weekly_review_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    week_starting: Mapped[date] = mapped_column(Date, index=True)
    focus_area: Mapped[str] = mapped_column(String(32), index=True)
    # prioritise | relationships | opportunities | strategy | review

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    decisions_made: Mapped[int] = mapped_column(Integer, default=0)
    actions_recorded: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class BriefingView(Base):
    """One record per briefing open.

    The V1.0 exit review defined ten success metrics and identified the
    tenth — *opened 10 of 10 working days* — as the one that matters,
    because the other nine can all be satisfied by a platform nobody uses.
    That metric was the only one ATLAS could not measure.

    Deliberately minimal: a timestamp, what the briefing contained, and how
    long it took to produce. No click tracking, no dwell time, no
    behavioural profiling. The question is "is this useful enough to open
    every morning", and the answer is a count of mornings.
    """

    __tablename__ = "briefing_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    view_date: Mapped[date] = mapped_column(Date, index=True)

    # What the briefing said, so adoption can be read against usefulness —
    # a briefing opened on a day it had nothing to report is a different
    # signal from one opened on a day it did.
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priorities_shown: Mapped[int] = mapped_column(Integer, default=0)
    changes_shown: Mapped[int] = mapped_column(Integer, default=0)
    decisions_awaiting: Mapped[int] = mapped_column(Integer, default=0)
    was_complete: Mapped[bool] = mapped_column(Boolean, default=False)

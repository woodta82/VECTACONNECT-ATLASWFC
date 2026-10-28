"""phase 3.1: decision journal, KPIs and learning loop

Revision ID: 0006_decision_journal
Revises: 0005_strategic_memory
Create Date: 2026-07-28

Turns ATLAS from a record of commercial activity into a record of
commercial reasoning: what was recommended, what was decided, what was
believed at the time, and what actually happened.

Snapshots are stored as text rather than referenced, deliberately —
reading a live opportunity six months later would show today's evidence,
not what was known when the decision was made.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_decision_journal"
down_revision: Union[str, None] = "0005_strategic_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_journal_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36),
                  sa.ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opportunity_title", sa.Text(), nullable=True),
        sa.Column("recommended_decision", sa.String(48), nullable=False),
        sa.Column("recommendation_rationale", sa.Text(), nullable=True),
        sa.Column("recommendation_confidence", sa.String(16), nullable=True),
        sa.Column("decision", sa.String(48), nullable=False),
        sa.Column("response", sa.String(24), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("evidence_snapshot", sa.Text(), nullable=True),
        sa.Column("assumptions_snapshot", sa.Text(), nullable=True),
        sa.Column("scores_snapshot", sa.Text(), nullable=True),
        sa.Column("focus_score_at_decision", sa.Integer(), nullable=True),
        sa.Column("win_probability_at_decision", sa.Integer(), nullable=True),
        sa.Column("risk_at_decision", sa.Integer(), nullable=True),
        sa.Column("qualification_at_decision", sa.String(32), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("expected_value", sa.Float(), nullable=True),
        sa.Column("expected_decision_date", sa.Date(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("focus_model_version", sa.String(16), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turnaround_hours", sa.Float(), nullable=True),
        sa.Column("superseded_by_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_journal_opportunity", "decision_journal_entries", ["opportunity_id"])
    op.create_index("ix_journal_decided", "decision_journal_entries", ["decided_at"])
    op.create_index("ix_journal_decision", "decision_journal_entries", ["decision"])
    op.create_index("ix_journal_response", "decision_journal_entries", ["response"])
    op.create_index("ix_journal_recommended", "decision_journal_entries", ["recommended_decision"])

    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entry_id", sa.String(36),
                  sa.ForeignKey("decision_journal_entries.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", sa.String(24), server_default="pending"),
        sa.Column("actual_outcome", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("recommendation_was_correct", sa.Boolean(), nullable=True),
        sa.Column("correctness_note", sa.Text(), nullable=True),
        sa.Column("failed_assumption", sa.Text(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("days_to_outcome", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_outcome_status", "decision_outcomes", ["status"])
    op.create_index("ix_outcome_recorded", "decision_outcomes", ["recorded_at"])

    op.create_table(
        "recommendation_accuracy",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("decision_type", sa.String(48), nullable=True),
        sa.Column("total_decisions", sa.Integer(), server_default="0"),
        sa.Column("outcomes_recorded", sa.Integer(), server_default="0"),
        sa.Column("correct", sa.Integer(), server_default="0"),
        sa.Column("incorrect", sa.Integer(), server_default="0"),
        sa.Column("accuracy_rate", sa.Float(), nullable=True),
        sa.Column("acceptance_rate", sa.Float(), nullable=True),
        sa.Column("edit_rate", sa.Float(), nullable=True),
        sa.Column("mean_turnaround_hours", sa.Float(), nullable=True),
        sa.Column("common_failure_pattern", sa.Text(), nullable=True),
        sa.Column("confidence_adjustment", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_accuracy_type", "recommendation_accuracy", ["decision_type"])
    op.create_index("ix_accuracy_computed", "recommendation_accuracy", ["computed_at"])

    op.create_table(
        "weekly_review_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("week_starting", sa.Date(), nullable=False),
        sa.Column("focus_area", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_reviewed", sa.Integer(), server_default="0"),
        sa.Column("decisions_made", sa.Integer(), server_default="0"),
        sa.Column("actions_recorded", sa.Integer(), server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_review_week", "weekly_review_log", ["week_starting"])
    op.create_index("ix_review_area", "weekly_review_log", ["focus_area"])


def downgrade() -> None:
    for table in ("weekly_review_log", "recommendation_accuracy",
                  "decision_outcomes", "decision_journal_entries"):
        op.drop_table(table)

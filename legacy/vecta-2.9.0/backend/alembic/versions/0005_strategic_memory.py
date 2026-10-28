"""phase 3.1: strategic memory and executive focus

Revision ID: 0005_strategic_memory
Revises: 0004_commercial_profile
Create Date: 2026-07-28

Adds the tables behind "what changed since yesterday" and the Executive
Focus Score. All computed — no AI call is required to populate any of
them, which is what makes the daily Briefing free and instant.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_strategic_memory"
down_revision: Union[str, None] = "0004_commercial_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "change_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=True),
        sa.Column("opportunity_id", sa.String(36),
                  sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("materiality", sa.String(16), server_default="medium"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("triggered_by", sa.String(24), server_default="system"),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("profile_version", sa.Integer(), nullable=True),
    )
    op.create_index("ix_change_occurred", "change_events", ["occurred_at"])
    op.create_index("ix_change_materiality", "change_events", ["materiality"])
    op.create_index("ix_change_opportunity", "change_events", ["opportunity_id"])
    op.create_index("ix_change_type", "change_events", ["event_type"])
    op.create_index("ix_change_subject", "change_events", ["subject_type"])

    op.create_table(
        "score_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36),
                  sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("coverage_percent", sa.Integer(), server_default="0"),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("delta_from_previous", sa.Integer(), nullable=True),
        sa.Column("change_reason", sa.String(48), server_default="rescore"),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(16), server_default="2.0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_score_history_opp", "score_history", ["opportunity_id"])
    op.create_index("ix_score_history_dim", "score_history", ["dimension"])
    op.create_index("ix_score_history_at", "score_history", ["recorded_at"])

    op.create_table(
        "assumption_ledger",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36),
                  sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_item_id", sa.String(36),
                  sa.ForeignKey("opportunity_analysis_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assumption_text", sa.Text(), nullable=False),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), server_default="active"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by_evidence_id", sa.String(36),
                  sa.ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invalidated_reason", sa.Text(), nullable=True),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("affects_recommendation", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("profile_version", sa.Integer(), nullable=True),
    )
    op.create_index("ix_assumption_opp", "assumption_ledger", ["opportunity_id"])
    op.create_index("ix_assumption_status", "assumption_ledger", ["status"])
    op.create_index("ix_assumption_review", "assumption_ledger", ["review_due_at"])
    op.create_index("ix_assumption_affects", "assumption_ledger", ["affects_recommendation"])

    op.create_table(
        "executive_focus",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36),
                  sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("score", sa.Integer(), server_default="0"),
        sa.Column("raw_score", sa.Integer(), server_default="0"),
        sa.Column("band", sa.String(24), server_default="no_action"),
        sa.Column("band_label", sa.String(48), server_default="No action needed"),
        sa.Column("is_actionable", sa.Boolean(), server_default=sa.true()),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        sa.Column("primary_drivers", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("contributions_json", sa.Text(), nullable=True),
        sa.Column("previous_score", sa.Integer(), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(16), server_default="1.0"),
        sa.Column("computed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_focus_score", "executive_focus", ["score"])
    op.create_index("ix_focus_band", "executive_focus", ["band"])
    op.create_index("ix_focus_actionable", "executive_focus", ["is_actionable"])
    op.create_index("ix_focus_computed", "executive_focus", ["computed_at"])


def downgrade() -> None:
    for table in ("executive_focus", "assumption_ledger", "score_history", "change_events"):
        op.drop_table(table)

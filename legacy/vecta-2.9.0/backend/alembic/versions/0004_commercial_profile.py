"""phase 3.1: commercial profile

Revision ID: 0004_commercial_profile
Revises: 0003_legacy_backfill
Create Date: 2026-07-28

Creates the Commercial Profile — the definition of VECTA against which
every opportunity is scored.

Additive only. Nothing existing is altered, so scores produced before the
profile existed keep `profile_version = NULL`, which honestly records
"scored before VECTA was defined" rather than back-dating a version that
was not in force.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_commercial_profile"
down_revision: Union[str, None] = "0003_legacy_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commercial_profile",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("strategic_objectives", sa.Text(), nullable=True),
        sa.Column("growth_priorities", sa.Text(), nullable=True),
        sa.Column("revenue_objective", sa.Float(), nullable=True),
        sa.Column("long_term_direction", sa.Text(), nullable=True),
        sa.Column("min_viable_contract_value", sa.Float(), nullable=True),
        sa.Column("target_contract_value", sa.Float(), nullable=True),
        sa.Column("max_mobilisation_exposure", sa.Float(), nullable=True),
        sa.Column("target_gross_margin", sa.Float(), nullable=True),
        sa.Column("min_gross_margin", sa.Float(), nullable=True),
        sa.Column("delivery_capacity_fte", sa.Float(), nullable=True),
        sa.Column("current_workload_pct", sa.Float(), nullable=True),
        sa.Column("risk_appetite", sa.String(24), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("created_reason", sa.Text(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "profile_priority_region",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("market", sa.String(128), nullable=True),
        sa.Column("tier", sa.Integer(), server_default="2"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.UniqueConstraint("profile_id", "region", "market", name="uq_profile_region"),
    )
    op.create_table(
        "profile_priority_account",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("tier", sa.Integer(), server_default="2"),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
    )
    op.create_table(
        "profile_target_type",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commercial_type", sa.String(48), nullable=False),
        sa.Column("priority_weight", sa.Float(), server_default="1.0"),
        sa.UniqueConstraint("profile_id", "commercial_type", name="uq_profile_target_type"),
    )
    op.create_table(
        "profile_capability",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability", sa.String(128), nullable=False),
        sa.Column("strength", sa.Integer(), server_default="50"),
        sa.Column("specialist_count", sa.Integer(), nullable=True),
        sa.Column("is_specialist_scarce", sa.Boolean(), server_default=sa.false()),
        sa.Column("evidence_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("profile_id", "capability", name="uq_profile_capability"),
    )
    op.create_table(
        "profile_partner",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_name", sa.String(255), nullable=False),
        sa.Column("capability", sa.String(255), nullable=True),
        sa.Column("regions", sa.Text(), nullable=True),
        sa.Column("relationship_strength", sa.Integer(), server_default="50"),
        sa.Column("provides_local_entity", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
    )
    op.create_table(
        "profile_exclusion",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exclusion_type", sa.String(32), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_table(
        "profile_route_preference",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("route_to_market", sa.String(48), nullable=False),
        sa.Column("preference", sa.Integer(), server_default="3"),
        sa.UniqueConstraint("profile_id", "route_to_market", name="uq_profile_route"),
    )
    op.create_table(
        "profile_weighting",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.UniqueConstraint("profile_id", "dimension", name="uq_profile_weighting"),
    )
    op.create_table(
        "profile_factor_anchor",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("commercial_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("factor_key", sa.String(64), nullable=False),
        sa.Column("anchor_0", sa.Text(), nullable=True),
        sa.Column("anchor_50", sa.Text(), nullable=True),
        sa.Column("anchor_100", sa.Text(), nullable=True),
        sa.UniqueConstraint("profile_id", "factor_key", name="uq_profile_anchor"),
    )
    op.create_table(
        "profile_change_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_version", sa.Integer(), nullable=True),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("field_path", sa.String(128), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_profile_version", "commercial_profile", ["version"])
    op.create_index("ix_profile_active", "commercial_profile", ["is_active"])
    op.create_index("ix_profile_region_pid", "profile_priority_region", ["profile_id"])
    op.create_index("ix_profile_account_pid", "profile_priority_account", ["profile_id"])
    op.create_index("ix_profile_capability_pid", "profile_capability", ["profile_id"])
    op.create_index("ix_profile_exclusion_type", "profile_exclusion", ["exclusion_type"])
    op.create_index("ix_profile_weighting_pid", "profile_weighting", ["profile_id"])
    op.create_index("ix_profile_changelog_version", "profile_change_log", ["to_version"])

    # Stamp Phase 2 score/priority rows with the profile version that
    # produced them. Nullable: existing rows stay NULL.
    with op.batch_alter_table("score_assessments") as batch:
        batch.add_column(sa.Column("profile_version", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("pursuit_priorities") as batch:
        batch.add_column(sa.Column("profile_version", sa.Integer(), nullable=True))
    op.create_index("ix_score_stale", "score_assessments", ["is_stale"])


def downgrade() -> None:
    op.drop_index("ix_score_stale", table_name="score_assessments")
    with op.batch_alter_table("pursuit_priorities") as batch:
        batch.drop_column("profile_version")
    with op.batch_alter_table("score_assessments") as batch:
        batch.drop_column("is_stale")
        batch.drop_column("profile_version")

    for table in (
        "profile_change_log",
        "profile_factor_anchor",
        "profile_weighting",
        "profile_route_preference",
        "profile_exclusion",
        "profile_partner",
        "profile_capability",
        "profile_target_type",
        "profile_priority_account",
        "profile_priority_region",
        "commercial_profile",
    ):
        op.drop_table(table)

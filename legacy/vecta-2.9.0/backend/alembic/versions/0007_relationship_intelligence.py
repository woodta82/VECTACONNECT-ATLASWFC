"""sprint 2: relationship intelligence

Revision ID: 0007_relationship_intelligence
Revises: 0006_decision_journal
Create Date: 2026-07-28

Turns contacts into intelligence profiles. Additive only — `contacts` is
referenced by three Phase 2 tables and is extended rather than replaced.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_relationship_intelligence"
down_revision: Union[str, None] = "0006_decision_journal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stakeholders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("contact_id", sa.String(255), nullable=True),
        sa.Column("organisation_id", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role_title", sa.String(255), nullable=True),
        sa.Column("organisation_name", sa.String(255), nullable=True),
        sa.Column("seniority", sa.String(48), nullable=True),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("market", sa.String(128), nullable=True),
        sa.Column("stakeholder_type", sa.String(32), nullable=False),
        sa.Column("decision_authority", sa.String(24), nullable=False),
        sa.Column("posture", sa.String(24), nullable=False),
        sa.Column("influence_level", sa.Integer(), nullable=True),
        sa.Column("influence_basis", sa.Text(), nullable=True),
        sa.Column("is_influence_inferred", sa.Boolean(), nullable=False),
        sa.Column("strategic_importance", sa.Integer(), nullable=True),
        sa.Column("trust_level", sa.String(24), nullable=True),
        sa.Column("trust_basis", sa.Text(), nullable=True),
        sa.Column("key_interests", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("relationship_owner", sa.String(255), nullable=True),
        sa.Column("last_engagement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_engagement_due", sa.Date(), nullable=True),
        sa.Column("next_engagement_note", sa.Text(), nullable=True),
        sa.Column("source_evidence_id", sa.String(255), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "relationship_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_type", sa.String(24), nullable=False),
        sa.Column("from_id", sa.String(36), nullable=True),
        sa.Column("to_type", sa.String(24), nullable=False),
        sa.Column("to_id", sa.String(36), nullable=False),
        sa.Column("edge_type", sa.String(32), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False),
        sa.Column("strength_basis", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("is_vecta_relationship", sa.Boolean(), nullable=False),
        sa.Column("is_partner_held", sa.Boolean(), nullable=False),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("evidence_id", sa.String(255), nullable=True),
        sa.Column("risk_note", sa.Text(), nullable=True),
        sa.Column("conflict_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "opportunity_stakeholders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(255), nullable=False),
        sa.Column("stakeholder_id", sa.String(255), nullable=False),
        sa.Column("role_on_opportunity", sa.String(48), nullable=True),
        sa.Column("posture", sa.String(24), nullable=False),
        sa.Column("engagement_status", sa.String(24), nullable=False),
        sa.Column("relevance", sa.Integer(), nullable=False),
        sa.Column("last_engagement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("next_action_due", sa.Date(), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "engagements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stakeholder_id", sa.String(255), nullable=False),
        sa.Column("opportunity_id", sa.String(255), nullable=True),
        sa.Column("engagement_type", sa.String(24), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("was_initiated_by_vecta", sa.Boolean(), nullable=False),
        sa.Column("received_response", sa.Boolean(), nullable=True),
        sa.Column("commitment_made", sa.Text(), nullable=True),
        sa.Column("commitment_due", sa.Date(), nullable=True),
        sa.Column("commitment_met", sa.Boolean(), nullable=True),
        sa.Column("follow_up_action", sa.Text(), nullable=True),
        sa.Column("follow_up_due", sa.Date(), nullable=True),
        sa.Column("follow_up_completed", sa.Boolean(), nullable=False),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "relationship_health",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stakeholder_id", sa.String(255), nullable=False, unique=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(24), nullable=False),
        sa.Column("band_label", sa.String(32), nullable=False),
        sa.Column("at_risk", sa.Boolean(), nullable=False),
        sa.Column("at_risk_reason", sa.Text(), nullable=True),
        sa.Column("previous_score", sa.Integer(), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=True),
        sa.Column("trend_direction", sa.String(24), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("contributions_json", sa.Text(), nullable=True),
        sa.Column("improvement_levers_json", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(16), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "introduction_paths",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_stakeholder_id", sa.String(255), nullable=False),
        sa.Column("opportunity_id", sa.String(255), nullable=True),
        sa.Column("path_json", sa.Text(), nullable=False),
        sa.Column("hop_count", sa.Integer(), nullable=False),
        sa.Column("weakest_link_strength", sa.Integer(), nullable=False),
        sa.Column("is_viable", sa.Boolean(), nullable=False),
        sa.Column("expected_win_probability_gain", sa.Integer(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "relationship_health_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stakeholder_id", sa.String(36),
                  sa.ForeignKey("stakeholders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(24), nullable=False),
        sa.Column("at_risk", sa.Boolean(), server_default=sa.false()),
        sa.Column("influence_score", sa.Integer(), nullable=True),
        sa.Column("trust_level", sa.String(24), nullable=True),
        sa.Column("days_since_engagement", sa.Integer(), nullable=True),
        sa.Column("change_reason", sa.String(48), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(16), server_default="1.0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_health_hist_stakeholder", "relationship_health_history", ["stakeholder_id"])
    op.create_index("ix_health_hist_recorded", "relationship_health_history", ["recorded_at"])

    op.create_table(
        "stakeholder_milestones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stakeholder_id", sa.String(36),
                  sa.ForeignKey("stakeholders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.String(36),
                  sa.ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("milestone_type", sa.String(48), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("influence_before", sa.Integer(), nullable=True),
        sa.Column("influence_after", sa.Integer(), nullable=True),
        sa.Column("trust_before", sa.String(24), nullable=True),
        sa.Column("trust_after", sa.String(24), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_milestone_stakeholder", "stakeholder_milestones", ["stakeholder_id"])
    op.create_index("ix_milestone_occurred", "stakeholder_milestones", ["occurred_at"])

    op.create_index("ix_engagements_created_at", "engagements", ["created_at"])
    op.create_index("ix_engagements_engagement_type", "engagements", ["engagement_type"])
    op.create_index("ix_engagements_occurred_at", "engagements", ["occurred_at"])
    op.create_index("ix_engagements_opportunity_id", "engagements", ["opportunity_id"])
    op.create_index("ix_engagements_outcome", "engagements", ["outcome"])
    op.create_index("ix_engagements_stakeholder_id", "engagements", ["stakeholder_id"])
    op.create_index("ix_introduction_p_computed_at", "introduction_paths", ["computed_at"])
    op.create_index("ix_introduction_p_is_viable", "introduction_paths", ["is_viable"])
    op.create_index("ix_introduction_p_opportunity_id", "introduction_paths", ["opportunity_id"])
    op.create_index("ix_introduction_p_target_stakeholder_id", "introduction_paths", ["target_stakeholder_id"])
    op.create_index("ix_opportunity_st_created_at", "opportunity_stakeholders", ["created_at"])
    op.create_index("ix_opportunity_st_engagement_status", "opportunity_stakeholders", ["engagement_status"])
    op.create_index("ix_opportunity_st_last_engagement_at", "opportunity_stakeholders", ["last_engagement_at"])
    op.create_index("ix_opportunity_st_opportunity_id", "opportunity_stakeholders", ["opportunity_id"])
    op.create_index("ix_opportunity_st_posture", "opportunity_stakeholders", ["posture"])
    op.create_index("ix_opportunity_st_stakeholder_id", "opportunity_stakeholders", ["stakeholder_id"])
    op.create_index("ix_relationship_e_created_at", "relationship_edges", ["created_at"])
    op.create_index("ix_relationship_e_edge_type", "relationship_edges", ["edge_type"])
    op.create_index("ix_relationship_e_evidence_id", "relationship_edges", ["evidence_id"])
    op.create_index("ix_relationship_e_from_id", "relationship_edges", ["from_id"])
    op.create_index("ix_relationship_e_from_type", "relationship_edges", ["from_type"])
    op.create_index("ix_relationship_e_is_vecta_relationship", "relationship_edges", ["is_vecta_relationship"])
    op.create_index("ix_relationship_e_to_id", "relationship_edges", ["to_id"])
    op.create_index("ix_relationship_e_to_type", "relationship_edges", ["to_type"])
    op.create_index("ix_relationship_h_at_risk", "relationship_health", ["at_risk"])
    op.create_index("ix_relationship_h_band", "relationship_health", ["band"])
    op.create_index("ix_relationship_h_computed_at", "relationship_health", ["computed_at"])
    op.create_index("ix_relationship_h_score", "relationship_health", ["score"])
    op.create_index("ix_relationship_h_stakeholder_id", "relationship_health", ["stakeholder_id"])
    op.create_index("ix_relationship_h_trend_direction", "relationship_health", ["trend_direction"])
    op.create_index("ix_stakeholders_contact_id", "stakeholders", ["contact_id"])
    op.create_index("ix_stakeholders_created_at", "stakeholders", ["created_at"])
    op.create_index("ix_stakeholders_full_name", "stakeholders", ["full_name"])
    op.create_index("ix_stakeholders_is_verified", "stakeholders", ["is_verified"])
    op.create_index("ix_stakeholders_last_engagement_at", "stakeholders", ["last_engagement_at"])
    op.create_index("ix_stakeholders_next_engagement_due", "stakeholders", ["next_engagement_due"])
    op.create_index("ix_stakeholders_organisation_id", "stakeholders", ["organisation_id"])
    op.create_index("ix_stakeholders_posture", "stakeholders", ["posture"])
    op.create_index("ix_stakeholders_region", "stakeholders", ["region"])
    op.create_index("ix_stakeholders_relationship_owner", "stakeholders", ["relationship_owner"])
    op.create_index("ix_stakeholders_source_evidence_id", "stakeholders", ["source_evidence_id"])
    op.create_index("ix_stakeholders_stakeholder_type", "stakeholders", ["stakeholder_type"])


def downgrade() -> None:
    for table in ("stakeholder_milestones", "relationship_health_history",
                  "introduction_paths", "relationship_health", "engagements",
                  "opportunity_stakeholders", "relationship_edges", "stakeholders"):
        op.drop_table(table)

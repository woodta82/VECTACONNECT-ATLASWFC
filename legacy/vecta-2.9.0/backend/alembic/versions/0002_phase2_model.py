"""phase 2: normalised intelligence model

Revision ID: 0002_phase2_model
Revises: 0001_baseline
Create Date: 2026-07-27

Creates the Phase 2 structure: classification columns on `opportunities`,
plus seventeen normalised tables for evidence, claim links, analysis
items, four-dimension scoring, pursuit priority, qualification, commercial
value, AI parse failures, legacy preservation and the override audit.

Additive only — no existing column is altered or dropped, so an in-place
upgrade of a live database cannot lose data. `downgrade()` is complete and
reverses everything this revision creates.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_model"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts(nullable: bool = True) -> sa.Column:
    return sa.DateTime(timezone=True)


def upgrade() -> None:
    # ---------------------------------------------------- opportunities
    with op.batch_alter_table("opportunities") as batch:
        batch.add_column(sa.Column("classification", sa.String(48), nullable=True))
        batch.add_column(sa.Column("classification_rationale", sa.Text(), nullable=True))
        batch.add_column(sa.Column("primary_vertical", sa.String(32), nullable=True))
        batch.add_column(sa.Column("vertical_rationale", sa.Text(), nullable=True))
        batch.add_column(sa.Column("primary_commercial_type", sa.String(48), nullable=True))
        batch.add_column(sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("verification_confidence", sa.String(16), nullable=True))
        batch.add_column(
            sa.Column("requires_human_review", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("human_review_reason", sa.Text(), nullable=True))

    op.create_index("ix_opportunities_classification", "opportunities", ["classification"])
    op.create_index("ix_opportunities_primary_vertical", "opportunities", ["primary_vertical"])
    op.create_index(
        "ix_opportunities_primary_commercial_type", "opportunities", ["primary_commercial_type"]
    )
    op.create_index(
        "ix_opportunities_requires_human_review", "opportunities", ["requires_human_review"]
    )

    # --------------------------------------------------------- evidence
    op.create_table(
        "opportunity_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("page_title", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("source_tier", sa.String(16), nullable=False),
        sa.Column("evidence_type", sa.String(48), server_default="other"),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("no_publication_date_reason", sa.Text(), nullable=True),
        sa.Column("date_accessed", sa.DateTime(timezone=True)),
        sa.Column("url_validation_status", sa.String(24), server_default="not_reviewed"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_unavailable", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_official_source", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_definitive", sa.Boolean(), server_default=sa.false()),
        sa.Column("confidence", sa.String(16), server_default="medium"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.false()),
    )
    op.create_index("ix_evidence_opportunity", "opportunity_evidence", ["opportunity_id"])
    op.create_index("ix_evidence_tier", "opportunity_evidence", ["source_tier"])
    op.create_index("ix_evidence_validation", "opportunity_evidence", ["url_validation_status"])
    op.create_index("ix_evidence_official", "opportunity_evidence", ["is_official_source"])
    op.create_index("ix_evidence_confidence", "opportunity_evidence", ["confidence"])

    op.create_table(
        "evidence_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("opportunity_evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_type", sa.String(48), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("evidence_id", "claim_type", name="uq_evidence_claim"),
    )
    op.create_index("ix_evidence_claims_evidence", "evidence_claims", ["evidence_id"])
    op.create_index("ix_evidence_claims_type", "evidence_claims", ["claim_type"])

    # --------------------------------------------------------- analysis
    op.create_table(
        "opportunity_analysis_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(48), nullable=True),
        sa.Column("supporting_evidence_id", sa.String(36), sa.ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("is_completed", sa.Boolean(), server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(16), server_default="ai"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_analysis_opportunity", "opportunity_analysis_items", ["opportunity_id"])
    op.create_index("ix_analysis_type", "opportunity_analysis_items", ["item_type"])
    op.create_index("ix_analysis_verified", "opportunity_analysis_items", ["is_verified"])

    # ---------------------------------------------------------- scoring
    op.create_table(
        "score_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer(), server_default="0"),
        sa.Column("coverage", sa.Float(), server_default="0"),
        sa.Column("coverage_percent", sa.Integer(), server_default="0"),
        sa.Column("coverage_band", sa.String(24), server_default="insufficient"),
        sa.Column("risk_established", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("manual_score", sa.Integer(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(16), server_default="2.0"),
        sa.Column("last_scored_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("opportunity_id", "dimension", name="uq_opportunity_dimension"),
    )
    op.create_index("ix_score_opportunity", "score_assessments", ["opportunity_id"])
    op.create_index("ix_score_dimension", "score_assessments", ["dimension"])
    op.create_index("ix_score_value", "score_assessments", ["score"])
    op.create_index("ix_score_coverage_band", "score_assessments", ["coverage_band"])
    op.create_index("ix_score_risk_established", "score_assessments", ["risk_established"])

    op.create_table(
        "score_factors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("score_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("factor_key", sa.String(64), nullable=False),
        sa.Column("factor_label", sa.String(128), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("scored", sa.Boolean(), server_default=sa.false()),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("supporting_evidence_id", sa.String(36), sa.ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("assessment_id", "factor_key", name="uq_assessment_factor"),
    )
    op.create_index("ix_score_factors_assessment", "score_factors", ["assessment_id"])
    op.create_index("ix_score_factors_key", "score_factors", ["factor_key"])

    op.create_table(
        "pursuit_priorities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("base_score", sa.Float(), server_default="0"),
        sa.Column("inverse_risk", sa.Float(), server_default="0"),
        sa.Column("urgency_adjustment", sa.Float(), server_default="0"),
        sa.Column("uncapped_score", sa.Integer(), server_default="0"),
        sa.Column("final_score", sa.Integer(), server_default="0"),
        sa.Column("band", sa.String(24), server_default="low"),
        sa.Column("band_label", sa.String(48), server_default="Low Priority"),
        sa.Column("coverage_restricted", sa.Boolean(), server_default=sa.false()),
        sa.Column("qualification_restricted", sa.Boolean(), server_default=sa.false()),
        sa.Column("restriction_explanation", sa.Text(), nullable=True),
        sa.Column("weights_used", sa.JSON(), nullable=True),
        sa.Column("model_version", sa.String(16), server_default="2.0"),
        sa.Column("calculated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_priority_final", "pursuit_priorities", ["final_score"])
    op.create_index("ix_priority_band", "pursuit_priorities", ["band"])
    op.create_index("ix_priority_coverage_restricted", "pursuit_priorities", ["coverage_restricted"])
    op.create_index("ix_priority_qual_restricted", "pursuit_priorities", ["qualification_restricted"])

    # ---------------------------------------------------- qualification
    op.create_table(
        "qualification_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("state", sa.String(32), server_default="not_assessed"),
        sa.Column("has_absolute_disqualifier", sa.Boolean(), server_default=sa.false()),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(16), server_default="2.0"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_qual_state", "qualification_assessments", ["state"])
    op.create_index("ix_qual_absolute", "qualification_assessments", ["has_absolute_disqualifier"])

    op.create_table(
        "qualification_checklist_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("qualification_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_key", sa.String(64), nullable=False),
        sa.Column("item_label", sa.String(128), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default=sa.false()),
        sa.Column("answer", sa.String(24), server_default="unknown"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(16), server_default="ai"),
        sa.UniqueConstraint("assessment_id", "item_key", name="uq_assessment_item"),
    )
    op.create_index("ix_qual_items_assessment", "qualification_checklist_items", ["assessment_id"])
    op.create_index("ix_qual_items_answer", "qualification_checklist_items", ["answer"])

    op.create_table(
        "qualification_blockers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("qualification_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("failure_type", sa.String(48), nullable=False),
        sa.Column("item_key", sa.String(64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), server_default=sa.false()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_blockers_assessment", "qualification_blockers", ["assessment_id"])
    op.create_index("ix_blockers_type", "qualification_blockers", ["failure_type"])
    op.create_index("ix_blockers_resolved", "qualification_blockers", ["is_resolved"])

    op.create_table(
        "qualification_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("qualification_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_state", sa.String(32), nullable=False),
        sa.Column("new_state", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_qual_overrides_assessment", "qualification_overrides", ["assessment_id"])

    # ------------------------------------------------- commercial value
    op.create_table(
        "commercial_values",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("published_programme_value", sa.Float(), nullable=True),
        sa.Column("published_contract_value", sa.Float(), nullable=True),
        sa.Column("estimated_contract_min", sa.Float(), nullable=True),
        sa.Column("estimated_contract_max", sa.Float(), nullable=True),
        sa.Column("estimated_vecta_revenue", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("value_status", sa.String(48), server_default="insufficient_evidence"),
        sa.Column("estimate_methodology", sa.Text(), nullable=True),
        sa.Column("source_evidence_id", sa.String(36), sa.ForeignKey("opportunity_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("partner_share_assumption", sa.Float(), nullable=True),
        sa.Column("is_legacy_unverified", sa.Boolean(), server_default=sa.false()),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_value_status", "commercial_values", ["value_status"])
    op.create_index("ix_value_legacy", "commercial_values", ["is_legacy_unverified"])
    op.create_index("ix_value_confidence", "commercial_values", ["confidence"])

    # ---------------------------------------------------- AI processing
    op.create_table(
        "ai_parse_failures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_run_id", sa.String(36), sa.ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(16), server_default="2.0"),
        sa.Column("parse_status", sa.String(32), server_default="parsing_failed"),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("proposed_title", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_parse_failures_scan", "ai_parse_failures", ["scan_run_id"])
    op.create_index("ix_parse_failures_status", "ai_parse_failures", ["parse_status"])
    op.create_index("ix_parse_failures_created", "ai_parse_failures", ["created_at"])

    # ----------------------------------------------------------- legacy
    op.create_table(
        "legacy_opportunity_data",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("legacy_alignment_score", sa.Integer(), nullable=True),
        sa.Column("legacy_score_breakdown", sa.JSON(), nullable=True),
        sa.Column("legacy_vertical", sa.String(32), nullable=True),
        sa.Column("legacy_value_estimate", sa.Float(), nullable=True),
        sa.Column("legacy_currency", sa.String(8), nullable=True),
        sa.Column("vertical_mapping_status", sa.String(32), server_default="mapped"),
        sa.Column("vertical_requires_review", sa.Boolean(), server_default=sa.false()),
        sa.Column("migration_version", sa.String(16), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_legacy_review", "legacy_opportunity_data", ["vertical_requires_review"])
    op.create_index("ix_legacy_mapping", "legacy_opportunity_data", ["vertical_mapping_status"])

    # ------------------------------------------------------------ audit
    op.create_table(
        "override_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_path", sa.String(128), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("updated_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_override_opportunity", "override_audits", ["opportunity_id"])
    op.create_index("ix_override_field", "override_audits", ["field_path"])
    op.create_index("ix_override_created", "override_audits", ["created_at"])

    # ------------------------------- multi-valued classification tables
    op.create_table(
        "opportunity_contributing_verticals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vertical", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), server_default="ai"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("opportunity_id", "vertical", name="uq_opp_contributing_vertical"),
    )
    op.create_index("ix_contrib_vertical_opp", "opportunity_contributing_verticals", ["opportunity_id"])
    op.create_index("ix_contrib_vertical", "opportunity_contributing_verticals", ["vertical"])

    op.create_table(
        "opportunity_secondary_commercial_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commercial_type", sa.String(48), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), server_default="ai"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("opportunity_id", "commercial_type", name="uq_opp_secondary_type"),
    )
    op.create_index("ix_secondary_type_opp", "opportunity_secondary_commercial_types", ["opportunity_id"])
    op.create_index("ix_secondary_type", "opportunity_secondary_commercial_types", ["commercial_type"])

    op.create_table(
        "opportunity_routes_to_market",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("route", sa.String(48), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_satisfied", sa.Boolean(), server_default=sa.false()),
        sa.Column("source", sa.String(16), server_default="ai"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("opportunity_id", "route", name="uq_opp_route"),
    )
    op.create_index("ix_route_opp", "opportunity_routes_to_market", ["opportunity_id"])
    op.create_index("ix_route", "opportunity_routes_to_market", ["route"])


def downgrade() -> None:
    """Complete reversal. Phase 2 data is lost by design — that is what a
    downgrade means here — but no pre-Phase-2 column is touched, so the
    v2.8/RC1 dataset survives intact."""
    for table in (
        "opportunity_routes_to_market",
        "opportunity_secondary_commercial_types",
        "opportunity_contributing_verticals",
        "override_audits",
        "legacy_opportunity_data",
        "ai_parse_failures",
        "commercial_values",
        "qualification_overrides",
        "qualification_blockers",
        "qualification_checklist_items",
        "qualification_assessments",
        "pursuit_priorities",
        "score_factors",
        "score_assessments",
        "opportunity_analysis_items",
        "evidence_claims",
        "opportunity_evidence",
    ):
        op.drop_table(table)

    for idx in (
        "ix_opportunities_requires_human_review",
        "ix_opportunities_primary_commercial_type",
        "ix_opportunities_primary_vertical",
        "ix_opportunities_classification",
    ):
        op.drop_index(idx, table_name="opportunities")

    with op.batch_alter_table("opportunities") as batch:
        for col in (
            "human_review_reason",
            "requires_human_review",
            "verification_confidence",
            "last_verified_at",
            "primary_commercial_type",
            "vertical_rationale",
            "primary_vertical",
            "classification_rationale",
            "classification",
        ):
            batch.drop_column(col)

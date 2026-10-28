"""v1.0: briefing view tracking for pilot adoption measurement

Revision ID: 0008_briefing_views
Revises: 0007_relationship_intelligence
Create Date: 2026-07-28

Adds the only pilot metric ATLAS could not measure: whether the briefing
is actually opened. Deliberately minimal — a timestamp and what the
briefing contained. No click tracking or behavioural profiling.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_briefing_views"
down_revision: Union[str, None] = "0007_relationship_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "briefing_views",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_date", sa.Date(), nullable=False),
        sa.Column("generation_ms", sa.Integer(), nullable=True),
        sa.Column("priorities_shown", sa.Integer(), server_default="0"),
        sa.Column("changes_shown", sa.Integer(), server_default="0"),
        sa.Column("decisions_awaiting", sa.Integer(), server_default="0"),
        sa.Column("was_complete", sa.Boolean(), server_default=sa.false()),
    )
    op.create_index("ix_briefing_view_at", "briefing_views", ["viewed_at"])
    op.create_index("ix_briefing_view_date", "briefing_views", ["view_date"])


def downgrade() -> None:
    op.drop_table("briefing_views")

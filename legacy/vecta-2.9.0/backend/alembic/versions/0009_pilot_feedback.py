"""v1.0: pilot feedback capture on decisions

Revision ID: 0009_pilot_feedback
Revises: 0008_briefing_views
Create Date: 2026-07-28

Adds the two subjective measures the objective KPIs cannot provide:
whether a recommendation was useful, and whether it was trusted.

`would_have_reached_alone` is the most informative of the three. A
recommendation the executive would have reached unaided is agreement
without value — and a platform scoring 90% acceptance on advice its user
already knew has measured its own redundancy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_pilot_feedback"
down_revision: Union[str, None] = "0008_briefing_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decision_journal_entries") as batch:
        batch.add_column(sa.Column("usefulness_rating", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("confidence_rating", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("would_have_reached_alone", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("friction_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("decision_journal_entries") as batch:
        batch.drop_column("friction_note")
        batch.drop_column("would_have_reached_alone")
        batch.drop_column("confidence_rating")
        batch.drop_column("usefulness_rating")

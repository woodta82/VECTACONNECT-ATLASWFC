"""Relationship intelligence to the ATLAS v1.0 parameters with open-market contact discovery (29 Oct 2026): stakeholder
judgements, engagement outcomes and direction, contact discoveries and their people, research documents scoped to a
discovery, outreach drafts. Additive; carries existing values over.

Revision ID: wfc_0013
Revises: wfc_0012
Create Date: 2026-10-29

Executes migrations/sql/wfc_0013_open_market_relationships.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0013"
down_revision = "wfc_0012"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0013_open_market_relationships.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0013 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

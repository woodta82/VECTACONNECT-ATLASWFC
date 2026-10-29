"""Refocus on global opportunity discovery and relationship intelligence (28 Oct 2026): record types, the
New/Reviewing/Pursuing/On hold/Closed progress flow, notes, saved opportunities and next actions; people research facts,
evidence, opportunity links, existing relationships, introduction routes, research runs. Additive; carries existing values over.

Revision ID: wfc_0011
Revises: wfc_0010
Create Date: 2026-10-28

Executes migrations/sql/wfc_0011_relationship_intelligence.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0011"
down_revision = "wfc_0010"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0011_relationship_intelligence.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0011 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

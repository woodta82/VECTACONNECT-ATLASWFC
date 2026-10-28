"""Amendments of 26 October 2026: complete reading of long documents in
sections with resume, structured eligibility, document-wide contradictions,
discovery link queue, revalidation of migrated deadlines.

Revision ID: wfc_0004
Revises: wfc_0003
Create Date: 2026-10-26

Executes migrations/sql/wfc_0004_amendments.sql, the same file the PostgreSQL
test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0004"
down_revision = "wfc_0003"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0004_amendments.sql").read_text())
    conn.execute((SQL_DIR / "wfc_0004_legacy_deadlines.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0004 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

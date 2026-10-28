"""Freight relevance, document-wide geography conflicts, status basis and
validation rules v4 (27 Oct 2026, second instruction).

Revision ID: wfc_0007
Revises: wfc_0006
Create Date: 2026-10-27

Executes migrations/sql/wfc_0007_relevance_v4.sql, the same file the
PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0007"
down_revision = "wfc_0006"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0007_relevance_v4.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0007 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

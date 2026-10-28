"""Freight relevance at the meaning level, announced vs open status, route and
road-feeder rules, validation rules v5 (27 Oct 2026, third instruction).

Revision ID: wfc_0008
Revises: wfc_0007
Create Date: 2026-10-27

Executes migrations/sql/wfc_0008_meaning_relevance_v5.sql, the same file the
PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0008"
down_revision = "wfc_0007"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0008_meaning_relevance_v5.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0008 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

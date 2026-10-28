"""Status chronology (retrieval never supersedes a dated status), terminal-only records as historical
intelligence, supporting tender context, validation rules v7 (27 Oct 2026, fifth instruction).

Revision ID: wfc_0010
Revises: wfc_0009
Create Date: 2026-10-27

Executes migrations/sql/wfc_0010_status_chronology_v7.sql, the same file the
PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0010"
down_revision = "wfc_0009"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0010_status_chronology_v7.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0010 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

"""Status freshness, truthful publication dates, route-launch capability area,
excluded passenger lots, validation rules v6 (27 Oct 2026, fourth instruction).

Revision ID: wfc_0009
Revises: wfc_0008
Create Date: 2026-10-27

Executes migrations/sql/wfc_0009_status_freshness_v6.sql, the same file the
PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0009"
down_revision = "wfc_0008"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0009_status_freshness_v6.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0009 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

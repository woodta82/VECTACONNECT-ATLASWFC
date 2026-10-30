"""One workspace, staged resumable research, global airport directory, cargo scope, canonical company and person records (30 Oct 2026).
Additive.

Revision ID: wfc_0016
Revises: wfc_0015
Create Date: 2026-10-30

Executes migrations/sql/wfc_0016_workspace_research.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0016"
down_revision = "wfc_0015"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0016_workspace_research.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0016 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

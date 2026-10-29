"""Four research purposes, company and people intelligence built directly, supplied data awaiting verification (29 Oct 2026).
Additive.

Revision ID: wfc_0015
Revises: wfc_0014
Create Date: 2026-10-29

Executes migrations/sql/wfc_0015_company_intelligence.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0015"
down_revision = "wfc_0014"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0015_company_intelligence.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0015 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

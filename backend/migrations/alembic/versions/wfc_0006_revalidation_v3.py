"""Validation rules v3 (27 Oct 2026): re-check of material-field assessments
made under earlier rules.

Revision ID: wfc_0006
Revises: wfc_0005
Create Date: 2026-10-27

Executes migrations/sql/wfc_0006_revalidation_v3.sql, the same file the
PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0006"
down_revision = "wfc_0005"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0006_revalidation_v3.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0006 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

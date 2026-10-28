"""Relationship-level eligibility validation (26 Oct 2026, evening): validation
version on field assessments, re-check of records assessed under earlier rules,
review flags on affected opportunities.

Revision ID: wfc_0005
Revises: wfc_0004
Create Date: 2026-10-26

Executes migrations/sql/wfc_0005_validation_version.sql, the same file the
PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0005"
down_revision = "wfc_0004"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0005_validation_version.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0005 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

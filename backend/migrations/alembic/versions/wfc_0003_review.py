"""Full build review and amendments (26 October 2026): deadline precision,
cumulative per-run AI budgets, truthful run completion, publication-date
provenance, resumable coverage, referral attribution, fit reassessment.

Revision ID: wfc_0003
Revises: wfc_0002
Create Date: 2026-10-26

Executes migrations/sql/wfc_0003_review.sql, the same file the PostgreSQL
test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0003"
down_revision = "wfc_0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute((SQL_DIR / "wfc_0003_review.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0003 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

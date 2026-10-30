"""Contact currency (historical and conflicting addresses) and truthful stage outcomes (complete with unresolved failures) (30 Oct 2026). Additive.

Revision ID: wfc_0018
Revises: wfc_0017
Create Date: 2026-10-30

Executes migrations/sql/wfc_0018_contact_currency.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0018"
down_revision = "wfc_0017"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0018_contact_currency.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0018 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

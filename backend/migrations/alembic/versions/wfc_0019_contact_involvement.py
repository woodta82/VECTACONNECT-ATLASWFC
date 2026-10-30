"""A person's evidenced involvement (employee, appointed representative, external adviser, press contact, unresolved) (30 Oct 2026). Additive.

Revision ID: wfc_0019
Revises: wfc_0018
Create Date: 2026-10-30

Executes migrations/sql/wfc_0019_contact_involvement.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0019"
down_revision = "wfc_0018"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0019_contact_involvement.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0019 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

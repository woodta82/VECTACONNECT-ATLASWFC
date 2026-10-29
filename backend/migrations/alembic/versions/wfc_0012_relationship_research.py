"""Complete, evidence-backed relationship research (28 Oct 2026, second continuation): research documents and their
sectioned, resumable reading; research outcome and coverage; evidence that binds a person to a role and an organisation;
evidence-backed roles; possible duplicates and reversible merges. Additive; carries existing values over.

Revision ID: wfc_0012
Revises: wfc_0011
Create Date: 2026-10-28

Executes migrations/sql/wfc_0012_relationship_research.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0012"
down_revision = "wfc_0011"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0012_relationship_research.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0012 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

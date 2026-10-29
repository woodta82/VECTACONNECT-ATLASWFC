"""Open-web discovery as the default (29 Oct 2026): the web_search source type and the built-in "Open web" source; per-document
publisher family and authority; access restrictions. Additive.

Revision ID: wfc_0014
Revises: wfc_0013
Create Date: 2026-10-29

Executes migrations/sql/wfc_0014_open_web_discovery.sql, the same file the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0014"
down_revision = "wfc_0013"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def upgrade() -> None:
    conn = op.get_bind().connection.driver_connection
    conn.execute((SQL_DIR / "wfc_0014_open_web_discovery.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0014 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

"""WFC lineage: complete initial schema for an EMPTY database.

Revision ID: wfc_0001
Revises:
Create Date: 2026-10-26

Executes migrations/sql/wfc_0001_schema.sql verbatim, the same file the
PostgreSQL test suite applies to a clean server. It refuses to run on a
database that already has tables (for example a VECTA 2.9.0 database):
the legacy adoption path is a separate, documented procedure, never a
stamp.
"""
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "wfc_0001"
down_revision = None
branch_labels = ("wfc",)
depends_on = None

SQL = Path(__file__).resolve().parents[2] / "sql" / "wfc_0001_schema.sql"


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    )).scalar()
    if existing:
        raise RuntimeError(
            f"wfc_0001 requires an empty database; found {existing} existing table(s). "
            "See docs/MIGRATIONS.md for the legacy adoption procedure."
        )
    # Run through the psycopg connection WITHOUT parameters, so the multi-
    # statement script (DO blocks, '%' in LIKE patterns) uses the simple
    # query protocol and is not reinterpreted by a paramstyle.
    raw = bind.connection.driver_connection
    raw.execute(SQL.read_text())


def downgrade() -> None:
    # Downgrade is not a data-recovery strategy. Restore from backup instead
    # (docs/RESTORE_RUNBOOK.md). This only exists for empty test databases.
    op.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")

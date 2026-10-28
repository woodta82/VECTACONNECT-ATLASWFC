"""Completion directive (26 October 2026): geography, source management,
country discovery, per-field claim validation, tender identity, review
queue, opportunity scope, remaining imports.

Revision ID: wfc_0002
Revises: wfc_0001
Create Date: 2026-10-26

Executes migrations/sql/wfc_0002_directive.sql and the generated geography
seed, the same files the PostgreSQL test suite applies.
"""
from pathlib import Path

from alembic import op

revision = "wfc_0002"
down_revision = "wfc_0001"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
FILES = ("wfc_0002_directive.sql", "wfc_0002_geography_seed.sql")


def upgrade() -> None:
    raw = op.get_bind().connection.driver_connection
    for name in FILES:
        raw.execute((SQL_DIR / name).read_text())


def downgrade() -> None:
    raise RuntimeError("wfc_0002 has no downgrade; restore from backup (docs/RESTORE_RUNBOOK.md)")

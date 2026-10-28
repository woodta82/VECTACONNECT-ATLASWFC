"""baseline: existing v2.8/RC1 schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-27

BASELINE STRATEGY
=================
This revision is intentionally a NO-OP.

The production database already contains the full v2.8/RC1 schema, created
by SQLAlchemy's `create_all()` before Alembic existed. Writing those tables
out as CREATE statements here would mean either failing against production
(tables already exist) or being unable to build a database from scratch —
so instead this revision represents "whatever `create_all()` produced",
and is applied one of two ways:

  EXISTING DATABASE (production):
      alembic stamp 0001_baseline
  ...which records the revision without executing it, then:
      alembic upgrade head
  ...applies only the Phase 2 changes.

  CLEAN DATABASE:
      python -c "from app.database import Base, engine; import app.models; \\
                 Base.metadata.create_all(bind=engine)"
      alembic stamp 0001_baseline
      alembic upgrade head
  ...or simply `create_all()` alone, which now includes the Phase 2 tables
  since models_phase2 is registered on Base.metadata; then stamp head.

From this revision onward Alembic is authoritative: no new schema change
may be introduced via startup ALTER TABLE.
"""
from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — see the module docstring. The pre-existing
    # schema is adopted by `alembic stamp 0001_baseline`.
    pass


def downgrade() -> None:
    # Nothing to undo: this revision never created anything.
    pass

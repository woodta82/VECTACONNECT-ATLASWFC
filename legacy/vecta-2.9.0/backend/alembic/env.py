"""Alembic migration environment for ATLAS.

Reads the database URL from the application settings (i.e. the
DATABASE_URL environment variable) rather than alembic.ini, so production
credentials are never committed.

`render_as_batch` is enabled for SQLite: SQLite cannot ALTER most column
properties in place, and Alembic's batch mode works around that by
rebuilding the table. Without it the migration test suite — which runs on
SQLite — could not exercise the same migration files that run against
production Postgres, and testing a *different* migration path than the one
that ships would defeat the point.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base

# Import the models module so every table is registered on Base.metadata
# before autogenerate compares against it.
from app import models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_sqlite() -> bool:
    return settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite(),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

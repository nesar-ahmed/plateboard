"""Alembic environment: async engine, settings-driven URL, SQLite-friendly.

Two deliberate choices:

* The DSN comes from :func:`app.core.config.get_settings`, never from
  ``alembic.ini``, so migrations and the running app can never point at
  different databases (and credentials stay out of version control).
* ``render_as_batch`` is enabled for SQLite because SQLite cannot ``ALTER``
  most constraints; Alembic then emits the documented
  ``batch_alter_table`` "recreate" dance automatically.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.db import build_engine, is_sqlite
from app.models import Base

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, **extra: object) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER columns in place, so autogenerate must emit
        # `with op.batch_alter_table(...)` blocks instead of plain ALTERs.
        render_as_batch=is_sqlite(settings.DATABASE_URL),
        compare_type=True,
        # Server defaults on SQLite (CURRENT_TIMESTAMP) are reported as
        # "changed" on every run; comparing them creates noise, not signal.
        compare_server_default=False,
        version_table="alembic_version",
        include_schemas=False,
        **extra,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    _configure(
        url=settings.resolved_database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against the live database through the async engine."""
    settings.ensure_sqlite_dir()
    engine = build_engine(settings.resolved_database_url, echo=settings.SQL_ECHO)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
            # `run_sync` executes inside the migration transaction that
            # `context.begin_transaction()` opened; commit on the connection.
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

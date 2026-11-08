"""Alembic environment: async engine, settings-driven URL, SQLite-friendly.

Three deliberate choices:

* The DSN comes from :func:`app.core.config.get_settings`, never from
  ``alembic.ini``, so migrations and the running app can never point at
  different databases (and credentials stay out of version control).
* ``render_as_batch`` is enabled for SQLite because SQLite cannot ``ALTER``
  most constraints; Alembic then emits the documented
  ``batch_alter_table`` "recreate" dance automatically.
* New revisions get the next sequential 4-digit id (``0005``, ``0006``, ...)
  instead of Alembic's random hex, matching the existing chain and the
  ``%(rev)s_%(slug)s`` file template in ``alembic.ini``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.operations import MigrationScript
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.db import build_engine, is_sqlite
from app.models import Base

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Width of the zero-padded sequential revision ids (``0001`` ... ``9999``).
REVISION_ID_WIDTH = 4

#: Shape of the id Alembic generates when none is given (``uuid4().hex[-12:]``).
_ALEMBIC_RANDOM_ID = re.compile(r"[0-9a-f]{12}")


def next_revision_id(existing: Iterable[str]) -> str:
    """The id after the highest numeric one in ``existing`` (``0001`` if none).

    Non-numeric ids (none today) are ignored rather than breaking numbering.
    """
    numbers = [int(rev) for rev in existing if rev.isdigit()]
    return f"{max(numbers, default=0) + 1:0{REVISION_ID_WIDTH}d}"


def _sequential_revision_id(
    _context: Any, _revision: Any, directives: list[MigrationScript]
) -> None:
    """``process_revision_directives`` hook: replace the random hex id.

    Numbering considers *every* known revision (not just heads), so an id is
    never reused. An explicit id wins - ``alembic revision --rev-id ...`` on
    the CLI or ``command.revision(..., rev_id=...)`` in code - so only ids
    shaped like Alembic's auto-generated ones are replaced.
    """
    if not directives:
        return
    script = directives[0]
    cmd_opts = config.cmd_opts
    if cmd_opts is not None and getattr(cmd_opts, "rev_id", None):
        return
    if not _ALEMBIC_RANDOM_ID.fullmatch(script.rev_id or ""):
        return
    scripts = ScriptDirectory.from_config(config)
    script.rev_id = next_revision_id(
        revision.revision for revision in scripts.walk_revisions()
    )


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
        process_revision_directives=_sequential_revision_id,
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

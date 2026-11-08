"""Async engine, session factory and the SQLite specifics.

The rest of the codebase only ever talks to :func:`get_sessionmaker` /
:data:`AsyncSession`, so moving from SQLite to PostgreSQL is a one-line
``DATABASE_URL`` change.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.shared.text import FOLD_SQL_FUNCTION, fold_text

logger = logging.getLogger(__name__)

_SQLITE_MEMORY_MARKERS = (":memory:", "mode=memory")


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def is_memory_sqlite(url: str) -> bool:
    return is_sqlite(url) and any(marker in url for marker in _SQLITE_MEMORY_MARKERS)


def _apply_sqlite_pragmas(engine: AsyncEngine, *, file_based: bool) -> None:
    """Turn on the SQLite settings a relational app actually expects.

    * ``foreign_keys`` is OFF by default in SQLite - without this, FKs are
      documentation only.
    * WAL + ``busy_timeout`` stop "database is locked" errors when the seed
      script or several workers touch the same file.
    * ``fold()`` - accent/case folding for search (``app.shared.text``);
      SQLite's built-in ``lower()`` only folds ASCII.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(
        dbapi_connection: object, _record: object
    ) -> None:  # pragma: no cover - glue
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            if file_based:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
        # deterministic=True lets SQLite treat it like a pure built-in.
        dbapi_connection.create_function(  # type: ignore[attr-defined]
            FOLD_SQL_FUNCTION, 1, fold_text, deterministic=True
        )


def build_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an :class:`AsyncEngine` for any SQLAlchemy URL."""
    kwargs: dict[str, object] = {"echo": echo}

    if is_sqlite(url):
        # aiosqlite runs the driver on a worker thread, so the default
        # same-thread check has to be relaxed.
        kwargs["connect_args"] = {"check_same_thread": False}
        if is_memory_sqlite(url):
            # One shared connection, otherwise every new connection would see a
            # brand new empty database.
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True

    engine = create_async_engine(url, **kwargs)  # type: ignore[arg-type]
    if is_sqlite(url):
        _apply_sqlite_pragmas(engine, file_based=not is_memory_sqlite(url))
    return engine


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Process-wide engine, built lazily from settings."""
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        if is_sqlite(settings.DATABASE_URL) and not is_memory_sqlite(
            settings.DATABASE_URL
        ):
            settings.ensure_sqlite_dir()
        _engine = build_engine(settings.resolved_database_url, echo=settings.SQL_ECHO)
        _sessionmaker = build_sessionmaker(_engine)
        logger.debug("database engine created for %s", settings.DATABASE_URL)
    assert _sessionmaker is not None
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session factory bound to :func:`get_engine`."""
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`echo` belongs to the engine, not the session - sessions must not pass it."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def set_engine(engine: AsyncEngine) -> None:
    """Install a pre-built engine (used by scripts and tests)."""
    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = build_sessionmaker(engine)


async def dispose_engine() -> None:
    """Close all pooled connections (shutdown hook)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def check_connection() -> bool:
    """Readiness helper: a real round trip, never an exception."""
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database connectivity check failed")
        return False
    return True


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session for scripts: commit on success, rollback on error.

    HTTP request sessions come from ``app.api.deps.get_db_session`` instead,
    because FastAPI needs a ``yield`` dependency rather than a context manager.
    """
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()

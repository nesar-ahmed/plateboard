"""Dependencies shared by every module.

Module-specific dependencies belong to the module itself
(``app/modules/<name>/dependencies.py``); this file only holds what is
genuinely global, and is the seam tests override.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker

__all__ = ["DbSession", "get_db_session"]


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session.

    Transactions are owned by services: a service calls ``commit()`` when a
    unit of work is complete. This dependency only guarantees rollback on an
    unhandled error and that the session is always closed.

    Tests replace *this* dependency (``app.dependency_overrides``), which is
    why routes never create sessions themselves.
    """
    session = get_sessionmaker()()
    try:
        yield session
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
"""Shorthand used by every module's ``dependencies.py``.

A type alias rather than ``session: AsyncSession = Depends(...)`` so the
session type stays visible to mypy and to route signatures.
"""

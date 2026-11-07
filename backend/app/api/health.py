"""``GET /api/health`` - the health endpoint consumed by the frontend.

The probe runs a real round trip against the database and reports the SQLite
settings this project relies on (WAL journaling, foreign keys). A database
that cannot be reached answers 503, so orchestrators - and the frontend -
can tell "up" from "usable".
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.db import get_engine, is_sqlite

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])


async def _inspect_database() -> dict[str, Any]:
    """One round trip plus the SQLite pragmas that matter, or raise.

    Anything that bubbles up here (connection refused, file locked, bad URL)
    is turned into a 503 by :func:`health`.
    """
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        info: dict[str, Any] = {"engine": engine.dialect.name}
        if is_sqlite(str(engine.url)):
            journal_mode = (
                await connection.execute(text("PRAGMA journal_mode"))
            ).scalar()
            foreign_keys = (
                await connection.execute(text("PRAGMA foreign_keys"))
            ).scalar()
            info["journal_mode"] = str(journal_mode).lower()
            info["foreign_keys"] = bool(foreign_keys)
    return info


@router.get("/health", summary="Service health")
async def health() -> JSONResponse:
    settings = get_settings()
    try:
        database = await _inspect_database()
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse(
            {
                "status": "degraded",
                "version": __version__,
                "environment": settings.ENVIRONMENT,
                "database": "error",
            },
            status_code=503,
        )
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "environment": settings.ENVIRONMENT,
            "database": "ok",
            "database_info": database,
        }
    )

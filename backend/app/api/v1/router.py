"""Router assembly for API v1.

This is the seam where feature routers get mounted under ``/api/v1``:

    from app.api.v1.boards import router as boards_router

    v1_router.include_router(boards_router, prefix="/boards", tags=["boards"])

Add a module = one ``include_router`` line here; routes never hard-code the
version prefix, so it stays defined in exactly one place.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

v1_router = APIRouter(prefix="/v1")


@v1_router.get("", summary="API v1 metadata", tags=["v1"])
async def v1_info() -> dict[str, Any]:
    """Version marker; replaced organically as real v1 resources land."""
    return {"version": "v1", "status": "under development"}

"""Router assembly - the only place HTTP surfaces are mounted under ``/api``.

* ``/api/health``  - operational probe, deliberately *not* versioned with the
  API: infrastructure must keep pointing at one stable URL while v1, v2, ...
  come and go.
* ``/api/v1/*``    - the versioned API under development (``app/api/v1``).

Adding a feature = one ``include_router`` line in ``app/api/v1/router.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1 import v1_router

api_router = APIRouter()
api_router.include_router(health_router)
# FastAPI bakes each router's own prefix into its routes at decoration time
# ("/v1" above), so the "/api" root is attached here, at assembly.
api_router.include_router(v1_router, prefix="/api")

__all__ = ["api_router"]

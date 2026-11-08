"""Router assembly - the only place HTTP surfaces are mounted under ``/api``.

* ``/api/health``  - operational probe, deliberately *not* versioned with the
  API: infrastructure must keep pointing at one stable URL while v1, v2, ...
  come and go.
* ``/api/auth``, ``/api/me``, ``/api/cooks``, ``/api/dishes``, ``/api/zones``,
  ``/api/me/cart`` - the current feature routers (``app/modules/<feature>``);
  each owns its ``/api/...`` prefix.
* ``/api/v1/*``    - the versioned API under development (``app/api/v1``).

Adding a feature = one ``include_router`` line here (un-versioned, like the
features above) or in ``app/api/v1/router.py`` (versioned).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1 import v1_router
from app.modules.auth import auth_router
from app.modules.cart import cart_router
from app.modules.cooks import cook_router
from app.modules.dishes import dish_router, public_dish_router
from app.modules.zones import zone_router

api_router = APIRouter()
api_router.include_router(health_router)
# Auth lives un-versioned next to health (fixed URLs for infra + frontend).
api_router.include_router(auth_router)
api_router.include_router(cook_router)
# Cook-only dish management under /api/me/dishes (the "me" namespace) and the
# public menu under /api/dishes - both own their /api prefix, like /api/cooks.
api_router.include_router(dish_router)
api_router.include_router(public_dish_router)
# Public zone list (reference data for the ?zone= filter and cook profiles).
api_router.include_router(zone_router)
# The caller's own cart, in the "me" namespace like /api/me/dishes.
api_router.include_router(cart_router)
# FastAPI bakes each router's own prefix into its routes at decoration time
# ("/v1" above), so the "/api" root is attached here, at assembly.
api_router.include_router(v1_router, prefix="/api")

__all__ = ["api_router"]

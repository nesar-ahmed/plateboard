"""Router assembly - the only place HTTP surfaces are mounted under ``/api``.

* ``/api/health``  - operational probe, deliberately *not* versioned with the
  API: infrastructure must keep pointing at one stable URL while v1, v2, ...
  come and go.
* ``/api/auth``, ``/api/me``, ``/api/cooks``, ``/api/dishes``, ``/api/zones``,
  ``/api/cart``, ``/api/me/favourites``, ``/api/me/addresses``, ``/api/me/orders`` +
  ``/api/cooks/me/orders``, reviews (``/api/me/reviews``,
  ``/api/cooks/me/reviews``, ``/api/dishes|cooks/{id}/reviews``), the dashboards
  (``/api/me/dashboard``, ``/api/cooks/me/dashboard``, ``/api/admin/dashboard``)
  plus the cook's earnings (``/api/cooks/me/earnings``), ``/api/admin`` and
  the notification inbox (``/api/me/notifications``) - the current feature
  routers (``app/modules/<feature>``);
  each owns its ``/api/...`` prefix.
* ``/api/v1/*``    - the versioned API under development (``app/api/v1``).

Adding a feature = one ``include_router`` line here (un-versioned, like the
features above) or in ``app/api/v1/router.py`` (versioned).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1 import v1_router
from app.modules.addresses import address_router
from app.modules.admin import admin_router
from app.modules.auth import auth_router
from app.modules.cart import cart_router
from app.modules.cooks import cook_router
from app.modules.dashboards import (
    admin_dashboard_router,
    cook_dashboard_router,
    cook_earnings_router,
    customer_dashboard_router,
)
from app.modules.dishes import dish_router, public_dish_router
from app.modules.favourites import favourite_router
from app.modules.notifications.router import notification_router
from app.modules.orders import cook_orders_router, my_orders_router
from app.modules.reviews.router import (
    cook_review_router,
    my_review_router,
    public_review_router,
)
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
# The caller's cart - guest (cookie) or account - under /api/cart.
api_router.include_router(cart_router)
# The signed-in customer's favourite dishes (and adding them to the cart).
api_router.include_router(favourite_router)
# The signed-in user's address book (checkout picks one of these).
api_router.include_router(address_router)
# Orders: the customer's (/api/me/orders) and the cook's incoming ones
# (/api/cooks/me/orders - three path segments, so /api/cooks/{user_id} never
# shadows them).
api_router.include_router(my_orders_router)
api_router.include_router(cook_orders_router)
# The cook's review router MUST come before the public one: otherwise
# /api/cooks/{user_id}/reviews catches /api/cooks/me/reviews (422 for "me").
api_router.include_router(my_review_router)
api_router.include_router(cook_review_router)
api_router.include_router(public_review_router)
# One read-only dashboard per audience, plus the admin back-office lists.
api_router.include_router(customer_dashboard_router)
api_router.include_router(cook_dashboard_router)
api_router.include_router(cook_earnings_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_router)
# The signed-in user's notification inboxes (account / cook / admin panels).
api_router.include_router(notification_router)
# FastAPI bakes each router's own prefix into its routes at decoration time
# ("/v1" above), so the "/api" root is attached here, at assembly.
api_router.include_router(v1_router, prefix="/api")

__all__ = ["api_router"]

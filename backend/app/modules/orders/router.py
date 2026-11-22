"""HTTP routes for orders - the customer's side and the cook's side.

Customer (any signed-in user; the "me" namespace, like ``/api/me/dishes``):

* POST /api/me/orders              - place an order from my cart to one of
                                     my addresses (201)
* GET  /api/me/orders              - my orders, newest first (``?status=``,
                                     repeatable: any of them)
* GET  /api/me/orders/{id}         - one of my orders
* POST /api/me/orders/{id}/cancel  - cancel it while it is still ``placed``
* POST /api/me/orders/{id}/receive - confirm I received a ``ready`` order:
                                     this is what completes it

Cook (``require_cook``; next to ``/api/cooks/me``):

* GET   /api/cooks/me/orders       - orders placed with me (``?status=``,
                                     repeatable; ``?sort=oldest`` = queue)
* GET   /api/cooks/me/orders/{id}  - one of them
* PATCH /api/cooks/me/orders/{id}  - ``{"status": ...}`` accept / ready /
  cancel (reject) - optionally with a ``reason`` when cancelling; completing
  is the customer's confirmation, never the cook's

Placing an order and every status move notify the other side (in-app
notifications, ``app.modules.orders.notifications``).

Someone else's order id is always a 404. The admin's all-orders list lives in
``app.modules.admin``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.modules.auth.dependencies import CookRequired, LoginRequired
from app.modules.orders import service
from app.modules.orders.models import OrderStatus
from app.modules.orders.schemas import (
    CookStatusUpdate,
    OrderOut,
    OrderPage,
    OrderPlaceRequest,
    order_out,
)

my_orders_router = APIRouter(prefix="/api/me/orders", tags=["orders"])
cook_orders_router = APIRouter(prefix="/api/cooks/me/orders", tags=["orders"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100, description="page size")]
PageOffset = Annotated[int, Query(ge=0, description="rows to skip")]
StatusFilter = Annotated[
    list[OrderStatus] | None,
    Query(description="repeatable: orders in any of these statuses (none = all)"),
]
Sort = Annotated[
    Literal["newest", "oldest"],
    Query(description="newest first (default) or oldest first - the kitchen queue"),
]


def _page(
    total: int, views: list[service.OrderView], limit: int, offset: int
) -> OrderPage:
    return OrderPage(
        items=[order_out(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
    )


# --- customer ------------------------------------------------------------------------


@my_orders_router.post("", response_model=OrderOut, status_code=201)
async def place_order(
    payload: OrderPlaceRequest, user: LoginRequired, db: DbSession
) -> OrderOut:
    """Place an order from the caller's cart to one of their addresses: prices
    and the address are copied, the cart is emptied. ``fulfilment`` defaults
    to ``pickup`` (``delivery``: 422 ``fulfilment_unavailable`` - not offered
    yet). 422 ``unknown_address``; 409 ``cart_empty`` /
    ``cart_has_unavailable`` / ``cart_changed`` / ``kitchen_closed`` (the
    kitchen is outside its hours or paused)."""
    view = await service.place_order(db, user.id, payload)
    return order_out(view)


@my_orders_router.get("", response_model=OrderPage)
async def list_my_orders(
    user: LoginRequired,
    db: DbSession,
    status: StatusFilter = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> OrderPage:
    total, views = await service.page_orders(
        db, customer_id=user.id, status=status or [], limit=limit, offset=offset
    )
    return _page(total, views, limit, offset)


@my_orders_router.get("/{order_id}", response_model=OrderOut)
async def get_my_order(
    order_id: uuid.UUID, user: LoginRequired, db: DbSession
) -> OrderOut:
    return order_out(await service.get_order(db, order_id, customer_id=user.id))


@my_orders_router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_my_order(
    order_id: uuid.UUID, user: LoginRequired, db: DbSession
) -> OrderOut:
    """Only while the order is ``placed``; after the cook accepted it, only
    the cook can cancel (409 ``invalid_status_transition``)."""
    view = await service.get_order(db, order_id, customer_id=user.id)
    return order_out(await service.cancel_by_customer(db, view))


@my_orders_router.post("/{order_id}/receive", response_model=OrderOut)
async def confirm_received(
    order_id: uuid.UUID, user: LoginRequired, db: DbSession
) -> OrderOut:
    """Confirm I have the food: a ``ready`` order becomes ``completed`` (only
    then does it count as completed - for the kitchen's earnings too). Any
    other status is 409 ``invalid_status_transition``."""
    view = await service.get_order(db, order_id, customer_id=user.id)
    return order_out(await service.confirm_received(db, view))


# --- cook ----------------------------------------------------------------------------


@cook_orders_router.get("", response_model=OrderPage)
async def list_cook_orders(
    user: CookRequired,
    db: DbSession,
    status: StatusFilter = None,
    sort: Sort = "newest",
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> OrderPage:
    """``?status=placed&sort=oldest`` is the queue of requests waiting for an
    answer, first come first served."""
    total, views = await service.page_orders(
        db,
        cook_id=user.id,
        status=status or [],
        oldest_first=sort == "oldest",
        limit=limit,
        offset=offset,
    )
    return _page(total, views, limit, offset)


@cook_orders_router.get("/{order_id}", response_model=OrderOut)
async def get_cook_order(
    order_id: uuid.UUID, user: CookRequired, db: DbSession
) -> OrderOut:
    return order_out(await service.get_order(db, order_id, cook_id=user.id))


@cook_orders_router.patch("/{order_id}", response_model=OrderOut)
async def update_cook_order(
    order_id: uuid.UUID, payload: CookStatusUpdate, user: CookRequired, db: DbSession
) -> OrderOut:
    """placed -> accepted | cancelled, accepted -> ready | cancelled;
    anything else is 409 ``invalid_status_transition`` - a ready order is
    completed by the customer (``POST /api/me/orders/{id}/receive``).
    Accept a request with ``{"status": "accepted"}``, reject it with
    ``{"status": "cancelled", "reason": "..."}`` (reason optional)."""
    view = await service.get_order(db, order_id, cook_id=user.id)
    return order_out(
        await service.update_by_cook(
            db, view, OrderStatus(payload.status), reason=payload.reason
        )
    )

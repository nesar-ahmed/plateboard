"""Order business logic: placing the cart, reading orders, moving statuses.

Rules in one place:

* **Placing** turns the caller's *account* cart into an order (checkout needs
  a login; a guest cart moves to the account at login), delivered to one of
  the caller's own addresses (copied into the order; 422 ``unknown_address``
  otherwise). The cart must hold at
  least one dish and no unavailable (deactivated) lines - 409 ``cart_empty`` /
  ``cart_has_unavailable``. Names and current prices are copied into the
  order lines (this is where the cart's "price is always current" ends), the
  totals are stored, and the cart is emptied - all in one transaction. If the
  cart changed between reading and emptying it (a double submit, an add in
  another tab), nothing is placed: 409 ``cart_changed``. The kitchen must be
  taking orders right now (its hours / pause switch - see
  ``app.modules.cooks.availability``), else 409 ``kitchen_closed`` saying
  when it opens again. (Filling the cart is always allowed.) The order is a
  ``pickup`` unless the customer asks otherwise; modes the platform does not
  offer yet (``delivery``) are a 422 ``fulfilment_unavailable``.
* **Visibility**: customers see their own orders, cooks the orders placed
  with them, admins everything; anyone else's order id is a 404 (never 403),
  like dishes.
* **Status**: the cook moves an order along ``models.TRANSITIONS`` (accept
  or reject a request, mark it ready; a rejection/cancellation may carry a
  ``cancel_reason`` for the customer); the customer follows
  ``models.CUSTOMER_TRANSITIONS``: cancel while it is still ``placed``, and
  confirm receipt of a ``ready`` order - which is what completes it. Each
  move stamps its ``*_at`` column. Moves are compare-and-set on the current
  status, so two racing changes (cook accepts while the customer cancels)
  cannot both win - the loser gets 409 ``invalid_status_transition``.
* **Notifications** (``orders.notifications``): placing and every move
  notify the other party - and admins, when a cook cancels an accepted order
  - inside the same transaction, so a refused or rolled-back change notifies
  nobody.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.addresses import service as address_service
from app.modules.auth.models import CookProfile, User
from app.modules.cart import service as cart_service
from app.modules.cart.models import CartItem
from app.modules.cooks.availability import compute_availability
from app.modules.orders import notifications as order_notifications
from app.modules.orders.models import (
    CUSTOMER_TRANSITIONS,
    ENABLED_FULFILMENTS,
    TRANSITIONS,
    Fulfilment,
    Order,
    OrderItem,
    OrderStatus,
    Party,
)
from app.modules.orders.schemas import OrderPlaceRequest
from app.shared.base import utcnow

type AnySelect = Select[*tuple[Any, ...]]

# --- errors --------------------------------------------------------------------------


class OrderNotFoundError(NotFoundError):
    """Unknown id *or* an order the caller is not part of - same answer."""

    default_message = "Order not found"


class CartEmptyError(ConflictError):
    code = "cart_empty"
    default_message = "Your cart is empty - add a dish before ordering"


class CartHasUnavailableError(ConflictError):
    """Deactivated dishes are still in the cart; the customer removes them
    first, so an order never silently differs from what they saw."""

    code = "cart_has_unavailable"
    default_message = "Remove the dishes that are no longer available first"

    def __init__(self, dishes: Sequence[tuple[uuid.UUID, str]]) -> None:
        super().__init__(
            details=[
                {"dish_id": str(dish_id), "name": name} for dish_id, name in dishes
            ]
        )


class CartChangedError(ConflictError):
    code = "cart_changed"
    default_message = (
        "Your cart changed while the order was being placed - please review it"
    )


class KitchenClosedError(ConflictError):
    """The cart's kitchen is not taking orders right now (outside its hours,
    or paused by the cook); ``details`` say when it opens again, if known."""

    code = "kitchen_closed"
    default_message = "This kitchen isn't taking orders right now"

    def __init__(self, *, status: str, opens_at: str | None) -> None:
        message = (
            "This kitchen has paused new orders"
            if status == "paused"
            else "This kitchen isn't taking orders right now"
        )
        super().__init__(message, details={"status": status, "opens_at": opens_at})


class FulfilmentUnavailableError(ValidationFailedError):
    """A fulfilment mode the platform does not offer yet (``delivery``)."""

    default_message = "This fulfilment mode is not available yet"

    def __init__(self, mode: Fulfilment) -> None:
        offered = ", ".join(enabled.value for enabled in ENABLED_FULFILMENTS)
        super().__init__(
            details=[
                {
                    "field": "fulfilment",
                    "type": "fulfilment_unavailable",
                    "message": f"{mode.value} is not available yet (offered: {offered})",
                }
            ]
        )


class InvalidStatusTransitionError(ConflictError):
    code = "invalid_status_transition"
    default_message = "This order cannot move to that status"

    def __init__(
        self,
        current: OrderStatus,
        target: OrderStatus,
        allowed: Sequence[OrderStatus],
        message: str | None = None,
    ) -> None:
        super().__init__(
            message or f"An order that is {current.value} cannot become {target.value}",
            details={
                "status": current.value,
                "requested": target.value,
                "allowed": [status.value for status in allowed],
            },
        )


# --- read model ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class OrderView:
    order: Order
    items: list[OrderItem]
    cook_name: str | None
    customer_name: str | None


_Cook = aliased(User, name="order_cook")
_Customer = aliased(User, name="order_customer")


def _order_select() -> AnySelect:
    """Orders with both parties' display names (one query, no N+1).

    ``populate_existing`` so a status just changed by a bulk UPDATE is what
    comes back, not the identity map's stale copy.
    """
    return (
        select(Order, _Cook.display_name, _Customer.display_name)
        .join(_Cook, _Cook.id == Order.cook_id)
        .join(_Customer, _Customer.id == Order.customer_id)
        .execution_options(populate_existing=True)
    )


async def _views(session: AsyncSession, stmt: AnySelect) -> list[OrderView]:
    rows = (await session.execute(stmt)).all()
    ids = [row[0].id for row in rows]
    lines: dict[uuid.UUID, list[OrderItem]] = {order_id: [] for order_id in ids}
    if ids:
        items = await session.scalars(
            select(OrderItem)
            .where(OrderItem.order_id.in_(ids))
            .order_by(OrderItem.order_id, OrderItem.position)
        )
        for item in items:
            lines[item.order_id].append(item)
    return [
        OrderView(
            order=order, items=lines[order.id], cook_name=cook, customer_name=customer
        )
        for order, cook, customer in rows
    ]


def _scope[S: Select[*tuple[Any, ...]]](
    stmt: S,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
    status: Sequence[OrderStatus] = (),
) -> S:
    if customer_id is not None:
        stmt = stmt.where(Order.customer_id == customer_id)
    if cook_id is not None:
        stmt = stmt.where(Order.cook_id == cook_id)
    if status:
        stmt = stmt.where(Order.status.in_([item.value for item in status]))
    return stmt


async def page_orders(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
    status: Sequence[OrderStatus] = (),
    oldest_first: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[OrderView]]:
    """Newest first (or ``oldest_first``, the kitchen's first-come queue):
    ``(total_matching, page)``. No party filter = every order (the admin
    view); routers always pass the caller's id otherwise. ``status`` keeps
    orders in *any* of the given statuses (empty = all)."""
    total = await session.scalar(
        _scope(
            select(func.count()).select_from(Order),
            customer_id=customer_id,
            cook_id=cook_id,
            status=status,
        )
    )
    stmt = (
        _scope(_order_select(), customer_id=customer_id, cook_id=cook_id, status=status)
        .order_by(
            Order.created_at.asc() if oldest_first else Order.created_at.desc(),
            Order.id,
        )
        .limit(limit)
        .offset(offset)
    )
    return total or 0, await _views(session, stmt)


async def get_order(
    session: AsyncSession,
    order_id: uuid.UUID,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
) -> OrderView:
    """One order, if the given party is part of it (404 otherwise)."""
    stmt = _scope(_order_select(), customer_id=customer_id, cook_id=cook_id).where(
        Order.id == order_id
    )
    views = await _views(session, stmt)
    if not views:
        raise OrderNotFoundError
    return views[0]


# --- placing -------------------------------------------------------------------------


async def place_order(
    session: AsyncSession, customer_id: uuid.UUID, payload: OrderPlaceRequest
) -> OrderView:
    """Turn the customer's account cart into a ``placed`` order (see module
    docstring for the rules), empty the cart and notify both parties."""
    if payload.fulfilment not in ENABLED_FULFILMENTS:
        raise FulfilmentUnavailableError(payload.fulfilment)
    try:
        address = await address_service.get_owned(
            session, payload.address_id, customer_id
        )
    except address_service.AddressNotFoundError:
        raise address_service.UnknownAddressError from None
    cart = await cart_service.get_cart(
        session, cart_service.CartOwner(user_id=customer_id)
    )
    if not cart.lines:
        raise CartEmptyError
    unavailable = [
        (line.dish.id, line.dish.name) for line in cart.lines if not line.available
    ]
    if unavailable:
        raise CartHasUnavailableError(unavailable)
    assert cart.cart_id is not None and cart.cook_id is not None  # non-empty cart
    kitchen = await session.get(CookProfile, cart.cook_id)
    if kitchen is not None:
        now = compute_availability(
            hours=kitchen.opening_hours or [],
            timezone=kitchen.timezone,
            paused=kitchen.orders_paused,
            now=utcnow(),
        )
        if not now.accepting_orders:
            raise KitchenClosedError(
                status=now.status,
                opens_at=now.opens_at.isoformat() if now.opens_at else None,
            )

    order = Order(
        customer_id=customer_id,
        cook_id=cart.cook_id,
        status=OrderStatus.PLACED.value,
        total=cart.total,
        item_count=cart.item_count,
        note=payload.note,
        fulfilment=payload.fulfilment.value,
        delivery_address=address_service.delivery_snapshot(address),
    )
    session.add(order)
    await session.flush()  # the id the lines point at
    for position, line in enumerate(cart.lines):
        session.add(
            OrderItem(
                order_id=order.id,
                dish_id=line.dish.id,
                position=position,
                name=line.dish.name,
                unit_price=line.dish.price,
                quantity=line.item.quantity,
            )
        )
    ordered = {(line.dish.id, line.item.quantity) for line in cart.lines}
    order_id = order.id

    # Empty the cart and check we emptied exactly what we ordered: anything
    # else means a concurrent change, and the whole order is rolled back.
    removed = await session.execute(
        delete(CartItem)
        .where(CartItem.cart_id == cart.cart_id)
        .returning(CartItem.dish_id, CartItem.quantity)
        .execution_options(synchronize_session=False)
    )
    if {(dish_id, quantity) for dish_id, quantity in removed.all()} != ordered:
        await session.rollback()
        raise CartChangedError
    await order_notifications.order_placed(
        session,
        order,
        cook_name=cart.cook_name,
        customer_name=await session.scalar(
            select(User.display_name).where(User.id == customer_id)
        ),
    )
    await session.commit()
    return await get_order(session, order_id)


# --- status changes ------------------------------------------------------------------

_STAMPS: dict[OrderStatus, str] = {
    OrderStatus.ACCEPTED: "accepted_at",
    OrderStatus.READY: "ready_at",
    OrderStatus.COMPLETED: "completed_at",
    OrderStatus.CANCELLED: "cancelled_at",
}


async def _move(
    session: AsyncSession,
    view: OrderView,
    target: OrderStatus,
    *,
    by: Party,
    reason: str | None = None,
    refusal: str | None = None,
) -> OrderView:
    """Compare-and-set ``view.order`` from its current status to ``target``,
    as the party ``by`` (cook or customer - which decides the allowed moves);
    ``reason`` is stored with a cancellation. The other party is notified in
    the same transaction."""
    transitions = TRANSITIONS if by is Party.COOK else CUSTOMER_TRANSITIONS
    current = OrderStatus(view.order.status)
    allowed = transitions[current]
    if target not in allowed:
        raise InvalidStatusTransitionError(current, target, allowed, refusal)
    values: dict[str, Any] = {"status": target.value, _STAMPS[target]: utcnow()}
    if target is OrderStatus.CANCELLED:
        values["cancelled_by"] = by.value
        values["cancel_reason"] = reason
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Order)
            .where(Order.id == view.order.id, Order.status == current.value)
            .values(**values)
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount != 1:  # somebody moved it first
        await session.rollback()
        fresh = await get_order(session, view.order.id)
        now = OrderStatus(fresh.order.status)
        raise InvalidStatusTransitionError(now, target, transitions[now])
    await order_notifications.status_changed(
        session,
        view.order,
        previous=current,
        target=target,
        by=by,
        reason=reason,
        cook_name=view.cook_name,
        customer_name=view.customer_name,
    )
    await session.commit()
    return await get_order(session, view.order.id)


async def update_by_cook(
    session: AsyncSession,
    view: OrderView,
    target: OrderStatus,
    *,
    reason: str | None = None,
) -> OrderView:
    """The cook's move. Cancelling a ``placed`` order is a rejection of the
    request, an ``accepted`` one a cancellation; ``reason`` (optional) tells
    the customer why. Completing is not the cook's to do: the customer
    confirms receipt (:func:`confirm_received`)."""
    return await _move(
        session,
        view,
        target,
        by=Party.COOK,
        reason=reason,
        refusal="Only the customer can complete an order, by confirming they "
        "received it"
        if target is OrderStatus.COMPLETED
        else None,
    )


async def cancel_by_customer(session: AsyncSession, view: OrderView) -> OrderView:
    """Customers may cancel only until the cook accepts the order."""
    current = OrderStatus(view.order.status)
    return await _move(
        session,
        view,
        OrderStatus.CANCELLED,
        by=Party.CUSTOMER,
        refusal=None
        if current is OrderStatus.PLACED
        else f"The order is already {current.value}; only placed orders can be cancelled",
    )


async def confirm_received(session: AsyncSession, view: OrderView) -> OrderView:
    """The customer confirms they have the food: ``ready`` -> ``completed``
    (stamps ``completed_at``; the kitchen is notified)."""
    current = OrderStatus(view.order.status)
    return await _move(
        session,
        view,
        OrderStatus.COMPLETED,
        by=Party.CUSTOMER,
        refusal=None
        if current is OrderStatus.READY
        else f"The order is {current.value}; it can be confirmed once the cook "
        "marks it ready",
    )

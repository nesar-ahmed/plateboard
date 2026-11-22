"""ORM models for orders: a placed cart, frozen.

* ``Order`` - one customer buying from one cook (a cart holds one cook's
  dishes, so an order does too). ``total`` and ``item_count`` are stored at
  placement: they are the amounts agreed on, not a live sum. The status moves
  along :data:`TRANSITIONS`; each step stamps its own ``*_at`` column, which
  is what the order timeline (and the dashboards' timings) read.
* ``Order.delivery_address`` - a *copy* of the address chosen at checkout
  (JSON, see ``addresses.schemas.DeliveryAddressOut``), so editing or
  deleting the address later never rewrites the order. Orders placed before
  addresses existed have none (NULL).
* ``OrderItem`` - one line, a *snapshot* of the dish at placement: its name
  and unit price are copied, so editing or deleting the dish later never
  rewrites an order. ``dish_id`` is kept while the dish exists (SET NULL when
  the cook deletes it) for linking back to the menu.
* ``Order.cancel_reason`` - the cook's optional explanation when they turn an
  order down. A cook cancelling a ``placed`` order is a *rejection* (it was
  never accepted: ``accepted_at`` stays NULL); after ``accepted`` it is a
  cancellation. Customers cancel without a reason.
* ``Order.fulfilment`` - how the food reaches the customer: ``pickup`` (the
  default, and the only mode taken today - :data:`ENABLED_FULFILMENTS`) or
  ``delivery`` (modelled, not offered yet).
* **Who moves what** - the cook accepts or rejects, cancels an accepted
  order, and marks it ``ready``; the *customer* cancels while ``placed`` and
  confirms receipt (``ready`` -> ``completed``): an order only counts as
  completed once the customer says they have the food.

Deleting an account deletes the orders it took part in (CASCADE, like every
other account-owned row); deleting an order deletes its lines. No ORM
relationships on purpose (same rule as the cart): every read is an explicit
query, so nothing can trigger an implicit lazy load under asyncio.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.cart.models import MAX_QUANTITY, MIN_QUANTITY
from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

NOTE_MAX_LENGTH = 300
DISH_NAME_MAX_LENGTH = 120  # same as Dish.name
#: Why the cook turned an order down (shown to the customer).
CANCEL_REASON_MAX_LENGTH = 200


class Fulfilment(str, Enum):
    """How an order reaches the customer."""

    PICKUP = "pickup"  # the customer collects it from the kitchen
    DELIVERY = "delivery"  # brought to the delivery address - not offered yet


FULFILMENT_VALUES: tuple[str, ...] = tuple(mode.value for mode in Fulfilment)
#: Modes a customer may choose at checkout today. Delivery joins once the
#: platform can deliver; until then asking for it is a 422.
ENABLED_FULFILMENTS: tuple[Fulfilment, ...] = (Fulfilment.PICKUP,)


class OrderStatus(str, Enum):
    """Lifecycle of an order. ``placed`` is where every order starts;
    ``completed`` and ``cancelled`` are final."""

    PLACED = "placed"
    ACCEPTED = "accepted"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ORDER_STATUS_VALUES: tuple[str, ...] = tuple(status.value for status in OrderStatus)

#: Statuses of orders still in progress (neither completed nor cancelled).
OPEN_STATUSES: tuple[OrderStatus, ...] = (
    OrderStatus.PLACED,
    OrderStatus.ACCEPTED,
    OrderStatus.READY,
)

#: The cook's allowed moves. A ``ready`` order waits for the *customer*.
TRANSITIONS: dict[OrderStatus, tuple[OrderStatus, ...]] = {
    OrderStatus.PLACED: (OrderStatus.ACCEPTED, OrderStatus.CANCELLED),
    OrderStatus.ACCEPTED: (OrderStatus.READY, OrderStatus.CANCELLED),
    OrderStatus.READY: (),
    OrderStatus.COMPLETED: (),
    OrderStatus.CANCELLED: (),
}

#: The customer's allowed moves: cancel until the cook accepts, and confirm
#: receipt once the food is ready (``service.cancel_by_customer`` /
#: ``service.confirm_received``).
CUSTOMER_TRANSITIONS: dict[OrderStatus, tuple[OrderStatus, ...]] = {
    OrderStatus.PLACED: (OrderStatus.CANCELLED,),
    OrderStatus.ACCEPTED: (),
    OrderStatus.READY: (OrderStatus.COMPLETED,),
    OrderStatus.COMPLETED: (),
    OrderStatus.CANCELLED: (),
}


class CancelledBy(str, Enum):
    CUSTOMER = "customer"
    COOK = "cook"


#: Who acts on an order - the same two parties that may cancel one. Moves
#: (``service._move``) and their notifications say ``by=Party.CUSTOMER``
#: when the customer confirms receipt, which ``CancelledBy`` would misname.
Party = CancelledBy


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """``created_at`` is the moment the order was placed."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(ORDER_STATUS_VALUES)})", name="status_known"),
        CheckConstraint(
            f"cancelled_by IS NULL OR cancelled_by IN "
            f"({_in(tuple(who.value for who in CancelledBy))})",
            name="cancelled_by_known",
        ),
        CheckConstraint(
            f"fulfilment IN ({_in(FULFILMENT_VALUES)})", name="fulfilment_known"
        ),
        CheckConstraint("total > 0", name="total_positive"),
        CheckConstraint("item_count > 0", name="item_count_positive"),
        # The cart already refuses a cook's own dish; this makes it a rule.
        CheckConstraint("customer_id <> cook_id", name="not_own_order"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OrderStatus.PLACED.value, index=True
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False)  # minor units
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)  # portions
    note: Mapped[str | None] = mapped_column(String(NOTE_MAX_LENGTH), nullable=True)
    fulfilment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=Fulfilment.PICKUP.value,
        server_default=text("'pickup'"),
    )
    delivery_address: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Optional explanation the cook gives when rejecting (placed -> cancelled)
    # or cancelling (accepted -> cancelled) an order; the customer sees it.
    cancel_reason: Mapped[str | None] = mapped_column(
        String(CANCEL_REASON_MAX_LENGTH), nullable=True
    )


class OrderItem(Base, UUIDPrimaryKeyMixin):
    """One order line; ``position`` keeps the cart's order (newest first)."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("unit_price > 0", name="unit_price_positive"),
        CheckConstraint(
            f"quantity >= {MIN_QUANTITY} AND quantity <= {MAX_QUANTITY}",
            name="quantity_range",
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dishes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(DISH_NAME_MAX_LENGTH), nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)  # minor units
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def line_total(self) -> int:
        return self.unit_price * self.quantity

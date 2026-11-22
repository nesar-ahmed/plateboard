"""Schemas for the order endpoints.

Money is integer minor units (like dish prices and the cart). Every order
response carries the whole :class:`OrderOut` - lines, both parties and the
status timeline - so a client never needs a second request to draw it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.addresses.schemas import DeliveryAddressOut
from app.modules.orders.models import (
    CANCEL_REASON_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    Fulfilment,
    OrderStatus,
)
from app.shared.types import UTCDateTime

if TYPE_CHECKING:  # the service imports this module; no runtime cycle
    from app.modules.orders.service import OrderView

__all__ = [
    "CookStatusUpdate",
    "OrderItemOut",
    "OrderOut",
    "OrderPage",
    "OrderPartyOut",
    "OrderPlaceRequest",
    "order_out",
]


class OrderPlaceRequest(BaseModel):
    """Body for ``POST /api/me/orders``.

    The order *is* the caller's account cart; the body says where it goes -
    ``address_id`` from the caller's address book (``/api/me/addresses``; any
    other id is a 422 ``unknown_address``) - plus an optional note for the
    cook. Blank notes are stored as no note.

    ``fulfilment`` is how the food reaches the customer: ``pickup`` (the
    default) - ``delivery`` is part of the contract but not offered yet (422
    ``fulfilment_unavailable``). The address is the customer's contact for
    the cook either way, and the delivery address once delivery exists.
    """

    address_id: uuid.UUID = Field(description="one of GET /api/me/addresses")
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)
    fulfilment: Fulfilment = Field(
        default=Fulfilment.PICKUP, description="pickup (default) | delivery (not yet)"
    )

    @field_validator("note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CookStatusUpdate(BaseModel):
    """Body for ``PATCH /api/cooks/me/orders/{id}``: the next status.

    Allowed moves: placed -> accepted | cancelled, accepted -> ready |
    cancelled. Anything else is a 409 ``invalid_status_transition`` naming the
    allowed targets - including ``completed``: a ready order is completed by
    the *customer* confirming they received it
    (``POST /api/me/orders/{id}/receive``).

    Accepting an order request is ``{"status": "accepted"}``; rejecting it is
    ``{"status": "cancelled", "reason": "Sold out for today"}``. ``reason`` is
    optional, shown to the customer, and only allowed with ``cancelled``
    (blank means none).
    """

    # Plain strings (not enum members) so a 422 names the values cleanly.
    status: Literal["accepted", "ready", "completed", "cancelled"]
    reason: str | None = Field(
        default=None,
        max_length=CANCEL_REASON_MAX_LENGTH,
        description="why the order is rejected/cancelled - only with status=cancelled",
    )

    @field_validator("reason")
    @classmethod
    def _clean_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def _reason_only_when_cancelling(self) -> Self:
        if self.reason is not None and self.status != "cancelled":
            raise ValueError("a reason can only be given when cancelling an order")
        return self


class OrderItemOut(BaseModel):
    dish_id: uuid.UUID | None = Field(
        description="null once the cook deleted the dish (the line stays)"
    )
    name: str = Field(description="dish name at placement")
    unit_price: int = Field(description="price at placement, minor units")
    quantity: int
    line_total: int = Field(description="unit_price * quantity, minor units")


class OrderPartyOut(BaseModel):
    """One side of the order (the cook or the customer)."""

    id: uuid.UUID
    name: str | None = Field(description="display name (may be unset)")


class OrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    cook: OrderPartyOut
    customer: OrderPartyOut
    items: list[OrderItemOut]
    item_count: int = Field(description="portions in the order")
    total: int = Field(description="sum of the line totals, minor units")
    note: str | None
    fulfilment: Fulfilment = Field(description="pickup | delivery")
    delivery_address: DeliveryAddressOut | None = Field(
        description="copy of the checkout address (null for orders placed before "
        "addresses existed)"
    )
    created_at: UTCDateTime = Field(description="when the order was placed")
    updated_at: UTCDateTime
    accepted_at: UTCDateTime | None
    ready_at: UTCDateTime | None
    completed_at: UTCDateTime | None = Field(
        description="when the customer confirmed they received the order"
    )
    cancelled_at: UTCDateTime | None
    cancelled_by: Literal["customer", "cook"] | None
    cancel_reason: str | None = Field(
        description="the cook's explanation when they rejected/cancelled the order"
    )


class OrderPage(BaseModel):
    """Order lists (same pagination contract as dishes and cooks)."""

    items: list[OrderOut]
    total: int
    limit: int
    offset: int


def order_out(view: OrderView) -> OrderOut:
    """Service read model -> response. Shared by every router that shows
    orders (customer, cook, admin, dashboards)."""
    order = view.order
    return OrderOut(
        id=order.id,
        status=OrderStatus(order.status),
        cook=OrderPartyOut(id=order.cook_id, name=view.cook_name),
        customer=OrderPartyOut(id=order.customer_id, name=view.customer_name),
        items=[
            OrderItemOut(
                dish_id=item.dish_id,
                name=item.name,
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_total=item.line_total,
            )
            for item in view.items
        ],
        item_count=order.item_count,
        total=order.total,
        note=order.note,
        fulfilment=Fulfilment(order.fulfilment),
        delivery_address=DeliveryAddressOut.model_validate(order.delivery_address)
        if order.delivery_address
        else None,
        created_at=order.created_at,
        updated_at=order.updated_at,
        accepted_at=order.accepted_at,
        ready_at=order.ready_at,
        completed_at=order.completed_at,
        cancelled_at=order.cancelled_at,
        cancelled_by=order.cancelled_by,  # type: ignore[arg-type]  # CHECK-constrained
        cancel_reason=order.cancel_reason,
    )

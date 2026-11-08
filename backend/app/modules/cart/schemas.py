"""Schemas for the cart endpoints.

Money is integer minor units, like dish prices. Every cart endpoint answers
with the whole :class:`CartOut`, so a client never needs a second request to
redraw the cart after a change.
"""

from __future__ import annotations

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.modules.cart.models import MAX_QUANTITY, MIN_QUANTITY
from app.shared.types import UTCDateTime

#: Distinct dishes one cart may hold.
MAX_CART_LINES = 50

__all__ = [
    "MAX_CART_LINES",
    "MAX_QUANTITY",
    "MIN_QUANTITY",
    "CartCookOut",
    "CartItemAdd",
    "CartItemOut",
    "CartItemUpdate",
    "CartOut",
]


class CartItemAdd(BaseModel):
    """Body for ``POST /api/cart/items``.

    Adding a dish that is already in the cart *increases* its quantity. A cart
    holds one cook's dishes: a dish from another cook is a 409
    ``different_cook`` unless ``replace_cart`` is true, which empties the cart
    and starts it over with this dish - atomically.
    """

    dish_id: uuid.UUID
    quantity: int = Field(default=1, ge=MIN_QUANTITY, le=MAX_QUANTITY)
    replace_cart: bool = Field(
        default=False,
        description="start a new cart with this dish if the cart holds another cook's dishes",
    )


class CartItemUpdate(BaseModel):
    """Body for ``PATCH /api/cart/items/{dish_id}`` - exactly one of:

    * ``quantity`` - set the quantity (e.g. typed into an input);
    * ``delta`` - increase (+) or decrease (-) it (the +/- buttons).

    The result must stay within 1..100; removing a dish is ``DELETE``, never a
    quantity of 0.
    """

    quantity: int | None = Field(default=None, ge=MIN_QUANTITY, le=MAX_QUANTITY)
    delta: int | None = Field(default=None, ge=-MAX_QUANTITY, le=MAX_QUANTITY)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.quantity is None) == (self.delta is None):
            raise ValueError("send exactly one of quantity or delta")
        if self.delta == 0:
            raise ValueError("delta must not be 0")
        return self


class CartItemOut(BaseModel):
    dish_id: uuid.UUID
    name: str
    price: int = Field(description="current unit price, minor units")
    quantity: int
    line_total: int = Field(description="price * quantity, minor units")
    available: bool = Field(
        description="false once the cook deactivates the dish: excluded from "
        "totals, can only be removed"
    )
    max_quantity: int = Field(description="the most this line may hold")
    added_at: UTCDateTime


class CartCookOut(BaseModel):
    """The one cook whose dishes the cart holds."""

    id: uuid.UUID
    name: str | None


class CartOut(BaseModel):
    """The caller's cart (guest or signed-in), newest additions first."""

    owner: Literal["guest", "user"]
    cook: CartCookOut | None = Field(description="null while the cart is empty")
    items: list[CartItemOut]
    item_count: int = Field(description="portions across available lines")
    total: int = Field(description="sum of available line totals, minor units")
    unavailable_count: int = Field(description="lines whose dish was deactivated")

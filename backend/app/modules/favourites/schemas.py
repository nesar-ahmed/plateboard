"""Schemas for the favourite-dish endpoints.

A favourite carries the whole public dish (:class:`PublicDishOut` - name,
price, cook, zone, ...), so a client can draw the same card as on the menu,
plus ``available`` and when it was saved. ``available`` is the one thing a
client must check before offering "add to cart": a dish its cook has hidden
stays on the list, flagged unavailable.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.cart.models import MAX_QUANTITY, MIN_QUANTITY
from app.modules.dishes.schemas import PublicDishOut
from app.modules.favourites.models import MAX_FAVOURITES
from app.shared.types import UTCDateTime

__all__ = [
    "MAX_FAVOURITES",
    "FavouriteCartAdd",
    "FavouriteOut",
    "FavouritePage",
]

AVAILABLE_DESCRIPTION = (
    "false once the cook hides the dish (made it private): it stays on the "
    "list but cannot be added to the cart until the cook publishes it again"
)


class FavouriteOut(BaseModel):
    """One saved dish."""

    dish: PublicDishOut = Field(description="the dish as the public menu shows it")
    available: bool = Field(description=AVAILABLE_DESCRIPTION)
    added_at: UTCDateTime = Field(description="when the dish was saved")


class FavouritePage(BaseModel):
    """``GET /api/me/favourites`` - newest first, with the same pagination
    contract as dishes and orders. ``total`` counts hidden dishes too (they
    take up room on the list); ``unavailable`` says how many of them there are."""

    items: list[FavouriteOut]
    total: int
    unavailable: int = Field(description="saved dishes the cook has hidden")
    max_favourites: int = Field(
        default=MAX_FAVOURITES, description="how many dishes the list may hold"
    )
    limit: int
    offset: int


class FavouriteCartAdd(BaseModel):
    """Body for ``POST /api/me/favourites/{dish_id}/cart`` (optional - an
    empty body adds one portion).

    The same rules as ``POST /api/cart/items``: an existing cart line grows,
    and one cook per cart - a dish from another cook is a 409
    ``different_cook`` unless ``replace_cart`` is true, which empties the cart
    and starts it over with this dish.
    """

    quantity: int = Field(default=1, ge=MIN_QUANTITY, le=MAX_QUANTITY)
    replace_cart: bool = Field(
        default=False,
        description="start a new cart with this dish if the cart holds another cook's dishes",
    )

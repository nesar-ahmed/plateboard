"""HTTP routes for favourite dishes (``require_customer``: 401 anonymous, 403
without the customer role - a cook is a customer too).

* GET    /api/me/favourites                 - my saved dishes, newest first;
                                              hidden ones flagged unavailable
* GET    /api/me/favourites/{dish_id}       - is this dish on my list? (404 if not)
* PUT    /api/me/favourites/{dish_id}       - save an available dish: 201 when
                                              added, 200 if it already was
* DELETE /api/me/favourites/{dish_id}       - remove it (204, also if it was not there)
* POST   /api/me/favourites/{dish_id}/cart  - add a saved dish to my cart;
                                              answers with the whole cart

``PUT``/``DELETE`` on the dish id make the heart button idempotent: a double
tap never errors or duplicates. Rules are in ``favourites.service``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Query, Response

from app.api.deps import DbSession
from app.modules.auth.dependencies import CustomerRequired
from app.modules.cart.schemas import CartOut, cart_out
from app.modules.dishes.schemas import PublicDishOut
from app.modules.favourites import service
from app.modules.favourites.schemas import (
    FavouriteCartAdd,
    FavouriteOut,
    FavouritePage,
)
from app.modules.reviews import service as review_service
from app.modules.reviews.schemas import rating_out
from app.modules.zones.schemas import ZoneOut

favourite_router = APIRouter(prefix="/api/me/favourites", tags=["favourites"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100, description="page size")]
PageOffset = Annotated[int, Query(ge=0, description="rows to skip")]


def _favourite_out(
    view: service.FavouriteView, rating: review_service.Rating | None = None
) -> FavouriteOut:
    row = view.row
    return FavouriteOut(
        dish=PublicDishOut.model_validate(row.dish).model_copy(
            update={
                "cook_name": row.cook_name,
                "zone": ZoneOut.model_validate(row.zone) if row.zone else None,
                "rating": rating_out(rating),
            }
        ),
        available=view.available,
        added_at=view.favourite.created_at,
    )


async def _one_out(db: DbSession, view: service.FavouriteView) -> FavouriteOut:
    dish_id = view.row.dish.id
    ratings = await review_service.dish_ratings(db, [dish_id])
    return _favourite_out(view, ratings.get(dish_id))


@favourite_router.get("", response_model=FavouritePage)
async def list_favourites(
    user: CustomerRequired,
    db: DbSession,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> FavouritePage:
    """My saved dishes, newest first. Dishes their cook has hidden stay on the
    list with ``available: false`` (and count towards the limit)."""
    total, unavailable, views = await service.page_favourites(
        db, user.id, limit=limit, offset=offset
    )
    ratings = await review_service.dish_ratings(db, (v.row.dish.id for v in views))
    return FavouritePage(
        items=[_favourite_out(view, ratings.get(view.row.dish.id)) for view in views],
        total=total,
        unavailable=unavailable,
        limit=limit,
        offset=offset,
    )


@favourite_router.get("/{dish_id}", response_model=FavouriteOut)
async def get_favourite(
    dish_id: uuid.UUID, user: CustomerRequired, db: DbSession
) -> FavouriteOut:
    """One saved dish - a 404 simply means "not on my list"."""
    return await _one_out(db, await service.get_favourite(db, user.id, dish_id))


@favourite_router.put(
    "/{dish_id}",
    response_model=FavouriteOut,
    responses={201: {"model": FavouriteOut, "description": "Saved now"}},
)
async def add_favourite(
    dish_id: uuid.UUID, user: CustomerRequired, db: DbSession, response: Response
) -> FavouriteOut:
    """Save a dish: **201** when it was added, **200** when it already was on
    the list. Only available (public) dishes - unknown or hidden ones are a
    404; your own dish is a 422 ``own_dish``; a full list (50) is a 409
    ``favourites_limit``."""
    added, view = await service.add_favourite(db, user.id, dish_id)
    response.status_code = 201 if added else 200
    return await _one_out(db, view)


@favourite_router.delete("/{dish_id}", status_code=204)
async def remove_favourite(
    dish_id: uuid.UUID, user: CustomerRequired, db: DbSession
) -> Response:
    """Remove a dish from the list (hidden ones too). Idempotent: 204 even if
    it was not on the list."""
    await service.remove_favourite(db, user.id, dish_id)
    return Response(status_code=204)


@favourite_router.post("/{dish_id}/cart", response_model=CartOut)
async def add_favourite_to_cart(
    dish_id: uuid.UUID,
    user: CustomerRequired,
    db: DbSession,
    payload: Annotated[FavouriteCartAdd | None, Body()] = None,
) -> CartOut:
    """Add a saved dish to my cart (default 1 portion) and answer with the
    whole cart, like every ``/api/cart`` endpoint. 404 if the dish is not on
    my list; 409 ``dish_unavailable`` while its cook hides it; otherwise the
    cart's rules - 409 ``different_cook`` (retry with ``replace_cart: true``
    to start a new cart), 422 ``quantity_unavailable``, 409 ``cart_full``."""
    view = await service.add_to_cart(
        db, user.id, dish_id, payload or FavouriteCartAdd()
    )
    return cart_out(view)

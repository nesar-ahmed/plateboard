"""HTTP routes for dishes.

Cook-only management lives under ``/api/me/dishes`` (every handler goes
through ``require_cook``, so customers see 403 and anonymous requests 401;
per-dish routes re-check ownership in the service -> 404):

* POST   /api/me/dishes            - add a dish to my menu
* GET    /api/me/dishes            - my dashboard list (incl. deactivated)
* GET    /api/me/dishes/{id}       - one of my dishes
* PATCH  /api/me/dishes/{id}       - edit / deactivate / reactivate
* DELETE /api/me/dishes/{id}       - remove for good

The public menu is a separate, unauthenticated router under ``/api/dishes``:

* GET /api/dishes?q=&cook_id=&zone=&max_distance=&min_price=&max_price=
  &dietary_tag=&exclude_allergen=&limit=&offset=  - active dishes, name
  search, location/price/diet/allergen filters (see ``PublicDishQuery``),
  simple pagination
* GET /api/dishes/{id}                        - one active dish (deactivated
  dishes answer 404 - hidden means gone to the public)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession
from app.modules.auth.dependencies import CookRequired
from app.modules.dishes import service
from app.modules.dishes.schemas import (
    DishCreateRequest,
    DishOut,
    DishPage,
    DishPatchRequest,
    PublicDishOut,
    PublicDishQuery,
)
from app.modules.zones.schemas import ZoneOut

dish_router = APIRouter(prefix="/api/me/dishes", tags=["dishes"])

# Public, unauthenticated by design (see the route docstrings).
public_dish_router = APIRouter(prefix="/api/dishes", tags=["dishes"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100, description="page size")]
PageOffset = Annotated[int, Query(ge=0, description="rows to skip")]


def _public_out(row: service.PublicDishRow) -> PublicDishOut:
    return PublicDishOut.model_validate(row.dish).model_copy(
        update={
            "cook_name": row.cook_name,
            "zone": ZoneOut.model_validate(row.zone) if row.zone else None,
            "distance": row.distance,
        }
    )


@dish_router.post("", response_model=DishOut, status_code=201)
async def create_dish(
    payload: DishCreateRequest, user: CookRequired, db: DbSession
) -> DishOut:
    dish = await service.create_dish(db, user.id, payload)
    return DishOut.model_validate(dish)


@dish_router.get("", response_model=list[DishOut])
async def list_my_dishes(user: CookRequired, db: DbSession) -> list[DishOut]:
    dishes = await service.list_cook_dishes(db, user.id)
    return [DishOut.model_validate(dish) for dish in dishes]


@dish_router.get("/{dish_id}", response_model=DishOut)
async def get_my_dish(
    dish_id: uuid.UUID, user: CookRequired, db: DbSession
) -> DishOut:
    dish = await service.get_owned_dish(db, dish_id, user.id)
    return DishOut.model_validate(dish)


@dish_router.patch("/{dish_id}", response_model=DishOut)
async def patch_my_dish(
    payload: DishPatchRequest, dish_id: uuid.UUID, user: CookRequired, db: DbSession
) -> DishOut:
    dish = await service.get_owned_dish(db, dish_id, user.id)
    updated = await service.update_dish(db, dish, payload)
    return DishOut.model_validate(updated)


@dish_router.delete("/{dish_id}", status_code=204)
async def delete_my_dish(
    dish_id: uuid.UUID, user: CookRequired, db: DbSession
) -> Response:
    dish = await service.get_owned_dish(db, dish_id, user.id)
    await service.delete_dish(db, dish)
    return Response(status_code=204)


@public_dish_router.get("", response_model=DishPage)
async def list_public_dishes(
    db: DbSession,
    filters: Annotated[PublicDishQuery, Query()],
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> DishPage:
    """Public menu: active dishes only, newest first, filters ANDed.

    ``q`` is a case-insensitive LIKE (``%``/``_`` escaped; blank = absent).
    ``zone`` alone keeps dishes from cooks in that zone; with ``max_distance``
    it keeps cooks within that many grid steps and each item carries its
    ``distance``. Prices are inclusive minor units. ``dietary_tag`` and
    ``exclude_allergen`` repeat (``?dietary_tag=vegan&dietary_tag=halal``).
    Bad filters - unknown zone or allergen, ``min_price > max_price``,
    ``max_distance`` without ``zone`` - are 422s naming the field.
    """
    total, rows = await service.page_public_dishes(
        db, filters, limit=limit, offset=offset
    )
    return DishPage(
        items=[_public_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@public_dish_router.get("/{dish_id}", response_model=PublicDishOut)
async def get_public_dish(dish_id: uuid.UUID, db: DbSession) -> PublicDishOut:
    return _public_out(await service.get_public_dish(db, dish_id))

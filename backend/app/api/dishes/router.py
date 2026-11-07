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

* GET /api/dishes?q=&cook_id=&limit=&offset=  - active dishes, name search,
  simple pagination
* GET /api/dishes/{id}                        - one active dish (deactivated
  dishes answer 404 - hidden means gone to the public)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.auth.dependencies import CookRequired
from app.api.deps import DbSession
from app.api.dishes import service
from app.api.dishes.models import Dish
from app.api.dishes.schemas import (
    DishCreateRequest,
    DishOut,
    DishPage,
    DishPatchRequest,
    PublicDishOut,
)

dish_router = APIRouter(prefix="/api/me/dishes", tags=["dishes"])

# Public, unauthenticated by design (see the route docstrings).
public_dish_router = APIRouter(prefix="/api/dishes", tags=["dishes"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100, description="page size")]
PageOffset = Annotated[int, Query(ge=0, description="rows to skip")]
CookIdFilter = Annotated[uuid.UUID | None, Query(description="restrict to one cook")]


def _public_out(dish: Dish, cook_name: str | None) -> PublicDishOut:
    return PublicDishOut.model_validate(dish).model_copy(update={"cook_name": cook_name})


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
    q: Annotated[
        str | None, Query(max_length=120, description="name substring")
    ] = None,
    cook_id: CookIdFilter = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> DishPage:
    """Public menu: active dishes only. ``q`` is a case-insensitive LIKE
    (``%``/``_`` escaped); blank search terms are treated as absent."""
    query = q.strip() if q and q.strip() else None
    total, rows = await service.page_public_dishes(
        db, query=query, cook_id=cook_id, limit=limit, offset=offset
    )
    return DishPage(
        items=[_public_out(dish, name) for dish, name in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@public_dish_router.get("/{dish_id}", response_model=PublicDishOut)
async def get_public_dish(dish_id: uuid.UUID, db: DbSession) -> PublicDishOut:
    dish, cook_name = await service.get_public_dish(db, dish_id)
    return _public_out(dish, cook_name)

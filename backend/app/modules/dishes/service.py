"""Dish business logic: cook-owned CRUD and the public menu read.

Ownership rule in one sentence: every per-dish query filters on ``cook_id``
*before* the row is handed back, so a foreign cook's dish simply does not
exist from the requester's point of view (404, never 403-with-details).
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from sqlalchemy import ColumnElement, FromClause, func, join, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.auth.models import CookProfile, User
from app.modules.dishes.models import Dish
from app.modules.dishes.schemas import (
    DishCreateRequest,
    DishPatchRequest,
    PublicDishQuery,
)
from app.modules.zones.grid import grid_distance_sql
from app.modules.zones.models import Zone
from app.modules.zones.service import resolve_zone
from app.shared.sql import (
    folded_contains,
    json_array_any_folded_contains,
    json_array_contains,
    json_array_contains_any,
)


class DishNotFoundError(NotFoundError):
    """Unknown id *or* somebody else's dish - identical answers on purpose.

    A 403 would confirm the row exists, which is information only the owner
    and the platform should have.
    """

    default_message = "Dish not found"


async def create_dish(
    session: AsyncSession, cook_id: uuid.UUID, payload: DishCreateRequest
) -> Dish:
    dish = Dish(cook_id=cook_id, **payload.model_dump())
    session.add(dish)
    await session.commit()
    await session.refresh(dish)
    return dish


async def get_owned_dish(
    session: AsyncSession, dish_id: uuid.UUID, cook_id: uuid.UUID
) -> Dish:
    """Fetch one of the cook's own dishes; anything else is a 404."""
    stmt = select(Dish).where(Dish.id == dish_id, Dish.cook_id == cook_id)
    dish = (await session.scalars(stmt)).one_or_none()
    if dish is None:
        raise DishNotFoundError
    return dish


async def list_cook_dishes(session: AsyncSession, cook_id: uuid.UUID) -> list[Dish]:
    """Dashboard list: the cook sees *all* their dishes, deactivated included
    (otherwise nothing could ever be reactivated). Newest first."""
    stmt = (
        select(Dish)
        .where(Dish.cook_id == cook_id)
        .order_by(Dish.created_at.desc(), Dish.id)
    )
    return list((await session.scalars(stmt)).all())


@dataclasses.dataclass(frozen=True)
class PublicDishRow:
    """One public-menu row: the dish plus what the listing shows about its cook."""

    dish: Dish
    cook_name: str | None
    zone: Zone | None
    distance: int | None = None  # only when the menu was queried with a zone


def _public_menu_from() -> FromClause:
    """dishes -> users (cook name) -> cooks -> zones (kitchen location).

    Outer joins past ``users``: a cook without a profile row or zone still
    lists (zone filters then simply never match them). Shared by the count
    and the page query so both always see the same rows.
    """
    return (
        join(Dish, User, User.id == Dish.cook_id)
        .outerjoin(CookProfile, CookProfile.user_id == Dish.cook_id)
        .outerjoin(Zone, Zone.id == CookProfile.zone_id)
    )


def _text_match(term: str) -> ColumnElement[bool]:
    """One search word found in the name, the description or an ingredient.

    ``term`` is already folded; ``folded_contains`` folds the column side the
    same way and escapes ``%``/``_``, so typed wildcards stay literal.
    """
    return or_(
        folded_contains(Dish.name, term),
        folded_contains(Dish.description, term),
        json_array_any_folded_contains(Dish.ingredients, term),
    )


def _menu_conditions(
    filters: PublicDishQuery, distance: ColumnElement[Any] | None
) -> list[Any]:
    """WHERE clauses for the public menu; every filter is optional and ANDed."""
    conditions: list[Any] = [Dish.active.is_(True)]
    # Text search: every word must match somewhere (words are ANDed, the
    # fields within one word ORed), in any order.
    conditions.extend(_text_match(term) for term in filters.terms)
    if filters.cook_id is not None:
        conditions.append(Dish.cook_id == filters.cook_id)
    if distance is not None:
        # No max_distance = "in this zone" (distance 0). Cooks without a zone
        # have a NULL distance, which already fails the comparison; the
        # explicit IS NOT NULL just says so in the SQL.
        conditions.append(Zone.id.is_not(None))
        conditions.append(distance <= (filters.max_distance or 0))
    if filters.min_price is not None:
        conditions.append(Dish.price >= filters.min_price)
    if filters.max_price is not None:
        conditions.append(Dish.price <= filters.max_price)
    for tag in filters.dietary_tag:  # must carry every requested tag
        conditions.append(json_array_contains(Dish.dietary_tags, tag))
    if filters.exclude_allergen:  # must declare none of them
        conditions.append(
            ~json_array_contains_any(Dish.allergens, filters.exclude_allergen)
        )
    return conditions


async def page_public_dishes(
    session: AsyncSession,
    filters: PublicDishQuery,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[PublicDishRow]]:
    """Paginated, filtered public menu: ``(total_matching, page_rows)``.

    Everything - filters, ``COUNT(*)`` and paging - runs in SQL, so ``total``
    is always the number of matches across all pages. The joins give each row
    its cook's name and zone without an N+1. An unknown ``zone`` slug is a
    422 (``UnknownZoneError``), not an empty page, so typos are visible.
    Order stays newest-first whether or not a zone is given.
    """
    origin = await resolve_zone(session, filters.zone) if filters.zone else None
    distance = grid_distance_sql(Zone.x, Zone.y, origin) if origin else None
    conditions = _menu_conditions(filters, distance)
    menu = _public_menu_from()

    total = (
        await session.scalar(
            select(func.count(Dish.id)).select_from(menu).where(*conditions)
        )
        or 0
    )
    distance_column = (distance if distance is not None else literal(None)).label(
        "distance"
    )
    stmt = (
        select(Dish, User.display_name, Zone, distance_column)
        .select_from(menu)
        .where(*conditions)
        .order_by(Dish.created_at.desc(), Dish.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return total, [
        PublicDishRow(dish=dish, cook_name=name, zone=zone, distance=dist)
        for dish, name, zone, dist in rows
    ]


async def get_public_dish(session: AsyncSession, dish_id: uuid.UUID) -> PublicDishRow:
    """One active dish with its cook's display name and zone.

    Deactivated dishes answer 404 here, same as unknown ids: to the public,
    hidden does not exist. (Cooks manage deactivated dishes through
    ``/api/me/dishes``.)
    """
    stmt = (
        select(Dish, User.display_name, Zone)
        .select_from(_public_menu_from())
        .where(Dish.id == dish_id, Dish.active.is_(True))
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise DishNotFoundError
    return PublicDishRow(dish=row[0], cook_name=row[1], zone=row[2])


async def update_dish(
    session: AsyncSession, dish: Dish, payload: DishPatchRequest
) -> Dish:
    # ``exclude_unset`` is what makes PATCH partial: only fields the client
    # actually sent are touched (an explicit null still counts as sent).
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(dish, field, value)
    await session.commit()
    await session.refresh(dish)
    return dish


async def delete_dish(session: AsyncSession, dish: Dish) -> None:
    """Hard delete. Day-to-day hiding is deactivation (``PATCH active=false``);
    this is the cook removing the row for good."""
    await session.delete(dish)
    await session.commit()

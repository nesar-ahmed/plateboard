"""Dish business logic: cook-owned CRUD and the public menu read.

Ownership rule in one sentence: every per-dish query filters on ``cook_id``
*before* the row is handed back, so a foreign cook's dish simply does not
exist from the requester's point of view (404, never 403-with-details).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.models import User
from app.api.dishes.models import Dish
from app.api.dishes.schemas import DishCreateRequest, DishPatchRequest
from app.core.exceptions import NotFoundError


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


async def page_public_dishes(
    session: AsyncSession,
    *,
    query: str | None = None,
    cook_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[tuple[Dish, str | None]]]:
    """Paginated public menu: ``(total_matching, page_rows)``.

    Rows are ``(dish, cook_display_name)`` pairs - the join to ``User`` is
    what gives the frontend cards a cook name without an N+1. ``icontains``
    compiles to a case-insensitive LIKE and ``autoescape=True`` neutralises
    ``%``/``_`` typed into the search box, so ``q`` is a literal substring.
    """
    conditions: list[Any] = [Dish.active.is_(True)]
    if query:
        conditions.append(Dish.name.icontains(query, autoescape=True))
    if cook_id is not None:
        conditions.append(Dish.cook_id == cook_id)

    total = (
        await session.scalar(
            select(func.count()).select_from(Dish).where(*conditions)
        )
        or 0
    )
    stmt = (
        select(Dish, User.display_name)
        .join(User, User.id == Dish.cook_id)
        .where(*conditions)
        .order_by(Dish.created_at.desc(), Dish.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return total, [(dish, display_name) for dish, display_name in rows]


async def get_public_dish(
    session: AsyncSession, dish_id: uuid.UUID
) -> tuple[Dish, str | None]:
    """One active dish with its cook's display name.

    Deactivated dishes answer 404 here, same as unknown ids: to the public,
    hidden does not exist. (Cooks manage deactivated dishes through
    ``/api/me/dishes``.)
    """
    stmt = (
        select(Dish, User.display_name)
        .join(User, User.id == Dish.cook_id)
        .where(Dish.id == dish_id, Dish.active.is_(True))
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise DishNotFoundError
    return row[0], row[1]


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

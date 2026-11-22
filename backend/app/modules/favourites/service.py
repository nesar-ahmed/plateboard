"""Favourite-dish business logic: a customer's saved list, and the cart from it.

Rules in one place:

* **Customers only** - the routes sit behind ``require_customer`` (a cook is
  a customer too; an admin-only account is not): 401 anonymous, 403 without
  the role. The list is private: every query filters on the caller.
* **Only available dishes can be saved** - an unknown or hidden dish is a
  404, the same answer as the public menu and the cart (to the public,
  hidden does not exist).
* **Not your own dish** - a cook saving one of their own dishes is a 422
  ``own_dish`` (as in the cart: cooks do not order from themselves).
* **At most** :data:`MAX_FAVOURITES` dishes (409 ``favourites_limit``).
  Hidden dishes still take up room - the customer removes them. The check
  and the insert are one SQL statement (``INSERT ... SELECT ... WHERE
  count < max``), so two concurrent adds can never overshoot the limit.
* **Saving is idempotent** - saving a dish already on the list changes
  nothing (the router answers 200 instead of 201); so is removing one that
  is not there (204 either way), so double taps on a heart are harmless.
* **Hidden dishes stay listed** with ``available = false`` (the cart's rule
  for deactivated dishes); they cannot go to the cart (409
  ``dish_unavailable``) until the cook publishes them again. A *deleted*
  dish leaves every list (FK CASCADE).
* **Cart from the list** - :func:`add_to_cart` adds a saved, available dish
  to the caller's account cart through the cart service, so every cart rule
  applies unchanged (lines grow, quantities 1..100, one cook per cart with
  ``replace_cart``, at most 50 lines).
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from sqlalchemy import DateTime, Insert, Select, Uuid, func, literal, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.auth.models import CookProfile, User
from app.modules.cart import service as cart_service
from app.modules.cart.schemas import CartItemAdd
from app.modules.dishes.models import Dish
from app.modules.dishes.service import DishNotFoundError, PublicDishRow
from app.modules.favourites.models import MAX_FAVOURITES, FavouriteDish
from app.modules.favourites.schemas import FavouriteCartAdd
from app.modules.zones.models import Zone
from app.shared.base import utcnow

type AnySelect = Select[*tuple[Any, ...]]

__all__ = [
    "FavouriteNotFoundError",
    "FavouriteUnavailableError",
    "FavouriteView",
    "FavouritesFullError",
    "OwnDishFavouriteError",
    "add_favourite",
    "add_to_cart",
    "get_favourite",
    "page_favourites",
    "remove_favourite",
]

# --- errors --------------------------------------------------------------------------


class FavouriteNotFoundError(NotFoundError):
    """The dish is not on the caller's list (or does not exist at all)."""

    default_message = "This dish is not in your favourites"


class OwnDishFavouriteError(ValidationFailedError):
    default_message = "You cannot add your own dish to your favourites"

    def __init__(self) -> None:
        super().__init__(
            details=[
                {
                    "field": "dish_id",
                    "type": "own_dish",
                    "message": "cooks cannot add their own dishes to their favourites",
                }
            ]
        )


class FavouritesFullError(ConflictError):
    code = "favourites_limit"
    default_message = (
        f"You can keep at most {MAX_FAVOURITES} favourite dishes - remove one first"
    )

    def __init__(self) -> None:
        super().__init__(details={"max_favourites": MAX_FAVOURITES})


class FavouriteUnavailableError(ConflictError):
    """A saved dish its cook has hidden: listed, but not orderable now."""

    code = "dish_unavailable"
    default_message = (
        "This dish is not available right now - its cook has hidden it from the menu"
    )


# --- read model ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FavouriteView:
    """One saved dish with what the public menu shows about it."""

    favourite: FavouriteDish
    row: PublicDishRow

    @property
    def available(self) -> bool:
        """Orderable right now - the same definition as a cart line's."""
        return self.row.dish.active


def _favourites_select(user_id: uuid.UUID) -> AnySelect:
    """The caller's favourites with each dish's cook name and kitchen zone
    (favourite -> dish -> cook account -> cook profile -> zone; outer joins
    past the account, as on the public menu)."""
    return (
        select(FavouriteDish, Dish, User.display_name, Zone)
        .join(Dish, Dish.id == FavouriteDish.dish_id)
        .join(User, User.id == Dish.cook_id)
        .outerjoin(CookProfile, CookProfile.user_id == Dish.cook_id)
        .outerjoin(Zone, Zone.id == CookProfile.zone_id)
        .where(FavouriteDish.user_id == user_id)
        # A dish hidden or edited since it was loaded must read fresh.
        .execution_options(populate_existing=True)
    )


def _view(row: Any) -> FavouriteView:
    favourite, dish, cook_name, zone = row
    return FavouriteView(
        favourite=favourite,
        row=PublicDishRow(dish=dish, cook_name=cook_name, zone=zone),
    )


async def page_favourites(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = 20, offset: int = 0
) -> tuple[int, int, list[FavouriteView]]:
    """Newest first: ``(total, unavailable, page)`` - ``total`` counts every
    saved dish, ``unavailable`` the hidden ones among them."""
    counts = (
        await session.execute(
            select(func.count(), func.count().filter(Dish.active.is_(False)))
            .select_from(FavouriteDish)
            .join(Dish, Dish.id == FavouriteDish.dish_id)
            .where(FavouriteDish.user_id == user_id)
        )
    ).one()
    stmt = (
        _favourites_select(user_id)
        .order_by(FavouriteDish.created_at.desc(), FavouriteDish.dish_id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return counts[0] or 0, counts[1] or 0, [_view(row) for row in rows]


async def get_favourite(
    session: AsyncSession, user_id: uuid.UUID, dish_id: uuid.UUID
) -> FavouriteView:
    """One dish of the caller's list (hidden ones included); 404 otherwise."""
    row = (
        await session.execute(
            _favourites_select(user_id).where(FavouriteDish.dish_id == dish_id)
        )
    ).one_or_none()
    if row is None:
        raise FavouriteNotFoundError
    return _view(row)


# --- mutations -----------------------------------------------------------------------


def _insert_below_limit(
    session: AsyncSession, user_id: uuid.UUID, dish_id: uuid.UUID
) -> Insert:
    """``INSERT ... SELECT <row> WHERE (the user's count) < MAX ON CONFLICT DO
    NOTHING RETURNING dish_id`` - one statement, so the limit check and the
    insert are atomic (SQLite serializes writers; PostgreSQL would need the
    same statement under a per-user lock to be strict). Returns a row only
    when a favourite was actually added."""
    saved = (
        select(func.count())
        .select_from(FavouriteDish)
        .where(FavouriteDish.user_id == user_id)
        .scalar_subquery()
    )
    new_row = select(
        literal(user_id, Uuid()),
        literal(dish_id, Uuid()),
        literal(utcnow(), DateTime()),
    ).where(saved < MAX_FAVOURITES)
    dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
    return (
        dialect.insert(FavouriteDish)
        .from_select(["user_id", "dish_id", "created_at"], new_row)
        .on_conflict_do_nothing(
            index_elements=[FavouriteDish.user_id, FavouriteDish.dish_id]
        )
        .returning(FavouriteDish.dish_id)
    )


async def add_favourite(
    session: AsyncSession, user_id: uuid.UUID, dish_id: uuid.UUID
) -> tuple[bool, FavouriteView]:
    """Save an available dish: ``(added_now, favourite)``. Already on the list
    -> ``added_now`` is False and nothing changes."""
    dish = await session.get(Dish, dish_id)
    if dish is None or not dish.active:
        raise DishNotFoundError
    if dish.cook_id == user_id:
        raise OwnDishFavouriteError

    try:
        added = (
            await session.execute(_insert_below_limit(session, user_id, dish_id))
        ).scalar_one_or_none() is not None
    except IntegrityError:  # the dish was deleted a moment ago (FK)
        await session.rollback()
        raise DishNotFoundError from None
    if not added and await session.get(FavouriteDish, (user_id, dish_id)) is None:
        # Nothing inserted and not already saved: the list is full.
        await session.rollback()
        raise FavouritesFullError
    await session.commit()
    return added, await get_favourite(session, user_id, dish_id)


async def remove_favourite(
    session: AsyncSession, user_id: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Take a dish off the list - hidden ones too; not on it is a no-op."""
    favourite = await session.get(FavouriteDish, (user_id, dish_id))
    if favourite is not None:
        await session.delete(favourite)
        await session.commit()


async def add_to_cart(
    session: AsyncSession,
    user_id: uuid.UUID,
    dish_id: uuid.UUID,
    payload: FavouriteCartAdd,
) -> cart_service.CartView:
    """Put a saved dish in the caller's account cart and return the cart.

    404 if the dish is not on the list, 409 ``dish_unavailable`` while its
    cook hides it; then the cart's own rules (``cart_service.add_item``):
    409 ``different_cook`` unless ``replace_cart``, 422
    ``quantity_unavailable`` past 100 portions, 409 ``cart_full``.
    """
    favourite = await get_favourite(session, user_id, dish_id)
    if not favourite.available:
        raise FavouriteUnavailableError
    owner = cart_service.CartOwner(user_id=user_id)
    await cart_service.add_item(
        session,
        owner,
        CartItemAdd(
            dish_id=dish_id,
            quantity=payload.quantity,
            replace_cart=payload.replace_cart,
        ),
    )
    return await cart_service.get_cart(session, owner)

"""Cart business logic - for guests and signed-in users alike.

Who owns the cart (:class:`CartOwner`):

* a signed-in user -> their account cart (``carts.user_id``);
* a guest -> the cart behind the ``plateboard_cart`` cookie token (only its
  SHA-256 is stored). Carts are created lazily on the first add; a new guest
  cart hands its token back so the router can set the cookie.

Rules in one place:

* only *active* dishes can be added (unknown or deactivated -> 404, the same
  answer as the public menu), and a signed-in cook never their own dish
  (422 ``own_dish``);
* **one cook per cart**: a dish from another cook is a 409 ``different_cook``
  unless the caller asks to ``replace_cart``, which empties it first;
* a line's quantity stays within ``1..100`` - going outside is a 422
  ``quantity_unavailable``, never a silent clamp;
* at most :data:`MAX_CART_LINES` distinct dishes (409 ``cart_full``);
* a dish deactivated after it was added stays listed as unavailable: left out
  of the totals, can only be removed (PATCH -> 409).

At login, :func:`claim_guest_cart` moves the guest cart to the account (see
there for how it combines with a cart the account already had).

Prices are always the dish's *current* price; freezing a price is the job of
order placement, not of the cart.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.auth.models import User
from app.modules.auth.security import hash_token, new_session_token
from app.modules.cart.models import Cart, CartItem
from app.modules.cart.schemas import (
    MAX_CART_LINES,
    MAX_QUANTITY,
    MIN_QUANTITY,
    CartItemAdd,
    CartItemUpdate,
)
from app.modules.dishes.models import Dish
from app.modules.dishes.service import DishNotFoundError

# --- errors --------------------------------------------------------------------------


class CartItemNotFoundError(NotFoundError):
    default_message = "This dish is not in your cart"


class CartFullError(ConflictError):
    code = "cart_full"
    default_message = f"A cart holds at most {MAX_CART_LINES} different dishes"


class DishUnavailableError(ConflictError):
    """The dish was deactivated after it went into the cart."""

    code = "dish_unavailable"
    default_message = "This dish is no longer available; remove it from the cart"


class DifferentCookError(ConflictError):
    """The cart already holds another cook's dishes (one cook per order).

    ``details`` names the cart's cook so a client can ask "start a new cart?"
    and retry with ``replace_cart: true``.
    """

    code = "different_cook"
    default_message = "Your cart holds dishes from another cook"

    def __init__(
        self, *, cart_cook_id: uuid.UUID, cart_cook_name: str | None, dish_cook_id: uuid.UUID
    ) -> None:
        who = cart_cook_name or "another cook"
        super().__init__(
            f"Your cart holds dishes from {who}; an order comes from one cook",
            details={
                "cart_cook_id": str(cart_cook_id),
                "cart_cook_name": cart_cook_name,
                "dish_cook_id": str(dish_cook_id),
            },
        )


class OwnDishError(ValidationFailedError):
    default_message = "You cannot order your own dish"

    def __init__(self) -> None:
        super().__init__(
            details=[
                {
                    "field": "dish_id",
                    "type": "own_dish",
                    "message": "cooks cannot add their own dishes to a cart",
                }
            ]
        )


class QuantityUnavailableError(ValidationFailedError):
    default_message = "Quantity not available"

    def __init__(self, *, requested: int) -> None:
        reason = (
            "quantity must be at least 1 (remove the dish instead)"
            if requested < MIN_QUANTITY
            else f"at most {MAX_QUANTITY} portions of one dish per order"
        )
        super().__init__(
            details=[
                {
                    "field": "quantity",
                    "type": "quantity_unavailable",
                    "message": reason,
                    "max_quantity": MAX_QUANTITY,
                }
            ]
        )


# --- owner + lookups -----------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CartOwner:
    """Who is asking: a signed-in user id, else the guest cookie token (which
    may be absent, unknown or stale - all simply mean "no cart yet")."""

    user_id: uuid.UUID | None
    guest_token: str | None = None

    @property
    def kind(self) -> Literal["guest", "user"]:
        return "guest" if self.user_id is None else "user"


async def _find_cart(session: AsyncSession, owner: CartOwner) -> Cart | None:
    if owner.user_id is not None:
        return await session.scalar(select(Cart).where(Cart.user_id == owner.user_id))
    if owner.guest_token:
        return await session.scalar(
            select(Cart).where(Cart.token_hash == hash_token(owner.guest_token))
        )
    return None


async def _get_or_create_cart(
    session: AsyncSession, owner: CartOwner
) -> tuple[Cart, str | None]:
    """``(cart, new_guest_token)`` - the token only when a guest cart was made."""
    cart = await _find_cart(session, owner)
    if cart is not None:
        return cart, None
    token: str | None = None
    if owner.user_id is not None:
        cart = Cart(user_id=owner.user_id)
    else:
        token, token_hash = new_session_token()
        cart = Cart(token_hash=token_hash)
    session.add(cart)
    await session.flush()
    return cart, token


async def _cart_cook_id(session: AsyncSession, cart_id: uuid.UUID) -> uuid.UUID | None:
    """The cook whose dishes the cart holds (None while empty)."""
    return await session.scalar(
        select(Dish.cook_id)
        .join(CartItem, CartItem.dish_id == Dish.id)
        .where(CartItem.cart_id == cart_id)
        .limit(1)
    )


# --- read model ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CartLine:
    item: CartItem
    dish: Dish

    @property
    def available(self) -> bool:
        return self.dish.active

    @property
    def line_total(self) -> int:
        return self.dish.price * self.item.quantity


@dataclasses.dataclass(frozen=True)
class CartView:
    owner: Literal["guest", "user"]
    lines: list[CartLine]
    cart_id: uuid.UUID | None = None  # None: the owner has no cart row (yet)
    cook_id: uuid.UUID | None = None
    cook_name: str | None = None

    @property
    def item_count(self) -> int:
        return sum(line.item.quantity for line in self.lines if line.available)

    @property
    def total(self) -> int:
        return sum(line.line_total for line in self.lines if line.available)

    @property
    def unavailable_count(self) -> int:
        return sum(1 for line in self.lines if not line.available)


async def get_cart(session: AsyncSession, owner: CartOwner) -> CartView:
    """The owner's cart, newest additions first (empty if none exists yet -
    reading never creates a cart or a cookie)."""
    cart = await _find_cart(session, owner)
    if cart is None:
        return CartView(owner=owner.kind, lines=[])
    stmt = (
        select(CartItem, Dish, User.display_name)
        .join(Dish, Dish.id == CartItem.dish_id)
        .join(User, User.id == Dish.cook_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.created_at.desc(), CartItem.dish_id)
    )
    rows = (await session.execute(stmt)).all()
    lines = [CartLine(item=item, dish=dish) for item, dish, _name in rows]
    first = rows[0] if rows else None
    return CartView(
        owner=owner.kind,
        lines=lines,
        cart_id=cart.id,
        cook_id=first[1].cook_id if first else None,
        cook_name=first[2] if first else None,
    )


# --- mutations -----------------------------------------------------------------------


def _check_quantity(quantity: int) -> None:
    if not MIN_QUANTITY <= quantity <= MAX_QUANTITY:
        raise QuantityUnavailableError(requested=quantity)


async def add_item(
    session: AsyncSession, owner: CartOwner, payload: CartItemAdd
) -> str | None:
    """Put ``payload.quantity`` portions of a dish in the owner's cart (adding
    to an existing line). Returns a new guest token if a guest cart was
    created (the router sets it as the cookie), else ``None``.

    Retried once if a concurrent request created the same cart or line
    between our read and our insert (unique/primary-key conflict).
    """
    dish = await session.get(Dish, payload.dish_id)
    if dish is None or not dish.active:
        raise DishNotFoundError
    if owner.user_id is not None and dish.cook_id == owner.user_id:
        raise OwnDishError
    # Plain values up front: a rollback (retry path) expires loaded objects,
    # and touching an expired attribute would mean implicit IO under asyncio.
    dish_id, dish_cook_id = dish.id, dish.cook_id

    for attempt in range(2):
        cart, token = await _get_or_create_cart(session, owner)
        cart_id = cart.id
        cart_cook_id = await _cart_cook_id(session, cart_id)
        if cart_cook_id is not None and cart_cook_id != dish_cook_id:
            if not payload.replace_cart:
                raise DifferentCookError(
                    cart_cook_id=cart_cook_id,
                    cart_cook_name=await session.scalar(
                        select(User.display_name).where(User.id == cart_cook_id)
                    ),
                    dish_cook_id=dish_cook_id,
                )
            await session.execute(delete(CartItem).where(CartItem.cart_id == cart_id))

        item = await session.get(CartItem, (cart_id, dish_id))
        if item is not None:
            _check_quantity(item.quantity + payload.quantity)
            item.quantity += payload.quantity
        else:
            _check_quantity(payload.quantity)
            lines = await session.scalar(
                select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart_id)
            )
            if (lines or 0) >= MAX_CART_LINES:
                raise CartFullError
            session.add(CartItem(cart_id=cart_id, dish_id=dish_id, quantity=payload.quantity))
        try:
            await session.commit()
            return token
        except IntegrityError:
            await session.rollback()
            if attempt == 1:
                raise
            # The dish may have changed meanwhile; re-check before retrying.
            reloaded = await session.get(Dish, dish_id)
            if reloaded is None or not reloaded.active:
                raise DishNotFoundError from None
    return None  # pragma: no cover - the loop always returns or raises


async def _get_item(
    session: AsyncSession, owner: CartOwner, dish_id: uuid.UUID
) -> CartItem:
    cart = await _find_cart(session, owner)
    item = await session.get(CartItem, (cart.id, dish_id)) if cart else None
    if item is None:
        raise CartItemNotFoundError
    return item


async def update_item(
    session: AsyncSession, owner: CartOwner, dish_id: uuid.UUID, payload: CartItemUpdate
) -> None:
    """Set (``quantity``) or adjust (``delta``) one line's quantity."""
    item = await _get_item(session, owner, dish_id)
    dish = await session.get(Dish, dish_id)
    if dish is None or not dish.active:  # FK cascade removes deleted dishes
        raise DishUnavailableError
    if payload.quantity is not None:
        wanted = payload.quantity
    else:
        assert payload.delta is not None  # guaranteed by CartItemUpdate
        wanted = item.quantity + payload.delta
    _check_quantity(wanted)
    item.quantity = wanted
    await session.commit()


async def remove_item(session: AsyncSession, owner: CartOwner, dish_id: uuid.UUID) -> None:
    item = await _get_item(session, owner, dish_id)
    await session.delete(item)
    await session.commit()


async def clear_cart(session: AsyncSession, owner: CartOwner) -> None:
    """Empty the cart (the cart row - and a guest's cookie - stay valid)."""
    cart = await _find_cart(session, owner)
    if cart is not None:
        await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await session.commit()


# --- login: guest cart -> account ------------------------------------------------------


async def claim_guest_cart(
    session: AsyncSession, user_id: uuid.UUID, guest_token: str | None
) -> None:
    """Move the guest cart behind ``guest_token`` to the account ``user_id``.

    Called right after a successful login (so "log in to check out" keeps the
    dishes). How it combines with a cart the account already had:

    * the user's *own* dishes are dropped from the guest cart first (a cook
      cannot order from themselves);
    * nothing left -> the guest cart is discarded, the account cart is kept;
    * no account cart -> the guest cart simply becomes the account cart;
    * account cart from the **same cook** -> lines merge (quantities add up,
      capped at 100);
    * account cart empty or from **another cook** -> the guest cart, i.e. what
      the user was choosing just now, replaces it (one cook per order).
    """
    if not guest_token:
        return
    guest = await session.scalar(
        select(Cart).where(Cart.token_hash == hash_token(guest_token), Cart.user_id.is_(None))
    )
    if guest is None:
        return
    guest_id = guest.id

    await session.execute(
        delete(CartItem).where(
            CartItem.cart_id == guest_id,
            CartItem.dish_id.in_(select(Dish.id).where(Dish.cook_id == user_id)),
        )
    )
    guest_items = list(
        (await session.scalars(select(CartItem).where(CartItem.cart_id == guest_id))).all()
    )
    if not guest_items:
        await session.delete(guest)
        await session.commit()
        return

    account = await session.scalar(select(Cart).where(Cart.user_id == user_id))
    if account is not None:
        account_cook = await _cart_cook_id(session, account.id)
        if account_cook is not None and account_cook == await _cart_cook_id(session, guest_id):
            for guest_item in guest_items:
                existing = await session.get(CartItem, (account.id, guest_item.dish_id))
                if existing is not None:
                    existing.quantity = min(MAX_QUANTITY, existing.quantity + guest_item.quantity)
                else:
                    session.add(
                        CartItem(
                            cart_id=account.id,
                            dish_id=guest_item.dish_id,
                            quantity=guest_item.quantity,
                        )
                    )
            await session.delete(guest)
            await session.commit()
            return
        # Different cook (or empty): the guest cart wins. Delete the old cart
        # *first* - one cart per account is a UNIQUE constraint, and the unit
        # of work would otherwise run our UPDATE before its DELETE.
        await session.delete(account)
        await session.flush()

    guest.token_hash = None
    guest.user_id = user_id
    await session.commit()

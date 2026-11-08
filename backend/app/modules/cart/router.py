"""HTTP routes for the cart (``/api/cart``) - guests and signed-in users.

* GET    /api/cart                  - the cart (newest additions first)
* POST   /api/cart/items            - add a dish (adds to an existing line)
* PATCH  /api/cart/items/{dish_id}  - set ``quantity`` or adjust by ``delta``
* DELETE /api/cart/items/{dish_id}  - remove a dish
* DELETE /api/cart                  - empty the cart

No login required: a signed-in caller uses their account cart, a guest the
cart behind the HTTP-only ``plateboard_cart`` cookie, which the first add sets.
Logging in moves a guest cart to the account (``POST /api/auth/login``), so
checkout can demand a login without losing anything. Every endpoint answers
200 with the whole cart, so the client can redraw from any response.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import DbSession
from app.modules.auth.dependencies import OptionalUser
from app.modules.cart import service
from app.modules.cart.cookies import (
    clear_guest_cookie,
    read_guest_token,
    set_guest_cookie,
)
from app.modules.cart.schemas import (
    MAX_QUANTITY,
    CartCookOut,
    CartItemAdd,
    CartItemOut,
    CartItemUpdate,
    CartOut,
)

cart_router = APIRouter(prefix="/api/cart", tags=["cart"])


def resolve_owner(request: Request, user: OptionalUser) -> service.CartOwner:
    """Signed-in -> the account cart (a guest cookie is ignored until login
    claims it); otherwise the guest cookie's cart, if any."""
    if user is not None:
        return service.CartOwner(user_id=user.id)
    return service.CartOwner(user_id=None, guest_token=read_guest_token(request))


Owner = Annotated[service.CartOwner, Depends(resolve_owner)]


def _cart_out(view: service.CartView) -> CartOut:
    return CartOut(
        owner=view.owner,
        cook=CartCookOut(id=view.cook_id, name=view.cook_name) if view.cook_id else None,
        items=[
            CartItemOut(
                dish_id=line.dish.id,
                name=line.dish.name,
                price=line.dish.price,
                quantity=line.item.quantity,
                line_total=line.line_total,
                available=line.available,
                max_quantity=MAX_QUANTITY,
                added_at=line.item.created_at,
            )
            for line in view.lines
        ],
        item_count=view.item_count,
        total=view.total,
        unavailable_count=view.unavailable_count,
    )


async def _current_cart(
    db: DbSession, owner: service.CartOwner, response: Response
) -> CartOut:
    view = await service.get_cart(db, owner)
    # A guest cookie that matches no cart (expired, claimed at login, forged)
    # is dead weight - drop it so the next add starts cleanly.
    if owner.user_id is None and owner.guest_token and view.cart_id is None:
        clear_guest_cookie(response)
    return _cart_out(view)


@cart_router.get("", response_model=CartOut)
async def get_cart(owner: Owner, db: DbSession, response: Response) -> CartOut:
    """Reading never creates a cart or sets a cookie."""
    return await _current_cart(db, owner, response)


@cart_router.delete("", response_model=CartOut)
async def clear_cart(owner: Owner, db: DbSession, response: Response) -> CartOut:
    await service.clear_cart(db, owner)
    return await _current_cart(db, owner, response)


@cart_router.post("/items", response_model=CartOut)
async def add_to_cart(
    payload: CartItemAdd, owner: Owner, db: DbSession, response: Response
) -> CartOut:
    """Add ``quantity`` (default 1) portions of an active dish; a dish already
    in the cart grows its line. One cook per cart: another cook's dish is a
    409 ``different_cook`` unless ``replace_cart`` is true."""
    token = await service.add_item(db, owner, payload)
    if token is not None:
        set_guest_cookie(response, token)
        owner = service.CartOwner(user_id=None, guest_token=token)
    return await _current_cart(db, owner, response)


@cart_router.patch("/items/{dish_id}", response_model=CartOut)
async def update_cart_item(
    dish_id: uuid.UUID,
    payload: CartItemUpdate,
    owner: Owner,
    db: DbSession,
    response: Response,
) -> CartOut:
    """``{"quantity": n}`` sets the quantity; ``{"delta": 1}`` / ``{"delta": -1}``
    increases / decreases it. The result must stay within 1..100."""
    await service.update_item(db, owner, dish_id, payload)
    return await _current_cart(db, owner, response)


@cart_router.delete("/items/{dish_id}", response_model=CartOut)
async def remove_from_cart(
    dish_id: uuid.UUID, owner: Owner, db: DbSession, response: Response
) -> CartOut:
    await service.remove_item(db, owner, dish_id)
    return await _current_cart(db, owner, response)

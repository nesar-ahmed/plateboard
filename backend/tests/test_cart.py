"""Cart API (``/api/cart``): guests and users, one cook per cart, login claim.

Acceptance rules under test:

* anyone has a cart: a signed-in user their account cart, a guest the cart
  behind the HTTP-only ``plateboard_cart`` cookie (set by the first add; only
  its hash is stored); carts are private to their owner;
* one cook per cart - another cook's dish is a 409 ``different_cook`` unless
  ``replace_cart`` starts a new cart with it;
* quantities are 1..100 per dish, set (``quantity``) or adjusted (``delta``),
  never silently clamped; a signed-in cook cannot add their own dish;
* logging in moves the guest cart to the account (own dishes dropped; same
  cook -> merged; other cook or empty account cart -> guest cart wins);
* totals use current prices and skip dishes deactivated after being added;
  deleting a dish or an account removes its cart lines (CASCADE).
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.modules.auth.models import User
from app.modules.cart import service as cart_service
from app.modules.cart.models import Cart, CartItem

CART = "/api/cart"
ITEMS = "/api/cart/items"
COOKIE = "plateboard_cart"

DISHES = {
    # key: (cook email, name, price, portions)
    "curry": ("chef-a@example.com", "Veg curry", 800, 5),
    "pot": ("chef-a@example.com", "Family biryani pot", 1250, 120),
    "tart": ("chef-a@example.com", "Custard tart", 500, 2),
    "pizza": ("chef-b@example.com", "Pizza margherita", 900, 6),
}
COOK_NAMES = {"chef-a@example.com": "Chef Ana", "chef-b@example.com": "Chef Bruno"}
BUYER = "buyer@example.com"


@pytest.fixture
async def shop(accounts) -> SimpleNamespace:
    """Two cooks with DISHES, a registered (not logged-in) customer, and the
    client left as an anonymous guest with an empty cookie jar."""
    ids: dict[str, str] = {}
    for cook, display_name in COOK_NAMES.items():
        await accounts.cook(cook)
        await accounts.client.patch("/api/me/profile", json={"display_name": display_name})
        for key, (owner, name, price, portions) in DISHES.items():
            if owner != cook:
                continue
            created = await accounts.client.post(
                "/api/me/dishes", json={"name": name, "price": price, "portions": portions}
            )
            assert created.status_code == 201, created.text
            ids[key] = created.json()["id"]
        await accounts.client.post("/api/auth/logout")
    await accounts.register(BUYER)
    accounts.client.cookies.clear()
    return SimpleNamespace(client=accounts.client, accounts=accounts, ids=ids)


async def add(shop, key: str, quantity: int | None = None, **extra):
    body: dict = {"dish_id": shop.ids[key], **extra}
    if quantity is not None:
        body["quantity"] = quantity
    return await shop.client.post(ITEMS, json=body)


async def cart(shop) -> dict:
    response = await shop.client.get(CART)
    assert response.status_code == 200, response.text
    return response.json()


async def login(shop, email: str = BUYER):
    response = await shop.accounts.login(email)
    assert response.status_code == 200, response.text
    return response


async def logout(shop) -> None:
    assert (await shop.client.post("/api/auth/logout")).status_code == 204


def set_cart_cookie(shop, value: str) -> None:
    """Plant a cart cookie the way the server's own ends up in the jar (httpx
    files ``testserver`` cookies under ``testserver.local``), so a later
    deletion by the server really replaces it."""
    shop.client.cookies.set(COOKIE, value, domain="testserver.local", path="/")


def quantities(body: dict) -> dict[str, int]:
    return {item["name"]: item["quantity"] for item in body["items"]}


def assert_error(response, status: int, code: str, detail_type: str | None = None) -> None:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    if detail_type is not None:
        assert error["details"][0]["type"] == detail_type, error


async def cart_rows() -> int:
    async with get_sessionmaker()() as session:
        return await session.scalar(select(func.count()).select_from(Cart)) or 0


# --- guests ------------------------------------------------------------------------------


async def test_guest_starts_with_an_empty_cart_and_no_cookie(shop) -> None:
    response = await shop.client.get(CART)
    assert response.status_code == 200
    assert response.json() == {
        "owner": "guest",
        "cook": None,
        "items": [],
        "item_count": 0,
        "total": 0,
        "unavailable_count": 0,
    }
    assert "set-cookie" not in response.headers  # reading never creates a cart
    assert await cart_rows() == 0


async def test_guest_add_sets_an_httponly_cart_cookie(shop) -> None:
    response = await add(shop, "curry")
    assert response.status_code == 200, response.text
    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    body = response.json()
    assert body["owner"] == "guest"
    assert quantities(body) == {"Veg curry": 1}
    # The cookie finds the same cart again.
    assert quantities(await cart(shop)) == {"Veg curry": 1}


async def test_only_the_token_hash_is_stored(shop) -> None:
    await add(shop, "curry")
    token = shop.client.cookies[COOKIE]
    async with get_sessionmaker()() as session:
        stored = await session.scalar(select(Cart.token_hash))
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert stored != token


async def test_guest_carts_are_private(shop) -> None:
    await add(shop, "curry", 2)
    mine = shop.client.cookies[COOKIE]
    shop.client.cookies.clear()  # another browser
    assert (await cart(shop))["items"] == []
    assert_error(await shop.client.delete(f"{ITEMS}/{shop.ids['curry']}"), 404, "not_found")
    set_cart_cookie(shop, mine)
    assert quantities(await cart(shop)) == {"Veg curry": 2}


async def test_forged_or_stale_cookie_is_dropped(shop) -> None:
    set_cart_cookie(shop, "forged-token")
    response = await shop.client.get(CART)
    assert response.json()["items"] == []
    assert f"{COOKIE}=" in response.headers["set-cookie"]  # deletion
    assert COOKIE not in shop.client.cookies
    # Adding afterwards starts a fresh cart with a fresh token.
    await add(shop, "curry")
    assert shop.client.cookies[COOKIE] != "forged-token"


# --- signed-in users -------------------------------------------------------------------------


async def test_signed_in_user_has_an_account_cart(shop) -> None:
    await login(shop)
    response = await add(shop, "curry")
    assert response.json()["owner"] == "user"
    assert "set-cookie" not in response.headers  # no guest cookie needed
    await logout(shop)
    assert (await cart(shop))["items"] == []  # the guest sees nothing
    await login(shop)
    assert quantities(await cart(shop)) == {"Veg curry": 1}  # kept on the account


async def test_cook_cannot_add_own_dish_but_can_order_from_others(shop) -> None:
    await login(shop, "chef-a@example.com")
    assert_error(await add(shop, "curry"), 422, "validation_failed", "own_dish")
    assert (await add(shop, "pizza")).status_code == 200


# --- adding + one cook per cart -----------------------------------------------------------------


async def test_add_returns_the_whole_cart(shop) -> None:
    body = (await add(shop, "curry", 2)).json()
    assert body["cook"]["name"] == "Chef Ana"
    assert body["item_count"] == 2
    assert body["total"] == 1600
    item = body["items"][0]
    assert item["name"] == "Veg curry"
    assert (item["price"], item["quantity"], item["line_total"]) == (800, 2, 1600)
    assert item["available"] is True
    assert item["max_quantity"] == 100
    assert item["added_at"].endswith("Z") or item["added_at"].endswith("+00:00")


async def test_adding_again_grows_the_line_and_order_is_newest_first(shop) -> None:
    await add(shop, "curry")
    await add(shop, "tart")
    body = (await add(shop, "curry", 2)).json()
    assert [item["name"] for item in body["items"]] == ["Custard tart", "Veg curry"]
    assert quantities(body) == {"Veg curry": 3, "Custard tart": 1}
    assert body["total"] == 3 * 800 + 500


async def test_dish_from_another_cook_is_refused(shop) -> None:
    await add(shop, "curry")
    response = await add(shop, "pizza")
    assert_error(response, 409, "different_cook")
    details = response.json()["error"]["details"]
    assert details["cart_cook_name"] == "Chef Ana"
    assert "Chef Ana" in response.json()["error"]["message"]
    assert quantities(await cart(shop)) == {"Veg curry": 1}  # untouched


async def test_replace_cart_starts_over_with_the_new_cook(shop) -> None:
    await add(shop, "curry", 3)
    await add(shop, "tart")
    body = (await add(shop, "pizza", 2, replace_cart=True)).json()
    assert quantities(body) == {"Pizza margherita": 2}
    assert body["cook"]["name"] == "Chef Bruno"


async def test_replace_cart_is_harmless_for_the_same_cook(shop) -> None:
    await add(shop, "curry")
    body = (await add(shop, "tart", replace_cart=True)).json()
    assert quantities(body) == {"Veg curry": 1, "Custard tart": 1}


async def test_emptied_cart_accepts_any_cook(shop) -> None:
    await add(shop, "curry")
    await shop.client.delete(f"{ITEMS}/{shop.ids['curry']}")
    assert (await add(shop, "pizza")).status_code == 200


async def test_unknown_deactivated_or_invalid_dish(shop) -> None:
    assert_error(await shop.client.post(ITEMS, json={"dish_id": str(uuid.uuid4())}), 404, "not_found")
    assert_error(await shop.client.post(ITEMS, json={"dish_id": "nope"}), 422, "validation_failed")
    await login(shop, "chef-a@example.com")
    await shop.client.patch(f"/api/me/dishes/{shop.ids['tart']}", json={"active": False})
    await logout(shop)
    assert_error(await add(shop, "tart"), 404, "not_found")


async def test_cart_full(shop, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cart_service, "MAX_CART_LINES", 2)
    await add(shop, "curry")
    await add(shop, "tart")
    assert_error(await add(shop, "pot"), 409, "cart_full")
    assert (await add(shop, "curry")).status_code == 200  # growing a line is fine


async def test_concurrent_add_of_the_same_dish_is_retried(
    shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between the service's "is this dish already in the cart?" read and its
    INSERT, another request commits the same line. The primary key conflict
    must lead to a retry that grows that line - no error, no lost update."""
    await login(shop)
    await add(shop, "curry")  # the cart row exists; now race on a new line
    original_get = AsyncSession.get
    raced = False

    async def get_with_race(self, entity, ident, *args, **kwargs):
        nonlocal raced
        if entity is CartItem and not raced:
            raced = True
            cart_id, dish_id = ident
            async with get_sessionmaker()() as other:
                other.add(CartItem(cart_id=cart_id, dish_id=dish_id, quantity=1))
                await other.commit()
            return None
        return await original_get(self, entity, ident, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "get", get_with_race)
    response = await add(shop, "pot")
    assert raced
    assert response.status_code == 200, response.text
    assert quantities(response.json()) == {"Family biryani pot": 2, "Veg curry": 1}


# --- quantities ----------------------------------------------------------------------------


async def test_quantity_range_is_1_to_100_regardless_of_portions(shop) -> None:
    assert (await add(shop, "tart", 50)).status_code == 200  # portions=2 is no limit
    assert (await add(shop, "tart", 50)).status_code == 200  # exactly 100
    over = await add(shop, "tart", 1)
    assert_error(over, 422, "validation_failed", "quantity_unavailable")
    assert over.json()["error"]["details"][0]["max_quantity"] == 100
    assert quantities(await cart(shop)) == {"Custard tart": 100}  # not clamped


@pytest.mark.parametrize("bad", [0, -1, 101, "two"])
async def test_add_quantity_is_validated(shop, bad) -> None:
    assert_error(await add(shop, "curry", bad), 422, "validation_failed")


async def test_set_increase_and_decrease(shop) -> None:
    await add(shop, "curry", 2)
    url = f"{ITEMS}/{shop.ids['curry']}"
    assert quantities((await shop.client.patch(url, json={"delta": 1})).json()) == {"Veg curry": 3}
    assert quantities((await shop.client.patch(url, json={"delta": -2})).json()) == {"Veg curry": 1}
    body = (await shop.client.patch(url, json={"quantity": 40})).json()
    assert quantities(body) == {"Veg curry": 40}
    assert body["total"] == 40 * 800


async def test_quantity_bounds_on_update(shop) -> None:
    await add(shop, "curry")
    url = f"{ITEMS}/{shop.ids['curry']}"
    below = await shop.client.patch(url, json={"delta": -1})
    assert_error(below, 422, "validation_failed", "quantity_unavailable")
    assert "at least 1" in below.json()["error"]["details"][0]["message"]
    assert_error(
        await shop.client.patch(url, json={"delta": 100}), 422, "validation_failed", "quantity_unavailable"
    )
    assert_error(await shop.client.patch(url, json={"quantity": 101}), 422, "validation_failed")
    assert quantities(await cart(shop)) == {"Veg curry": 1}


@pytest.mark.parametrize(
    "body", [{}, {"quantity": 2, "delta": 1}, {"delta": 0}, {"quantity": 0}, {"quantity": None}]
)
async def test_update_body_needs_exactly_one_change(shop, body) -> None:
    await add(shop, "curry")
    response = await shop.client.patch(f"{ITEMS}/{shop.ids['curry']}", json=body)
    assert_error(response, 422, "validation_failed")


async def test_update_or_remove_a_dish_not_in_the_cart_is_404(shop) -> None:
    url = f"{ITEMS}/{shop.ids['curry']}"
    assert_error(await shop.client.patch(url, json={"delta": 1}), 404, "not_found")  # no cart
    await add(shop, "tart")
    assert_error(await shop.client.patch(url, json={"delta": 1}), 404, "not_found")  # no line
    assert_error(await shop.client.delete(url), 404, "not_found")


# --- removing ------------------------------------------------------------------------------


async def test_remove_and_clear(shop) -> None:
    await add(shop, "curry")
    await add(shop, "tart")
    body = (await shop.client.delete(f"{ITEMS}/{shop.ids['curry']}")).json()
    assert quantities(body) == {"Custard tart": 1}
    cleared = await shop.client.delete(CART)
    assert cleared.status_code == 200
    assert cleared.json()["items"] == [] and cleared.json()["cook"] is None
    assert (await shop.client.delete(CART)).status_code == 200  # idempotent
    assert shop.client.cookies.get(COOKIE)  # the guest cart stays valid


# --- login claims the guest cart ---------------------------------------------------------------


async def test_login_moves_the_guest_cart_to_the_account(shop) -> None:
    await add(shop, "curry", 2)
    await add(shop, "tart")
    response = await login(shop)
    assert f"{COOKIE}=" in response.headers.get("set-cookie", "")  # cleared
    assert COOKIE not in shop.client.cookies
    body = await cart(shop)
    assert body["owner"] == "user"
    assert quantities(body) == {"Veg curry": 2, "Custard tart": 1}
    assert await cart_rows() == 1  # converted, not copied
    # Survives logout/login: it is the account's cart now.
    await logout(shop)
    assert (await cart(shop))["items"] == []
    await login(shop)
    assert quantities(await cart(shop)) == {"Veg curry": 2, "Custard tart": 1}


async def test_register_then_login_keeps_the_guest_cart(shop) -> None:
    """The checkout flow for a brand-new customer: register, then log in."""
    await add(shop, "pizza", 3)
    await shop.accounts.register("newcomer@example.com")  # no session yet
    assert quantities(await cart(shop)) == {"Pizza margherita": 3}  # still the guest's
    await login(shop, "newcomer@example.com")
    body = await cart(shop)
    assert body["owner"] == "user"
    assert quantities(body) == {"Pizza margherita": 3}


async def test_same_cook_carts_merge_at_login(shop) -> None:
    await login(shop)
    await add(shop, "curry", 2)
    await add(shop, "pot", 90)
    await logout(shop)
    await add(shop, "curry", 3)  # as a guest, same cook
    await add(shop, "pot", 20)
    await add(shop, "tart")
    await login(shop)
    assert quantities(await cart(shop)) == {
        "Veg curry": 5,
        "Family biryani pot": 100,  # 90 + 20, capped at 100
        "Custard tart": 1,
    }
    assert await cart_rows() == 1


async def test_guest_cart_from_another_cook_replaces_the_saved_cart(shop) -> None:
    await login(shop)
    await add(shop, "curry", 2)  # saved: Chef Ana
    await logout(shop)
    await add(shop, "pizza")  # just chosen as a guest: Chef Bruno
    await login(shop)
    body = await cart(shop)
    assert quantities(body) == {"Pizza margherita": 1}
    assert body["cook"]["name"] == "Chef Bruno"
    assert await cart_rows() == 1


async def test_empty_guest_cart_leaves_the_saved_cart_alone(shop) -> None:
    await login(shop)
    await add(shop, "curry", 2)
    await logout(shop)
    await add(shop, "pizza")
    await shop.client.delete(f"{ITEMS}/{shop.ids['pizza']}")  # guest cart now empty
    await login(shop)
    assert quantities(await cart(shop)) == {"Veg curry": 2}
    assert await cart_rows() == 1  # the empty guest cart is gone


async def test_own_dishes_are_dropped_when_a_cook_logs_in(shop) -> None:
    await add(shop, "curry")  # browsing logged out...
    await login(shop, "chef-a@example.com")  # ...as the curry's own cook
    assert (await cart(shop))["items"] == []
    assert await cart_rows() == 0


async def test_login_without_or_with_a_stale_guest_cookie(shop) -> None:
    await login(shop)
    await add(shop, "curry")
    await logout(shop)
    await login(shop)  # no guest cookie at all
    assert quantities(await cart(shop)) == {"Veg curry": 1}
    await logout(shop)
    set_cart_cookie(shop, "stale-token")
    await login(shop)  # unknown token: ignored, cleared
    assert COOKIE not in shop.client.cookies
    assert quantities(await cart(shop)) == {"Veg curry": 1}


async def test_logged_in_user_ignores_a_guest_cookie_until_next_login(shop) -> None:
    await add(shop, "pizza")
    guest_cookie = shop.client.cookies[COOKIE]
    await login(shop)  # claims it
    await add(shop, "pizza")
    set_cart_cookie(shop, guest_cookie)  # old cookie replayed
    assert quantities(await cart(shop)) == {"Pizza margherita": 2}


# --- the dish changes after it was added ----------------------------------------------------------


async def test_deactivated_dish_stays_visible_but_out_of_totals(shop) -> None:
    await login(shop)
    await add(shop, "curry", 2)
    await add(shop, "tart")
    await login(shop, "chef-a@example.com")
    await shop.client.patch(f"/api/me/dishes/{shop.ids['curry']}", json={"active": False})
    await login(shop)
    body = await cart(shop)
    curry = next(item for item in body["items"] if item["name"] == "Veg curry")
    assert curry["available"] is False
    assert (body["unavailable_count"], body["item_count"], body["total"]) == (1, 1, 500)
    url = f"{ITEMS}/{shop.ids['curry']}"
    assert_error(await shop.client.patch(url, json={"delta": 1}), 409, "dish_unavailable")
    assert (await shop.client.delete(url)).json()["unavailable_count"] == 0


async def test_current_price_and_deleted_dishes(shop) -> None:
    await login(shop)
    await add(shop, "curry", 2)
    await add(shop, "tart")
    await login(shop, "chef-a@example.com")
    await shop.client.patch(f"/api/me/dishes/{shop.ids['curry']}", json={"price": 900})
    await shop.client.delete(f"/api/me/dishes/{shop.ids['tart']}")
    await login(shop)
    body = await cart(shop)
    assert quantities(body) == {"Veg curry": 2}
    assert body["total"] == 1800


async def test_deleted_account_takes_its_cart(shop) -> None:
    await login(shop)
    await add(shop, "curry")
    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.email == BUYER))
        await session.commit()
        assert (await session.scalars(select(Cart))).all() == []
        assert (await session.scalars(select(CartItem))).all() == []


# --- database guards ---------------------------------------------------------------------------------


def test_database_constraints(environment, tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        conn.execute("PRAGMA foreign_keys=OFF")  # isolate the CHECKs from the FKs
        for quantity in (0, 101):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                conn.execute(
                    "INSERT INTO cart_items (cart_id, dish_id, quantity) VALUES (?, ?, ?)",
                    ("a" * 32, uuid.uuid4().hex, quantity),
                )
        for user_id, token_hash in ((None, None), ("c" * 32, "d" * 64)):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                conn.execute(
                    "INSERT INTO carts (id, user_id, token_hash) VALUES (?, ?, ?)",
                    (uuid.uuid4().hex, user_id, token_hash),
                )
    finally:
        conn.close()


async def test_cart_endpoints_in_openapi(client) -> None:
    paths = (await client.get("/api/v1/openapi.json")).json()["paths"]
    assert {"/api/cart", "/api/cart/items", "/api/cart/items/{dish_id}"} <= set(paths)
    assert not any(path.startswith("/api/me/cart") for path in paths)

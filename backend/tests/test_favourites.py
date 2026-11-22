"""Favourite dishes (``/api/me/favourites``) and adding them to the cart.

Acceptance rules under test:

* customers only: 401 anonymous, 403 for an account without the customer
  role (an admin-only account); a cook is a customer too;
* only available dishes can be saved - unknown or hidden ones are a 404;
* a cook cannot save their own dish (422 ``own_dish``);
* at most 50 dishes (409 ``favourites_limit``), hidden ones included, and
  concurrent saves never overshoot;
* saving and removing are idempotent (201 then 200; 204 always);
* a dish the cook hides stays on the list as ``available: false``, cannot go
  to the cart (409 ``dish_unavailable``) and is available again once
  published; a deleted dish leaves the list;
* lists are private;
* adding a saved dish to the cart follows the cart's rules (lines grow,
  one cook per cart with ``replace_cart``, quantities 1..100).
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.dishes.models import Dish
from app.modules.favourites.models import MAX_FAVOURITES
from tests.conftest import BUYER, CHEF_A, CHEF_B, OTHER_BUYER

FAVOURITES = "/api/me/favourites"


def assert_error(response, status: int, code: str, detail_type: str | None = None):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    if detail_type is not None:
        assert detail_type in {d["type"] for d in error["details"]}, error
    return error


async def save(client, dish_id: str, status: int = 201) -> dict:
    response = await client.put(f"{FAVOURITES}/{dish_id}")
    assert response.status_code == status, response.text
    return response.json()


async def listing(client, **params) -> dict:
    response = await client.get(FAVOURITES, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def set_active(market, cook: str, dish_id: str, active: bool) -> None:
    """The dish's cook hides (``False``) or publishes (``True``) it."""
    await market.login(cook)
    response = await market.client.patch(
        f"/api/me/dishes/{dish_id}", json={"active": active}
    )
    assert response.status_code == 200, response.text


async def add_dishes(market, cook: str, count: int) -> list[str]:
    """``count`` more public dishes from ``cook``; returns their ids."""
    await market.login(cook)
    ids = []
    for n in range(count):
        created = await market.client.post(
            "/api/me/dishes",
            json={"name": f"Extra dish {n}", "price": 300 + n, "portions": 2},
        )
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])
    return ids


# --- access ------------------------------------------------------------------------------


async def test_favourites_require_login(client) -> None:
    dish = str(uuid.uuid4())
    for response in (
        await client.get(FAVOURITES),
        await client.get(f"{FAVOURITES}/{dish}"),
        await client.put(f"{FAVOURITES}/{dish}"),
        await client.delete(f"{FAVOURITES}/{dish}"),
        await client.post(f"{FAVOURITES}/{dish}/cart"),
    ):
        assert_error(response, 401, "unauthenticated")


async def test_only_customers_keep_favourites(market) -> None:
    """An account without the customer role (the seed's admin-only account)
    is refused with 403; 401 still outranks it for anonymous callers."""
    await market.login(OTHER_BUYER)
    async with get_sessionmaker()() as session:
        await session.execute(
            update(User).where(User.email == OTHER_BUYER).values(roles=[ROLE_ADMIN])
        )
        await session.commit()
    curry = market.ids["curry"]
    for response in (
        await market.client.get(FAVOURITES),
        await market.client.put(f"{FAVOURITES}/{curry}"),
        await market.client.post(f"{FAVOURITES}/{curry}/cart"),
    ):
        error = assert_error(response, 403, "forbidden")
        assert "customer role" in error["message"]


# --- saving ------------------------------------------------------------------------------


async def test_save_is_idempotent_and_listed(market) -> None:
    await market.login(BUYER)
    curry = market.ids["curry"]

    first = await save(market.client, curry, status=201)
    again = await save(market.client, curry, status=200)  # already saved: no change
    assert first == again
    assert first["available"] is True
    assert first["dish"]["id"] == curry
    assert first["dish"]["name"] == "Veg curry"
    assert first["dish"]["price"] == 800
    assert first["dish"]["cook_name"] == "Chef Ana"
    assert first["added_at"].endswith(("Z", "+00:00"))  # explicit UTC

    page = await listing(market.client)
    assert page["total"] == 1
    assert page["unavailable"] == 0
    assert page["max_favourites"] == MAX_FAVOURITES
    assert [item["dish"]["id"] for item in page["items"]] == [curry]

    one = await market.client.get(f"{FAVOURITES}/{curry}")
    assert one.status_code == 200, one.text
    assert one.json() == first


async def test_list_is_newest_first_and_paged(market) -> None:
    await market.login(BUYER)
    for key in ("curry", "tart", "pizza"):
        await save(market.client, market.ids[key])

    page = await listing(market.client, limit=2)
    assert page["total"] == 3
    assert [i["dish"]["name"] for i in page["items"]] == ["Pizza margherita", "Custard tart"]
    rest = await listing(market.client, limit=2, offset=2)
    assert [i["dish"]["name"] for i in rest["items"]] == ["Veg curry"]


async def test_only_available_dishes_can_be_saved(market) -> None:
    tart = market.ids["tart"]
    await set_active(market, CHEF_A, tart, False)
    await market.login(BUYER)

    assert_error(await market.client.put(f"{FAVOURITES}/{tart}"), 404, "not_found")
    assert_error(
        await market.client.put(f"{FAVOURITES}/{uuid.uuid4()}"), 404, "not_found"
    )
    assert_error(
        await market.client.put(f"{FAVOURITES}/not-a-uuid"), 422, "validation_failed"
    )
    assert (await listing(market.client))["total"] == 0


async def test_cook_cannot_save_own_dish(market) -> None:
    await market.login(CHEF_A)
    assert_error(
        await market.client.put(f"{FAVOURITES}/{market.ids['curry']}"),
        422,
        "validation_failed",
        "own_dish",
    )
    # ...but a cook is a customer too: another kitchen's dish is fine.
    await save(market.client, market.ids["pizza"])
    page = await listing(market.client)
    assert [i["dish"]["name"] for i in page["items"]] == ["Pizza margherita"]


# --- the 50-dish limit --------------------------------------------------------------------


async def test_at_most_fifty_favourites(market) -> None:
    extra = await add_dishes(market, CHEF_B, MAX_FAVOURITES - 1)
    await market.login(BUYER)
    for dish_id in [market.ids["curry"], *extra]:
        await save(market.client, dish_id)
    assert (await listing(market.client))["total"] == MAX_FAVOURITES

    error = assert_error(
        await market.client.put(f"{FAVOURITES}/{market.ids['tart']}"),
        409,
        "favourites_limit",
    )
    assert error["details"] == {"max_favourites": MAX_FAVOURITES}
    # Re-saving a dish that is already on the full list is still fine.
    await save(market.client, market.ids["curry"], status=200)
    assert (await listing(market.client))["total"] == MAX_FAVOURITES

    # Removing one frees a slot.
    removed = await market.client.delete(f"{FAVOURITES}/{market.ids['curry']}")
    assert removed.status_code == 204
    await save(market.client, market.ids["tart"])
    assert (await listing(market.client))["total"] == MAX_FAVOURITES


async def test_hidden_dishes_count_towards_the_limit(market) -> None:
    extra = await add_dishes(market, CHEF_B, MAX_FAVOURITES - 1)
    await market.login(BUYER)
    for dish_id in [market.ids["curry"], *extra]:
        await save(market.client, dish_id)
    await set_active(market, CHEF_A, market.ids["curry"], False)

    await market.login(BUYER)
    page = await listing(market.client)
    assert (page["total"], page["unavailable"]) == (MAX_FAVOURITES, 1)
    assert_error(
        await market.client.put(f"{FAVOURITES}/{market.ids['tart']}"),
        409,
        "favourites_limit",
    )


async def test_concurrent_saves_never_exceed_the_limit(market, monkeypatch) -> None:
    """Two saves racing for the last slot: exactly one wins.

    A barrier right after each request's dish lookup forces the race: both
    requests finish their checks before either writes - the window where a
    "count, then insert" implementation would let both in (51 favourites).
    The limit check and the insert being one statement is what closes it.
    """
    extra = await add_dishes(market, CHEF_B, MAX_FAVOURITES - 2)
    await market.login(BUYER)
    for dish_id in [market.ids["curry"], *extra]:
        await save(market.client, dish_id)
    assert (await listing(market.client))["total"] == MAX_FAVOURITES - 1

    barrier = asyncio.Barrier(2)
    original_get = AsyncSession.get

    async def get_then_wait(self, entity, ident, **kwargs):
        found = await original_get(self, entity, ident, **kwargs)
        if entity is Dish:
            await asyncio.wait_for(barrier.wait(), timeout=10)
        return found

    monkeypatch.setattr(AsyncSession, "get", get_then_wait)
    responses = await asyncio.gather(
        market.client.put(f"{FAVOURITES}/{market.ids['tart']}"),
        market.client.put(f"{FAVOURITES}/{market.ids['pizza']}"),
    )
    monkeypatch.undo()

    assert sorted(r.status_code for r in responses) == [201, 409], [
        r.text for r in responses
    ]
    assert (await listing(market.client))["total"] == MAX_FAVOURITES


# --- hidden, published, deleted ---------------------------------------------------------


async def test_hidden_dish_stays_listed_as_unavailable(market) -> None:
    tart = market.ids["tart"]
    await market.login(BUYER)
    await save(market.client, market.ids["curry"])
    await save(market.client, tart)

    await set_active(market, CHEF_A, tart, False)
    await market.login(BUYER)
    page = await listing(market.client)
    assert page["total"] == 2 and page["unavailable"] == 1
    by_name = {item["dish"]["name"]: item for item in page["items"]}
    assert by_name["Custard tart"]["available"] is False
    assert by_name["Custard tart"]["dish"]["active"] is False
    assert by_name["Veg curry"]["available"] is True
    one = (await market.client.get(f"{FAVOURITES}/{tart}")).json()
    assert one["available"] is False

    # Not orderable while hidden...
    assert_error(
        await market.client.post(f"{FAVOURITES}/{tart}/cart"), 409, "dish_unavailable"
    )
    # ...and available again once the cook publishes it.
    await set_active(market, CHEF_A, tart, True)
    await market.login(BUYER)
    page = await listing(market.client)
    assert page["unavailable"] == 0
    assert all(item["available"] for item in page["items"])


async def test_hidden_dish_can_be_removed(market) -> None:
    tart = market.ids["tart"]
    await market.login(BUYER)
    await save(market.client, tart)
    await set_active(market, CHEF_A, tart, False)
    await market.login(BUYER)
    assert (await market.client.delete(f"{FAVOURITES}/{tart}")).status_code == 204
    assert (await listing(market.client))["total"] == 0


async def test_list_shows_the_current_dish(market) -> None:
    """A favourite is a link, not a snapshot: price edits show through."""
    curry = market.ids["curry"]
    await market.login(BUYER)
    await save(market.client, curry)
    await market.login(CHEF_A)
    edited = await market.client.patch(f"/api/me/dishes/{curry}", json={"price": 950})
    assert edited.status_code == 200, edited.text
    await market.login(BUYER)
    assert (await listing(market.client))["items"][0]["dish"]["price"] == 950


async def test_deleted_dish_leaves_the_list(market) -> None:
    curry = market.ids["curry"]
    await market.login(BUYER)
    await save(market.client, curry)
    await market.login(CHEF_A)
    assert (await market.client.delete(f"/api/me/dishes/{curry}")).status_code == 204
    await market.login(BUYER)
    assert (await listing(market.client))["total"] == 0


# --- removing + privacy ------------------------------------------------------------------


async def test_remove_is_idempotent(market) -> None:
    curry = market.ids["curry"]
    await market.login(BUYER)
    await save(market.client, curry)
    for _ in range(2):
        assert (await market.client.delete(f"{FAVOURITES}/{curry}")).status_code == 204
    # Never saved at all: still a no-op.
    assert (await market.client.delete(f"{FAVOURITES}/{uuid.uuid4()}")).status_code == 204
    assert_error(await market.client.get(f"{FAVOURITES}/{curry}"), 404, "not_found")
    assert (await listing(market.client))["total"] == 0


async def test_favourites_are_private(market) -> None:
    curry = market.ids["curry"]
    await market.login(BUYER)
    await save(market.client, curry)

    await market.login(OTHER_BUYER)
    assert (await listing(market.client))["total"] == 0
    assert_error(await market.client.get(f"{FAVOURITES}/{curry}"), 404, "not_found")
    assert_error(
        await market.client.post(f"{FAVOURITES}/{curry}/cart"), 404, "not_found"
    )
    # Removing "it" on another account touches nothing of the owner's.
    assert (await market.client.delete(f"{FAVOURITES}/{curry}")).status_code == 204

    await market.login(BUYER)
    assert (await listing(market.client))["total"] == 1


# --- from the list to the cart -----------------------------------------------------------


async def test_add_a_favourite_to_the_cart(market) -> None:
    curry = market.ids["curry"]
    await market.login(BUYER)
    await save(market.client, curry)

    response = await market.client.post(f"{FAVOURITES}/{curry}/cart")  # no body
    assert response.status_code == 200, response.text
    cart = response.json()
    assert cart["owner"] == "user"
    assert cart["cook"]["name"] == "Chef Ana"
    assert [(i["dish_id"], i["quantity"]) for i in cart["items"]] == [(curry, 1)]

    # Adding again grows the line, like POST /api/cart/items.
    response = await market.client.post(f"{FAVOURITES}/{curry}/cart", json={"quantity": 2})
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["quantity"] == 3
    assert response.json()["total"] == 3 * 800
    # The regular cart endpoint sees the same cart.
    assert (await market.client.get("/api/cart")).json()["item_count"] == 3
    # The dish stays a favourite.
    assert (await listing(market.client))["total"] == 1


async def test_only_saved_dishes_go_to_the_cart_from_the_list(market) -> None:
    await market.login(BUYER)
    assert_error(
        await market.client.post(f"{FAVOURITES}/{market.ids['tart']}/cart"),
        404,
        "not_found",
    )
    assert (await market.client.get("/api/cart")).json()["items"] == []


async def test_one_cook_per_cart_from_the_list(market) -> None:
    pizza = market.ids["pizza"]
    await market.login(BUYER)
    await market.add("curry")  # the cart holds Chef Ana's dish
    await save(market.client, pizza)  # Chef Bruno's

    error = assert_error(
        await market.client.post(f"{FAVOURITES}/{pizza}/cart"), 409, "different_cook"
    )
    assert error["details"]["cart_cook_name"] == "Chef Ana"

    response = await market.client.post(
        f"{FAVOURITES}/{pizza}/cart", json={"replace_cart": True}
    )
    assert response.status_code == 200, response.text
    cart = response.json()
    assert cart["cook"]["name"] == "Chef Bruno"
    assert [i["dish_id"] for i in cart["items"]] == [pizza]


async def test_cart_quantity_rules_apply(market) -> None:
    curry = market.ids["curry"]
    await market.login(BUYER)
    await save(market.client, curry)

    assert_error(
        await market.client.post(f"{FAVOURITES}/{curry}/cart", json={"quantity": 0}),
        422,
        "validation_failed",
    )
    full = await market.client.post(f"{FAVOURITES}/{curry}/cart", json={"quantity": 100})
    assert full.status_code == 200, full.text
    assert_error(
        await market.client.post(f"{FAVOURITES}/{curry}/cart"),
        422,
        "validation_failed",
        "quantity_unavailable",
    )

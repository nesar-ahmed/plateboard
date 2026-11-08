"""Dishes: cook-only CRUD with ownership, validation, public visibility.

Acceptance rules under test:

* a cook can create, edit and deactivate **only their own** dishes -
  another cook's dish is invisible (404, not 403-with-details);
* price must be a positive integer in minor units (422 otherwise, and the
  database CHECK refuses even for direct SQL);
* allergens come from the fixed ``Allergen`` enum - unknown values 422;
* deactivated dishes never appear on the public menu (``/api/dishes`` and
  its detail route),
  while the owner's dashboard (``/api/me/dishes``) still lists them.
"""

from __future__ import annotations

import sqlite3
import uuid as uuidlib

import pytest

from app.modules.dishes.models import ALLERGEN_VALUES

DISH_BODY = {
    "name": "Hyderabadi chicken biryani",
    "description": "Slow-cooked dum biryani with saffron.",
    "price": 8900,
    "portions": 12,
    "ingredients": ["basmati rice", "chicken", "yogurt"],
    "allergens": ["milk"],
    "dietary_tags": ["Halal"],
}


async def create_dish(accounts, **overrides) -> dict:
    """POST /api/me/dishes and fail loudly (with the body) if not 201."""
    response = await accounts.client.post(
        "/api/me/dishes", json={**DISH_BODY, **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- the happy CRUD path -------------------------------------------------------


async def test_cook_can_create_dish(accounts) -> None:
    await accounts.cook()
    me = await accounts.client.get("/api/me")
    dish = await create_dish(accounts)
    assert dish["name"] == DISH_BODY["name"]
    assert dish["description"] == DISH_BODY["description"]
    assert dish["price"] == DISH_BODY["price"]
    assert dish["portions"] == DISH_BODY["portions"]
    assert dish["ingredients"] == DISH_BODY["ingredients"]
    assert dish["allergens"] == ["milk"]
    assert dish["dietary_tags"] == ["halal"]  # normalized like specialty tags
    assert dish["active"] is True
    assert dish["cook_id"] == me.json()["id"]


async def test_dashboard_lists_my_dishes(accounts) -> None:
    await accounts.cook()
    first = await create_dish(accounts, name="First dish")
    second = await create_dish(accounts, name="Second dish")
    listed = await accounts.client.get("/api/me/dishes")
    assert listed.status_code == 200
    # Newest first: second was created after first.
    assert [d["id"] for d in listed.json()] == [second["id"], first["id"]]


async def test_get_patch_and_delete_one_dish(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts)
    dish_id = dish["id"]

    fetched = await accounts.client.get(f"/api/me/dishes/{dish_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == DISH_BODY["name"]

    patched = await accounts.client.patch(
        f"/api/me/dishes/{dish_id}", json={"price": 9900, "portions": 20}
    )
    assert patched.status_code == 200
    assert patched.json()["price"] == 9900
    assert patched.json()["portions"] == 20

    # PATCH is partial: price survived, description untouched...
    cleared = await accounts.client.patch(
        f"/api/me/dishes/{dish_id}", json={"description": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["description"] is None
    assert cleared.json()["price"] == 9900

    deleted = await accounts.client.delete(f"/api/me/dishes/{dish_id}")
    assert deleted.status_code == 204
    assert (await accounts.client.get(f"/api/me/dishes/{dish_id}")).status_code == 404
    assert (await accounts.client.get("/api/me/dishes")).json() == []


async def test_patch_requires_at_least_one_field(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts)
    response = await accounts.client.patch(f"/api/me/dishes/{dish['id']}", json={})
    assert response.status_code == 422


# --- cook role gates (401 anonymous, 403 customer) ------------------------------


async def test_anonymous_gets_401_on_dish_endpoints(client) -> None:
    for method, path in (
        ("post", "/api/me/dishes"),
        ("get", "/api/me/dishes"),
        ("delete", "/api/me/dishes/some-id"),
    ):
        response = await getattr(client, method)(path)
        assert response.status_code == 401, path


async def test_customer_without_cook_role_gets_403(accounts) -> None:
    await accounts.customer()
    listed = await accounts.client.get("/api/me/dishes")
    assert listed.status_code == 403
    assert listed.json()["error"]["code"] == "forbidden"
    created = await accounts.client.post("/api/me/dishes", json=DISH_BODY)
    assert created.status_code == 403
    patched = await accounts.client.patch(
        "/api/me/dishes/11111111-1111-1111-1111-111111111111", json={"price": 100}
    )
    assert patched.status_code == 403


# --- ownership: another cook must not reach my dish ------------------------------


async def test_other_cook_gets_404_on_my_dish(accounts) -> None:
    """Unknown id and foreign cook give the identical answer: 404, so a
    probing cook never learns that the row exists."""
    await accounts.cook("chef-a@example.com")
    dish = await create_dish(accounts)

    await accounts.cook("chef-b@example.com")  # cookie jar now holds cook B
    for method in ("get", "patch", "delete"):
        kwargs = {} if method != "patch" else {"json": {"price": 1}}
        response = await getattr(accounts.client, method)(
            f"/api/me/dishes/{dish['id']}", **kwargs
        )
        assert response.status_code == 404, method
        assert response.json()["error"]["code"] == "not_found", method

    # B's dashboard never sees A's dish either.
    listed = await accounts.client.get("/api/me/dishes")
    assert listed.json() == []

    # ...and B's attempts changed nothing for A.
    await accounts.login("chef-a@example.com")
    still = await accounts.client.get(f"/api/me/dishes/{dish['id']}")
    assert still.status_code == 200
    assert still.json()["price"] == DISH_BODY["price"]


# --- validation: price, portions, name, tags, allergens -------------------------


async def test_price_must_be_positive_on_create(accounts) -> None:
    await accounts.cook()
    for bad_price in (0, -500):
        response = await accounts.client.post(
            "/api/me/dishes", json={**DISH_BODY, "price": bad_price}
        )
        assert response.status_code == 422, bad_price
        body = response.json()["error"]
        assert body["code"] == "validation_failed"
        assert any(d["field"] == "price" for d in body["details"])


async def test_price_must_be_positive_on_patch(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts)
    response = await accounts.client.patch(
        f"/api/me/dishes/{dish['id']}", json={"price": 0}
    )
    assert response.status_code == 422
    assert (
        await accounts.client.get(f"/api/me/dishes/{dish['id']}")
    ).json()["price"] == DISH_BODY["price"]  # untouched


async def test_missing_price_is_rejected(accounts) -> None:
    await accounts.cook()
    body = {key: value for key, value in DISH_BODY.items() if key != "price"}
    response = await accounts.client.post("/api/me/dishes", json=body)
    assert response.status_code == 422
    assert any(d["field"] == "price" for d in response.json()["error"]["details"])


async def test_portions_must_be_at_least_one(accounts) -> None:
    await accounts.cook()
    for bad in (0, -1):
        response = await accounts.client.post(
            "/api/me/dishes", json={**DISH_BODY, "portions": bad}
        )
        assert response.status_code == 422, bad


async def test_blank_or_oversized_name_rejected(accounts) -> None:
    await accounts.cook()
    assert (
        await accounts.client.post("/api/me/dishes", json={**DISH_BODY, "name": "  "})
    ).status_code == 422
    assert (
        await accounts.client.post("/api/me/dishes", json={**DISH_BODY, "name": "n" * 121})
    ).status_code == 422


async def test_unknown_allergen_is_rejected(accounts) -> None:
    await accounts.cook()
    response = await accounts.client.post(
        "/api/me/dishes", json={**DISH_BODY, "allergens": ["dragonfruit"]}
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert any(d["field"] == "allergens.0" for d in details)


async def test_unknown_allergen_on_patch_is_rejected(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts)
    response = await accounts.client.patch(
        f"/api/me/dishes/{dish['id']}", json={"allergens": ["gluten", "nanites"]}
    )
    assert response.status_code == 422


async def test_every_declared_allergen_is_accepted(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts, allergens=list(ALLERGEN_VALUES))
    assert dish["allergens"] == list(ALLERGEN_VALUES)


async def test_duplicate_allergens_are_rejected(accounts) -> None:
    await accounts.cook()
    response = await accounts.client.post(
        "/api/me/dishes", json={**DISH_BODY, "allergens": ["milk", "milk"]}
    )
    assert response.status_code == 422


async def test_ingredients_and_tags_are_normalized_tags(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(
        accounts,
        ingredients=[" Chicken ", "YOGURT", "saffron  "],
        dietary_tags=["HALAL", "gluten free"],
    )
    assert dish["ingredients"] == ["chicken", "yogurt", "saffron"]
    assert dish["dietary_tags"] == ["halal", "gluten free"]


async def test_duplicate_or_blank_tags_rejected(accounts) -> None:
    await accounts.cook()
    dupe = await accounts.client.post(
        "/api/me/dishes", json={**DISH_BODY, "dietary_tags": ["Vegan", "VEGAN"]}
    )
    assert dupe.status_code == 422
    blank = await accounts.client.post(
        "/api/me/dishes", json={**DISH_BODY, "ingredients": ["chicken", "  "]}
    )
    assert blank.status_code == 422


def test_database_check_constraint_refuses_non_positive_price(
    environment, tmp_path
) -> None:
    """Beyond the API: raw SQL cannot insert a free dish either.

    ``environment`` migrated a real SQLite file; CHECK constraints are part
    of the table definition, so they hold even on a direct connection.
    """
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        user_id = uuidlib.uuid4().hex
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, "db-check@example.com", "not-a-real-hash"),
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            conn.execute(
                "INSERT INTO dishes (id, cook_id, name, price, portions) "
                "VALUES (?, ?, ?, ?, ?)",
                (uuidlib.uuid4().hex, user_id, "Free lunch", 0, 4),
            )
    finally:
        conn.close()


# --- public visibility ----------------------------------------------------------


async def public_ids(client) -> set[str]:
    """All ids on the (unauthenticated) public menu, following pages."""
    ids: set[str] = set()
    offset = 0
    while True:
        response = await client.get(f"/api/dishes?limit=100&offset={offset}")
        assert response.status_code == 200
        page = response.json()
        ids.update(dish["id"] for dish in page["items"])
        offset += page["limit"]
        if offset >= page["total"]:
            return ids


async def test_public_menu_needs_no_login(client) -> None:
    response = await client.get("/api/dishes")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_public_menu_lists_active_dishes_from_every_cook(accounts) -> None:
    await accounts.cook("chef-a@example.com")
    dish_a = await create_dish(accounts)
    await accounts.cook("chef-b@example.com")
    dish_b = await create_dish(accounts, name="Kerala sadya")

    public = await accounts.client.get("/api/dishes")
    assert public.status_code == 200
    body = public.json()
    assert {d["id"] for d in body["items"]} == {dish_a["id"], dish_b["id"]}
    assert body["total"] == 2
    # Cook display name rides along for links (accounts.cook sets none, so
    # the join returns NULL rather than dropping the dish).
    assert all(d["cook_name"] is None for d in body["items"])


async def test_deactivated_dish_disappears_from_public_menu(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts)

    deactivated = await accounts.client.patch(
        f"/api/me/dishes/{dish['id']}", json={"active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    assert await public_ids(accounts.client) == set()  # invisible to the world

    # The owner still sees it on the dashboard - that is how it gets back.
    mine = (await accounts.client.get("/api/me/dishes")).json()
    assert [d["id"] for d in mine] == [dish["id"]]

    reactivated = await accounts.client.patch(
        f"/api/me/dishes/{dish['id']}", json={"active": True}
    )
    assert reactivated.status_code == 200
    assert await public_ids(accounts.client) == {dish["id"]}


# --- public search & pagination ---------------------------------------------------


async def test_public_search_is_case_insensitive_substring(accounts) -> None:
    await accounts.cook()
    biryani = await create_dish(accounts, name="Hyderabadi Biryani Supreme")
    # Own description: search also reads descriptions (tests/test_dish_search.py),
    # and DISH_BODY's mentions biryani.
    await create_dish(
        accounts, name="Kerala Payasam", description="Rice pudding with cardamom."
    )

    response = await accounts.client.get("/api/dishes", params={"q": "bIrYaNi"})
    assert response.status_code == 200
    assert [d["id"] for d in response.json()["items"]] == [biryani["id"]]

    # LIKE wildcards typed by a user are literal characters, not patterns.
    percent = await create_dish(accounts, name="Fifty % Friday special")
    wildcard = await accounts.client.get("/api/dishes", params={"q": "% Fri"})
    assert [d["id"] for d in wildcard.json()["items"]] == [percent["id"]]
    percent_only = await accounts.client.get("/api/dishes", params={"q": "%"})
    assert [d["id"] for d in percent_only.json()["items"]] == [percent["id"]]

    # A blank search behaves as if absent; no match yields an empty page.
    blank = await accounts.client.get("/api/dishes", params={"q": "   "})
    assert blank.json()["total"] == 3
    miss = await accounts.client.get("/api/dishes", params={"q": "zzz"})
    assert miss.json()["items"] == []


async def test_public_pagination(accounts) -> None:
    await accounts.cook()
    created = [await create_dish(accounts, name=f"Dish {i}") for i in range(5)]

    page_one = (await accounts.client.get("/api/dishes", params={"limit": 2})).json()
    page_two = (
        await accounts.client.get("/api/dishes", params={"limit": 2, "offset": 2})
    ).json()
    page_three = (
        await accounts.client.get("/api/dishes", params={"limit": 2, "offset": 4})
    ).json()

    assert page_one["total"] == page_two["total"] == 5
    assert len(page_one["items"]) == len(page_two["items"]) == 2
    assert len(page_three["items"]) == 1
    # newest first, and the pages partition the menu exactly
    assert (
        [d["id"] for d in page_one["items"]]
        + [d["id"] for d in page_two["items"]]
        + [d["id"] for d in page_three["items"]]
        == [dish["id"] for dish in reversed(created)]
    )


async def test_public_pagination_bounds_validated(client) -> None:
    assert (await client.get("/api/dishes", params={"limit": 0})).status_code == 422
    assert (await client.get("/api/dishes", params={"limit": 101})).status_code == 422
    assert (await client.get("/api/dishes", params={"offset": -1})).status_code == 422


async def test_public_filter_by_cook(accounts) -> None:
    await accounts.cook("chef-a@example.com")
    me_a = (await accounts.client.get("/api/me")).json()
    dish_a = await create_dish(accounts)
    await accounts.cook("chef-b@example.com")
    await create_dish(accounts, name="Prawn masala")

    only_a = await accounts.client.get("/api/dishes", params={"cook_id": me_a["id"]})
    assert [d["id"] for d in only_a.json()["items"]] == [dish_a["id"]]


# --- public dish detail -----------------------------------------------------------


async def test_public_dish_detail(accounts) -> None:
    await accounts.cook("chef-a@example.com")
    await accounts.client.patch("/api/me/profile", json={"display_name": "Ayesha"})
    dish = await create_dish(accounts)

    response = await accounts.client.get(f"/api/dishes/{dish['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == DISH_BODY["name"]
    assert body["ingredients"] == DISH_BODY["ingredients"]
    assert body["allergens"] == ["milk"]
    assert body["cook_name"] == "Ayesha"
    assert body["active"] is True


async def test_public_dish_detail_hides_deactivated(accounts) -> None:
    await accounts.cook()
    dish = await create_dish(accounts)
    assert (
        await accounts.client.get(f"/api/dishes/{dish['id']}")
    ).status_code == 200

    await accounts.client.patch(f"/api/me/dishes/{dish['id']}", json={"active": False})
    gone = await accounts.client.get(f"/api/dishes/{dish['id']}")
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "not_found"

    unknown = await accounts.client.get(
        "/api/dishes/22222222-2222-2222-2222-222222222222"
    )
    assert unknown.status_code == 404

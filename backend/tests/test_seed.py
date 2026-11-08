"""scripts/seed.py: idempotency and the acceptance flow it exists for.

The suite's temporary database (``environment`` fixture) is what gets seeded
- the script uses the same session factory the app does, and tests exercise
it in-process via ``seed()`` rather than as a subprocess.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.modules.zones.grid import grid_distance
from scripts.seed import COOKS, CUSTOMERS, ZONES, seed

TOTAL_DISHES = sum(len(cook.dishes) for cook in COOKS)
INACTIVE_DISHES = sum(1 for cook in COOKS for dish in cook.dishes if not dish.active)

NEW_DISH = {
    "name": "Test verifier's paya",
    "description": "Created straight after seeding, must show up publicly.",
    "price": 640,
    "portions": 4,
    "ingredients": ["lamb trotters", "ginger", "green chilli"],
    "allergens": [],
    "dietary_tags": ["halal"],
}


async def test_seeded_credentials_can_login_and_post_a_dish(client) -> None:
    """The acceptance flow: seed, log in with a printed credential, create a
    dish in the dashboard, see it on the public menu."""
    result = await seed()
    assert result.users_created == len(COOKS) + len(CUSTOMERS) == 15
    assert result.dishes_created == TOTAL_DISHES == 40

    cook = next(account for account in result.accounts if account.kind == "cook")
    login = await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    assert login.status_code == 200, login.text
    assert "cook" in login.json()["roles"]

    created = await client.post("/api/me/dishes", json=NEW_DISH)
    assert created.status_code == 201, created.text

    page = (await client.get("/api/dishes?limit=100")).json()
    # 40 seeded minus the deliberately deactivated ones, plus this new dish.
    assert page["total"] == TOTAL_DISHES - INACTIVE_DISHES + 1
    public = next(dish for dish in page["items"] if dish["id"] == created.json()["id"])
    assert public["name"] == NEW_DISH["name"]
    assert public["cook_name"] == cook.display_name

    # The seeded menu also powers search: q=biryani finds Nadia's dish.
    found = await client.get("/api/dishes", params={"q": "biryani"})
    assert any("biryani" in d["name"].lower() for d in found.json()["items"])


async def test_seed_is_safe_to_rerun(client) -> None:
    first = await seed()
    second = await seed()

    assert second.users_created == 0
    assert second.dishes_created == 0
    assert second.users_existing == len(first.accounts)
    assert second.dishes_existing == TOTAL_DISHES

    # Re-run resets passwords to freshly generated ones - and those are the
    # ones the operator sees printed, so they must work.
    cook = next(account for account in second.accounts if account.kind == "cook")
    login = await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    assert login.status_code == 200

    page = (await client.get("/api/dishes?limit=100")).json()
    assert page["total"] == TOTAL_DISHES - INACTIVE_DISHES  # nothing duplicated


async def test_rerun_keeps_dashboard_edits(client) -> None:
    """Existing dishes are never overwritten: a deactivation survives seeding."""
    first = await seed()
    cook = next(account for account in first.accounts if account.kind == "cook")
    await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    mine = (await client.get("/api/me/dishes")).json()
    target = mine[0]["id"]
    assert (
        await client.patch(f"/api/me/dishes/{target}", json={"active": False})
    ).status_code == 200

    # A later run regenerates the credential, logs back in, and the dish is
    # still deactivated - the seed left it alone.
    second = await seed()
    same = next(account for account in second.accounts if account.email == cook.email)
    await client.post(
        "/api/auth/login", json={"email": same.email, "password": same.password}
    )
    again = (await client.get("/api/me/dishes")).json()
    deactivated = next(dish for dish in again if dish["id"] == target)
    assert deactivated["active"] is False


# --- zones ------------------------------------------------------------------------


async def test_seed_creates_the_zone_grid_and_places_every_cook(client) -> None:
    result = await seed()
    assert result.zones_created == len(ZONES) == 9

    zones = (await client.get("/api/zones")).json()
    assert [(z["slug"], z["x"], z["y"]) for z in zones] == [
        (slug, x, y) for slug, _name, x, y in ZONES
    ]

    cooks = (await client.get("/api/cooks?limit=100")).json()["items"]
    assert len(cooks) == len(COOKS)
    placed = {cook["display_name"]: cook["zone"]["slug"] for cook in cooks}
    assert placed == {spec.name: spec.zone for spec in COOKS}


async def test_seeded_menu_answers_zone_and_distance_queries(client) -> None:
    await seed()
    zone_of = {spec.name: spec.zone for spec in COOKS}
    cells = {slug: SimpleNamespace(x=x, y=y) for slug, _name, x, y in ZONES}

    same_zone = (await client.get("/api/dishes?zone=market-square&limit=100")).json()
    assert same_zone["total"] > 0
    assert {d["cook_name"] for d in same_zone["items"]} == {
        name for name, slug in zone_of.items() if slug == "market-square"
    }

    near = (
        await client.get("/api/dishes?zone=north-gate&max_distance=1&limit=100")
    ).json()
    assert near["total"] > 0
    for dish in near["items"]:
        kitchen = cells[zone_of[dish["cook_name"]]]
        assert dish["distance"] == grid_distance(cells["north-gate"], kitchen) <= 1


async def test_rerun_keeps_zones_and_a_cooks_own_zone_choice(client) -> None:
    first = await seed()
    cook = next(account for account in first.accounts if account.kind == "cook")
    await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    moved = await client.patch("/api/cooks/me", json={"zone": "harbour"})
    assert moved.status_code == 200

    second = await seed()
    assert second.zones_created == 0
    assert second.zones_existing == len(ZONES)
    same = next(account for account in second.accounts if account.email == cook.email)
    await client.post(
        "/api/auth/login", json={"email": same.email, "password": same.password}
    )
    assert (await client.get("/api/cooks/me")).json()["zone"]["slug"] == "harbour"

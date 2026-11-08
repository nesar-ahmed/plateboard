"""Public menu filters: zone, distance, price range, dietary tag, allergens.

``GET /api/dishes`` acceptance rules under test:

* ``zone`` alone -> dishes from cooks in that zone; with ``max_distance`` ->
  cooks within that many Manhattan grid steps; items then carry ``distance``.
  Cooks without a zone never match a zone filter (but list without one).
* ``min_price`` / ``max_price`` are inclusive minor-unit bounds.
* ``dietary_tag`` repeats and must *all* be present (exact tag, any case).
* ``exclude_allergen`` repeats and drops dishes declaring *any* of them.
* Everything ANDs together, ``total`` counts all matches (pagination stays
  right), deactivated dishes stay hidden, bad filters are 422 field errors.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from app.core.db import get_sessionmaker
from app.modules.auth.models import ROLE_COOK, ROLE_CUSTOMER, CookProfile, User
from app.modules.dishes.models import Dish

# --- the menu every test queries ----------------------------------------------------------
#
# Grid (tests/conftest.py ZONE_GRID)     Manhattan distance from market-square (1,1)
#
#   north-gate  old-town   hillside           2   1   2
#   riverside   MARKET-SQ  university         1   0   1
#   harbour     station    garden-district    2   1   2
#
# Cook "ayesha" @ market-square (1,1)     Cook "bruno" @ north-gate (0,0)
# Cook "chen"   @ university    (2,1)     Cook "elif"  @ garden-district (2,2)
# Cook "dara"   - no zone (kitchen not placed yet)


@dataclasses.dataclass(frozen=True)
class D:
    cook: str
    name: str
    price: int
    dietary_tags: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()
    active: bool = True


COOK_ZONES: dict[str, str | None] = {
    "ayesha": "market-square",
    "bruno": "north-gate",
    "chen": "university",
    "dara": None,
    "elif": "garden-district",
}

MENU: tuple[D, ...] = (
    D("ayesha", "Veg curry", 800, ("vegan", "gluten free")),
    D("ayesha", "Paneer tikka", 1200, ("vegetarian",), ("milk",)),
    D("ayesha", "Retired vegan stew", 700, ("vegan",), active=False),
    D("bruno", "Nut cake", 500, ("vegetarian", "sweet"), ("nuts", "eggs", "gluten")),
    D("bruno", "Halal mixed grill", 1500, ("halal",)),
    D("chen", "Sesame salad", 650, ("vegan",), ("sesame",)),
    D("dara", "Celery soup", 450, ("vegan",), ("celery",)),
    D("elif", "Dumplings", 900, (), ("gluten",)),
)
ACTIVE = {dish.name for dish in MENU if dish.active}


@pytest.fixture
async def menu(zones) -> dict[str, uuid.UUID]:
    """Cooks (placed per COOK_ZONES) and MENU, written straight to the DB.

    Values are stored exactly as the API would store them (tags already
    trimmed/lowercased). Returns cook name -> user id.
    """
    cook_ids: dict[str, uuid.UUID] = {}
    async with get_sessionmaker()() as session:
        for cook, zone_slug in COOK_ZONES.items():
            user = User(
                email=f"{cook}@example.com",
                password_hash="not-used-here",
                display_name=cook.title(),
                roles=[ROLE_CUSTOMER, ROLE_COOK],
            )
            session.add(user)
            await session.flush()
            zone = zones[zone_slug] if zone_slug else None
            session.add(
                CookProfile(
                    user_id=user.id,
                    headline=f"{cook.title()} cooks",
                    zone_id=zone.id if zone else None,
                )
            )
            cook_ids[cook] = user.id
        for dish in MENU:
            session.add(
                Dish(
                    cook_id=cook_ids[dish.cook],
                    name=dish.name,
                    price=dish.price,
                    portions=4,
                    dietary_tags=list(dish.dietary_tags),
                    allergens=list(dish.allergens),
                    active=dish.active,
                )
            )
        await session.commit()
    return cook_ids


async def fetch(client, **params) -> dict:
    """GET /api/dishes (page size 100) and insist on a 200."""
    response = await client.get("/api/dishes", params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


async def names(client, **params) -> set[str]:
    body = await fetch(client, **params)
    found = {dish["name"] for dish in body["items"]}
    assert body["total"] == len(found)  # total always counts every match
    return found


def assert_field_error(response, field: str) -> None:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert field in {detail["field"] for detail in error["details"]}, error


# --- baseline --------------------------------------------------------------------------


async def test_no_filters_lists_every_active_dish_with_its_zone(client, menu) -> None:
    body = await fetch(client)
    assert {dish["name"] for dish in body["items"]} == ACTIVE
    by_name = {dish["name"]: dish for dish in body["items"]}
    assert by_name["Veg curry"]["zone"] == {
        "slug": "market-square",
        "name": "Market Square",
        "x": 1,
        "y": 1,
    }
    assert by_name["Celery soup"]["zone"] is None  # cook without a zone
    # No origin zone -> no distance to report.
    assert all(dish["distance"] is None for dish in body["items"])


# --- zone + distance ----------------------------------------------------------------------


async def test_zone_alone_means_the_same_zone(client, menu) -> None:
    body = await fetch(client, zone="market-square")
    assert {dish["name"] for dish in body["items"]} == {"Veg curry", "Paneer tikka"}
    assert {dish["distance"] for dish in body["items"]} == {0}


async def test_max_distance_widens_the_radius(client, menu) -> None:
    within_1 = await fetch(client, zone="market-square", max_distance=1)
    assert {d["name"]: d["distance"] for d in within_1["items"]} == {
        "Veg curry": 0,
        "Paneer tikka": 0,
        "Sesame salad": 1,  # university is one step east
    }
    within_2 = await names(client, zone="market-square", max_distance=2)
    # north-gate and garden-district are diagonal = 2 steps; the zoneless cook
    # is never "near" anything.
    assert within_2 == ACTIVE - {"Celery soup"}


async def test_distance_is_manhattan_not_euclidean(client, menu) -> None:
    """From the north-gate corner: university (2,1) is 3 steps, garden-district
    (2,2) is 4 - Euclidean (~2.83) would wrongly let Dumplings in."""
    body = await fetch(client, zone="north-gate", max_distance=3)
    assert {d["name"]: d["distance"] for d in body["items"]} == {
        "Nut cake": 0,
        "Halal mixed grill": 0,
        "Veg curry": 2,
        "Paneer tikka": 2,
        "Sesame salad": 3,
    }
    assert "Dumplings" in await names(client, zone="north-gate", max_distance=4)


async def test_zone_with_no_cooks_is_an_empty_page_not_an_error(client, menu) -> None:
    body = await fetch(client, zone="harbour")
    assert body["items"] == []
    assert body["total"] == 0


async def test_zone_slug_is_case_and_space_insensitive(client, menu) -> None:
    assert await names(client, zone="  Market-Square ") == {"Veg curry", "Paneer tikka"}


async def test_unknown_zone_is_a_422(client, menu) -> None:
    response = await client.get("/api/dishes", params={"zone": "atlantis"})
    assert_field_error(response, "zone")
    assert response.json()["error"]["details"][0]["type"] == "unknown_zone"


async def test_max_distance_requires_a_zone(client, menu) -> None:
    response = await client.get("/api/dishes", params={"max_distance": 2})
    assert_field_error(response, "max_distance")


@pytest.mark.parametrize("bad", [-1, 1999, "far"])
async def test_max_distance_must_be_a_sane_integer(client, menu, bad) -> None:
    response = await client.get(
        "/api/dishes", params={"zone": "market-square", "max_distance": bad}
    )
    assert_field_error(response, "max_distance")


# --- price range -----------------------------------------------------------------------------


async def test_price_range_is_inclusive(client, menu) -> None:
    # 650 and 900 are exact dish prices: both bounds must include them.
    assert await names(client, min_price=650, max_price=900) == {
        "Sesame salad",
        "Veg curry",
        "Dumplings",
    }


async def test_open_ended_price_bounds(client, menu) -> None:
    assert await names(client, min_price=1200) == {"Paneer tikka", "Halal mixed grill"}
    assert await names(client, max_price=500) == {"Nut cake", "Celery soup"}
    assert await names(client, min_price=800, max_price=800) == {"Veg curry"}


async def test_min_price_above_max_price_is_a_422(client, menu) -> None:
    response = await client.get(
        "/api/dishes", params={"min_price": 1000, "max_price": 500}
    )
    assert_field_error(response, "max_price")


@pytest.mark.parametrize("field", ["min_price", "max_price"])
async def test_negative_prices_are_rejected(client, menu, field) -> None:
    assert_field_error(await client.get("/api/dishes", params={field: -1}), field)


# --- dietary tags ----------------------------------------------------------------------------


async def test_single_dietary_tag(client, menu) -> None:
    # "Retired vegan stew" is vegan but deactivated: filters never resurrect it.
    assert await names(client, dietary_tag="vegan") == {
        "Veg curry",
        "Sesame salad",
        "Celery soup",
    }


async def test_repeated_dietary_tags_must_all_match(client, menu) -> None:
    both = await client.get(
        "/api/dishes", params=[("dietary_tag", "vegan"), ("dietary_tag", "gluten free")]
    )
    assert {dish["name"] for dish in both.json()["items"]} == {"Veg curry"}


async def test_dietary_tag_is_normalized_like_stored_tags(client, menu) -> None:
    assert await names(client, dietary_tag="  VEGETARIAN ") == {"Paneer tikka", "Nut cake"}
    # Blank tags are ignored (like a blank q), not "match nothing".
    assert await names(client, dietary_tag="  ") == ACTIVE


async def test_dietary_tag_matches_whole_tags_only(client, menu) -> None:
    """Exact element match: no substrings, no LIKE wildcards."""
    assert await names(client, dietary_tag="veg") == set()
    assert await names(client, dietary_tag="%") == set()
    assert await names(client, dietary_tag="gluten") == set()  # vs "gluten free"


async def test_overlong_dietary_tag_is_a_422(client, menu) -> None:
    response = await client.get("/api/dishes", params={"dietary_tag": "x" * 31})
    assert_field_error(response, "dietary_tag")


# --- allergen exclusion ----------------------------------------------------------------------


async def test_exclude_one_allergen(client, menu) -> None:
    assert await names(client, exclude_allergen="milk") == ACTIVE - {"Paneer tikka"}


async def test_exclude_several_allergens_drops_any_match(client, menu) -> None:
    found = await client.get(
        "/api/dishes",
        params=[("exclude_allergen", "gluten"), ("exclude_allergen", "sesame")],
    )
    assert {dish["name"] for dish in found.json()["items"]} == {
        "Veg curry",  # no allergens declared
        "Paneer tikka",  # milk only
        "Halal mixed grill",  # none
        "Celery soup",  # celery only
    }  # Nut cake + Dumplings (gluten) and Sesame salad are gone


async def test_excluding_every_allergen_leaves_allergen_free_dishes(client, menu) -> None:
    from app.modules.dishes.models import ALLERGEN_VALUES

    params = [("exclude_allergen", allergen) for allergen in ALLERGEN_VALUES]
    found = await client.get("/api/dishes", params=params)
    assert {dish["name"] for dish in found.json()["items"]} == {
        "Veg curry",
        "Halal mixed grill",
    }


async def test_unknown_allergen_is_a_422(client, menu) -> None:
    response = await client.get(
        "/api/dishes", params=[("exclude_allergen", "milk"), ("exclude_allergen", "kryptonite")]
    )
    assert_field_error(response, "exclude_allergen.1")


# --- combinations, pagination, compatibility ----------------------------------------------


async def test_all_filters_and_together(client, menu) -> None:
    """Near the market, vegan, no sesame, at most 10.00: only the curry.
    (Sesame salad fails the allergen rule; Celery soup has no zone.)"""
    found = await names(
        client,
        zone="market-square",
        max_distance=2,
        dietary_tag="vegan",
        exclude_allergen="sesame",
        max_price=1000,
    )
    assert found == {"Veg curry"}


async def test_filters_combine_with_search_and_cook(client, menu) -> None:
    assert await names(client, q="SALAD", dietary_tag="vegan") == {"Sesame salad"}
    assert await names(client, cook_id=str(menu["bruno"]), max_price=600) == {"Nut cake"}


async def test_pagination_total_counts_filtered_matches(client, menu) -> None:
    params = {"zone": "market-square", "max_distance": 2, "limit": 2}
    first = (await client.get("/api/dishes", params={**params, "offset": 0})).json()
    assert first["total"] == len(ACTIVE) - 1  # everything except the zoneless soup
    seen: list[str] = []
    for offset in range(0, first["total"], 2):
        page = (await client.get("/api/dishes", params={**params, "offset": offset})).json()
        assert page["total"] == first["total"]
        assert len(page["items"]) <= 2
        seen += [dish["name"] for dish in page["items"]]
    assert sorted(seen) == sorted(ACTIVE - {"Celery soup"})  # no dupes, no gaps


async def test_dish_detail_carries_the_zone(client, menu) -> None:
    listed = await fetch(client, zone="university")
    dish_id = listed["items"][0]["id"]
    detail = await client.get(f"/api/dishes/{dish_id}")
    assert detail.status_code == 200
    assert detail.json()["zone"]["slug"] == "university"
    assert detail.json()["distance"] is None  # no origin on the detail route


async def test_filters_are_documented_in_openapi(client) -> None:
    spec = (await client.get("/api/v1/openapi.json")).json()
    params = {p["name"] for p in spec["paths"]["/api/dishes"]["get"]["parameters"]}
    assert {
        "q",
        "cook_id",
        "zone",
        "max_distance",
        "min_price",
        "max_price",
        "dietary_tag",
        "exclude_allergen",
        "limit",
        "offset",
    } <= params

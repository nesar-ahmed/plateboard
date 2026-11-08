"""Zones: grid geometry, the distance function, the zone list, cook placement.

Acceptance rules under test:

* zones are cells on an integer grid (one zone per cell, coordinates >= 0);
* distance between zones is the Manhattan grid distance, and the SQL version
  the menu filters with agrees with the Python one for every pair;
* ``GET /api/zones`` is public and lists zones in grid order;
* cooks are placed in a zone by slug (422 for unknown slugs), can move, and
  clear it with an explicit ``null``; public cook pages show the zone.
"""

from __future__ import annotations

import itertools
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.db import get_sessionmaker
from app.modules.zones import service as zone_service
from app.modules.zones.grid import MAX_GRID_DISTANCE, grid_distance, grid_distance_sql
from app.modules.zones.models import Zone
from app.modules.zones.schemas import ZoneCreate
from app.modules.zones.service import ZoneConflictError
from tests.conftest import COOK_BODY, ZONE_GRID


@dataclass(frozen=True)
class P:
    """A bare grid position (anything with ``x``/``y`` works)."""

    x: int
    y: int


# --- the distance function ------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (P(0, 0), P(0, 0), 0),  # same cell
        (P(0, 0), P(1, 0), 1),  # one step east
        (P(0, 0), P(0, 1), 1),  # one step south
        (P(0, 0), P(1, 1), 2),  # diagonal = two grid steps (not sqrt 2)
        (P(0, 0), P(2, 2), 4),  # Euclidean would say ~2.83
        (P(3, 1), P(0, 5), 7),  # |3-0| + |1-5|
        (P(999, 0), P(0, 999), MAX_GRID_DISTANCE),  # corner to corner
    ],
)
def test_grid_distance_is_manhattan(a: P, b: P, expected: int) -> None:
    assert grid_distance(a, b) == expected


def test_grid_distance_is_a_metric() -> None:
    """Symmetric, zero only on the same cell, triangle inequality - checked
    exhaustively on a 4 x 4 grid."""
    cells = [P(x, y) for x in range(4) for y in range(4)]
    for a, b in itertools.product(cells, repeat=2):
        assert grid_distance(a, b) == grid_distance(b, a)
        assert (grid_distance(a, b) == 0) == (a == b)
        assert isinstance(grid_distance(a, b), int)
    for a, b, c in itertools.product(cells, repeat=3):
        assert grid_distance(a, c) <= grid_distance(a, b) + grid_distance(b, c)


def test_works_on_zone_rows() -> None:
    assert grid_distance(Zone(x=0, y=0), Zone(x=2, y=1)) == 3


async def test_sql_distance_matches_python_for_every_pair(zones) -> None:
    """The menu filters in SQL; it must measure exactly what Python does."""
    async with get_sessionmaker()() as session:
        for origin in zones.values():
            rows = await session.execute(
                select(Zone.slug, grid_distance_sql(Zone.x, Zone.y, origin))
            )
            for slug, sql_distance in rows:
                assert sql_distance == grid_distance(origin, zones[slug]), (
                    origin.slug,
                    slug,
                )


# --- zone rows: validation and database constraints ------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"slug": "Old Town", "name": "x", "x": 0, "y": 0},  # not a slug
        {"slug": "old--town", "name": "x", "x": 0, "y": 0},
        {"slug": "ok", "name": "  ", "x": 0, "y": 0},  # blank name
        {"slug": "ok", "name": "x", "x": -1, "y": 0},  # off the grid
        {"slug": "ok", "name": "x", "x": 0, "y": 1000},
    ],
)
def test_zone_create_validation(bad: dict) -> None:
    with pytest.raises(ValidationError):
        ZoneCreate(**bad)


async def test_one_zone_per_slug_and_per_cell(zones) -> None:
    async with get_sessionmaker()() as session:
        with pytest.raises(ZoneConflictError):  # slug taken
            await zone_service.create_zone(
                session, ZoneCreate(slug="old-town", name="Again", x=7, y=7)
            )
        with pytest.raises(ZoneConflictError):  # cell (1, 1) taken
            await zone_service.create_zone(
                session, ZoneCreate(slug="elsewhere", name="Elsewhere", x=1, y=1)
            )


def test_database_refuses_negative_coordinates(environment, tmp_path: Path) -> None:
    """The CHECKs hold even for raw SQL that skips the schemas."""
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            conn.execute(
                "INSERT INTO zones (id, slug, name, x, y) VALUES (?, ?, ?, ?, ?)",
                ("b" * 32, "nowhere", "Nowhere", -1, 0),
            )
    finally:
        conn.close()


# --- GET /api/zones ----------------------------------------------------------------------


async def test_zone_list_is_public_and_empty_without_zones(client) -> None:
    response = await client.get("/api/zones")
    assert response.status_code == 200
    assert response.json() == []


async def test_zone_list_in_grid_order(client, zones) -> None:
    response = await client.get("/api/zones")
    assert response.status_code == 200
    body = response.json()
    # Row by row (y), then column (x) - exactly the order ZONE_GRID is drawn in.
    assert [zone["slug"] for zone in body] == [slug for slug, *_ in ZONE_GRID]
    assert body[4] == {"slug": "market-square", "name": "Market Square", "x": 1, "y": 1}
    assert all(set(zone) == {"slug", "name", "x", "y"} for zone in body)


# --- placing cooks in zones ----------------------------------------------------------------


async def test_become_cook_with_a_zone(accounts, zones) -> None:
    await accounts.customer()
    response = await accounts.become_cook({**COOK_BODY, "zone": "market-square"})
    assert response.status_code == 201, response.text
    assert response.json()["zone"] == {
        "slug": "market-square",
        "name": "Market Square",
        "x": 1,
        "y": 1,
    }
    mine = await accounts.client.get("/api/cooks/me")
    assert mine.json()["zone"]["slug"] == "market-square"


async def test_zone_is_optional_and_slug_case_insensitive(accounts, zones) -> None:
    await accounts.cook("no-zone@example.com")
    assert (await accounts.client.get("/api/cooks/me")).json()["zone"] is None

    await accounts.customer("mixed-case@example.com")
    response = await accounts.become_cook({**COOK_BODY, "zone": "  Old-Town "})
    assert response.status_code == 201
    assert response.json()["zone"]["slug"] == "old-town"


async def test_unknown_zone_is_a_422_naming_the_field(accounts, zones) -> None:
    await accounts.customer()
    response = await accounts.become_cook({**COOK_BODY, "zone": "atlantis"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["field"] == "zone"
    assert error["details"][0]["type"] == "unknown_zone"
    # ...and nothing was created: still not a cook.
    assert "cook" not in (await accounts.client.get("/api/me")).json()["roles"]


async def test_cook_moves_and_clears_zone(accounts, zones) -> None:
    await accounts.cook()

    moved = await accounts.client.patch("/api/cooks/me", json={"zone": "harbour"})
    assert moved.status_code == 200
    assert moved.json()["zone"]["slug"] == "harbour"
    assert moved.json()["headline"] == COOK_BODY["headline"]  # untouched

    kept = await accounts.client.patch("/api/cooks/me", json={"headline": "New line"})
    assert kept.json()["zone"]["slug"] == "harbour"  # omitted = keep

    cleared = await accounts.client.patch("/api/cooks/me", json={"zone": None})
    assert cleared.status_code == 200
    assert cleared.json()["zone"] is None
    assert (await accounts.client.get("/api/cooks/me")).json()["zone"] is None


async def test_patch_zone_validation(accounts, zones) -> None:
    await accounts.cook()
    unknown = await accounts.client.patch("/api/cooks/me", json={"zone": "atlantis"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["details"][0]["field"] == "zone"
    blank = await accounts.client.patch("/api/cooks/me", json={"zone": "  "})
    assert blank.status_code == 422
    # A null headline alone is still "nothing to change".
    nothing = await accounts.client.patch("/api/cooks/me", json={"headline": None})
    assert nothing.status_code == 422


async def test_public_cook_pages_show_the_zone(accounts, zones) -> None:
    await accounts.cook()
    await accounts.client.patch("/api/cooks/me", json={"zone": "station"})
    me = (await accounts.client.get("/api/me")).json()

    profile = await accounts.client.get(f"/api/cooks/{me['id']}")
    assert profile.json()["zone"]["slug"] == "station"
    directory = (await accounts.client.get("/api/cooks")).json()
    assert directory["items"][0]["zone"]["slug"] == "station"


async def test_deleting_a_zone_unplaces_its_cooks(accounts, zones) -> None:
    """ON DELETE SET NULL: retiring a zone keeps the cook, drops the placement."""
    await accounts.cook()
    await accounts.client.patch("/api/cooks/me", json={"zone": "hillside"})
    async with get_sessionmaker()() as session:
        await session.execute(delete(Zone).where(Zone.slug == "hillside"))
        await session.commit()
    mine = await accounts.client.get("/api/cooks/me")
    assert mine.status_code == 200
    assert mine.json()["zone"] is None

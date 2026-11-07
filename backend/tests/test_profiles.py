"""PATCH /api/me/profile: partial edits, length validation, defaults.

Acceptance rule under test: profile edits validate length (and are
login-gated). Limits: display_name 60, bio 500, area 120 (schemas.py).
"""

from __future__ import annotations


async def test_profile_fields_default_to_none(accounts) -> None:
    await accounts.customer()
    me = await accounts.client.get("/api/me")
    body = me.json()
    assert body["display_name"] is None
    assert body["bio"] is None
    assert body["area"] is None


async def test_patch_profile_requires_login(client) -> None:
    response = await client.patch("/api/me/profile", json={"bio": "hello"})
    assert response.status_code == 401


async def test_patch_profile_updates_and_returns_user(accounts) -> None:
    await accounts.customer()
    response = await accounts.client.patch(
        "/api/me/profile",
        json={
            "display_name": "Rina",
            "bio": "Food first, questions later.",
            "area": "Dhanmondi, Dhaka",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Rina"
    assert body["bio"] == "Food first, questions later."
    assert body["area"] == "Dhanmondi, Dhaka"
    # persisted
    assert (await accounts.client.get("/api/me")).json()["display_name"] == "Rina"


async def test_partial_patch_keeps_other_fields(accounts) -> None:
    await accounts.customer()
    await accounts.client.patch(
        "/api/me/profile", json={"display_name": "Rina", "area": "Mirpur"}
    )
    await accounts.client.patch("/api/me/profile", json={"bio": "only bio changed"})
    body = (await accounts.client.get("/api/me")).json()
    assert body["display_name"] == "Rina"
    assert body["area"] == "Mirpur"
    assert body["bio"] == "only bio changed"


async def test_empty_patch_is_rejected(accounts) -> None:
    await accounts.customer()
    response = await accounts.client.patch("/api/me/profile", json={})
    assert response.status_code == 422


async def test_display_name_length_bounds(accounts) -> None:
    await accounts.customer()
    too_long = await accounts.client.patch(
        "/api/me/profile", json={"display_name": "x" * 61}
    )
    assert too_long.status_code == 422
    blank = await accounts.client.patch("/api/me/profile", json={"display_name": "   "})
    assert blank.status_code == 422
    ok = await accounts.client.patch("/api/me/profile", json={"display_name": "x" * 60})
    assert ok.status_code == 200


async def test_bio_length_bound(accounts) -> None:
    await accounts.customer()
    too_long = await accounts.client.patch("/api/me/profile", json={"bio": "b" * 501})
    assert too_long.status_code == 422
    ok = await accounts.client.patch("/api/me/profile", json={"bio": "b" * 500})
    assert ok.status_code == 200


async def test_area_length_bound(accounts) -> None:
    await accounts.customer()
    too_long = await accounts.client.patch("/api/me/profile", json={"area": "a" * 121})
    assert too_long.status_code == 422
    ok = await accounts.client.patch("/api/me/profile", json={"area": "a" * 120})
    assert ok.status_code == 200

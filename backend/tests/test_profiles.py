"""PATCH /api/me/profile: partial edits, length validation, defaults.

Acceptance rule under test: profile edits validate length (and are
login-gated). Limits: display_name 60, bio 500, area 120 (schemas.py).
PATCH semantics per field: omitted keeps, a string replaces, ``null`` clears.
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


# --- clearing fields with an explicit null ----------------------------------------

FULL_PROFILE = {"display_name": "Rina", "bio": "Food first.", "area": "Mirpur"}


async def test_null_alone_clears_a_field(accounts) -> None:
    """The dashboard sends ``{"bio": null}`` when a field is blanked - that
    single-field clear must be an accepted edit, not an 'empty body' 422."""
    await accounts.customer()
    await accounts.client.patch("/api/me/profile", json=FULL_PROFILE)

    response = await accounts.client.patch("/api/me/profile", json={"bio": None})
    assert response.status_code == 200, response.text
    assert response.json()["bio"] is None

    body = (await accounts.client.get("/api/me")).json()  # persisted
    assert body["bio"] is None
    assert body["display_name"] == "Rina"
    assert body["area"] == "Mirpur"


async def test_null_clears_alongside_other_edits(accounts) -> None:
    """Previously the null was silently dropped when sent with another field."""
    await accounts.customer()
    await accounts.client.patch("/api/me/profile", json=FULL_PROFILE)

    response = await accounts.client.patch(
        "/api/me/profile", json={"display_name": "Rina K.", "area": None}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Rina K."
    assert body["area"] is None
    assert body["bio"] == "Food first."


async def test_every_field_can_be_cleared(accounts) -> None:
    await accounts.customer()
    await accounts.client.patch("/api/me/profile", json=FULL_PROFILE)
    response = await accounts.client.patch(
        "/api/me/profile", json={"display_name": None, "bio": None, "area": None}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["display_name"], body["bio"], body["area"]) == (None, None, None)


async def test_blank_string_is_still_rejected_not_cleared(accounts) -> None:
    """Clearing is spelled ``null``; whitespace stays a validation error."""
    await accounts.customer()
    await accounts.client.patch("/api/me/profile", json=FULL_PROFILE)
    for field in ("display_name", "bio", "area"):
        response = await accounts.client.patch("/api/me/profile", json={field: "  "})
        assert response.status_code == 422, field
    assert (await accounts.client.get("/api/me")).json()["bio"] == "Food first."


# --- timestamps -------------------------------------------------------------------


async def test_user_out_carries_updated_at(accounts) -> None:
    """``UserOut`` mirrors the frontend ``User`` type: both timestamps, UTC."""
    await accounts.customer()
    before = (await accounts.client.get("/api/me")).json()
    assert before["created_at"].endswith("Z") or before["created_at"].endswith("+00:00")
    assert before["updated_at"].endswith("Z") or before["updated_at"].endswith("+00:00")

    after = (
        await accounts.client.patch("/api/me/profile", json={"bio": "changed"})
    ).json()
    assert after["updated_at"] >= before["updated_at"]
    assert after["created_at"] == before["created_at"]

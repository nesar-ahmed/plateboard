"""Role enforcement: the acceptance rule is 403 for non-cooks on cook
endpoints, with 401 always winning over 403 for anonymous requests.
"""

from __future__ import annotations

from tests.conftest import COOK_BODY

# --- the cook endpoints reject non-cooks --------------------------------------


async def test_non_cook_gets_403_on_get_cook_me(accounts) -> None:
    await accounts.customer()
    response = await accounts.client.get("/api/cooks/me")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_non_cook_gets_403_on_patch_cook_me(accounts) -> None:
    await accounts.customer()
    response = await accounts.client.patch(
        "/api/cooks/me", json={"headline": "pretending hard"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_anonymous_gets_401_not_403(accounts) -> None:
    """Login failure must not even leak that cook endpoints exist."""
    response = await accounts.client.get("/api/cooks/me")
    assert response.status_code == 401


async def test_cook_can_reach_cook_endpoints(accounts) -> None:
    assert (await accounts.cook()).status_code == 201
    response = await accounts.client.get("/api/cooks/me")
    assert response.status_code == 200
    assert response.json()["headline"] == COOK_BODY["headline"]


# --- become-a-cook --------------------------------------------------------------


async def test_become_cook_adds_role_but_keeps_customer(accounts) -> None:
    await accounts.customer()
    assert (await accounts.become_cook()).status_code == 201
    me = await accounts.client.get("/api/me")
    assert sorted(me.json()["roles"]) == ["cook", "customer"]


async def test_new_accounts_default_to_customer_only(accounts) -> None:
    await accounts.register()
    login = await accounts.login()
    assert login.status_code == 200
    assert login.json()["roles"] == ["customer"]


async def test_become_cook_twice_conflicts(accounts) -> None:
    await accounts.customer()
    assert (await accounts.become_cook()).status_code == 201
    again = await accounts.become_cook()
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_cook"


async def test_become_cook_requires_login(accounts) -> None:
    response = await accounts.client.post("/api/cooks", json=COOK_BODY)
    assert response.status_code == 401


# --- cook profile content -------------------------------------------------------


async def test_specialties_are_normalized_tags(accounts) -> None:
    await accounts.customer()
    response = await accounts.become_cook(
        {"headline": "Tag tester", "specialties": [" Kebab ", "Paya", "BIRYANI"]}
    )
    assert response.status_code == 201
    assert response.json()["specialties"] == ["kebab", "paya", "biryani"]


async def test_duplicate_tags_rejected_case_insensitively(accounts) -> None:
    await accounts.customer()
    response = await accounts.become_cook(
        {"headline": "Dupes", "specialties": ["Kebab", "KEBAB"]}
    )
    assert response.status_code == 422


async def test_patch_cook_me_updates_fields(accounts) -> None:
    await accounts.cook()
    response = await accounts.client.patch(
        "/api/cooks/me", json={"specialties": ["halim"], "headline": "Halim king"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["headline"] == "Halim king"
    assert body["specialties"] == ["halim"]


async def test_patch_cook_me_requires_a_field(accounts) -> None:
    await accounts.cook()
    assert (await accounts.client.patch("/api/cooks/me", json={})).status_code == 422


# --- public cook directory & profile pages ---------------------------------------


async def test_public_cooks_list_shows_only_profiles(client, accounts) -> None:
    await accounts.customer("fan@example.com")  # no cook profile
    await accounts.cook("chef-a@example.com")
    await accounts.client.patch(
        "/api/me/profile", json={"display_name": "Ayesha", "area": "Mirpur"}
    )
    await accounts.cook("chef-b@example.com")

    response = await client.get("/api/cooks")  # no auth at all
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2  # the plain customer is not listed
    assert len(body["items"]) == 2
    card = next(item for item in body["items"] if item["display_name"] == "Ayesha")
    assert card["headline"] == COOK_BODY["headline"]
    assert card["specialties"] == COOK_BODY["specialties"]
    assert card["area"] == "Mirpur"


async def test_public_cooks_pagination(client, accounts) -> None:
    for i in range(3):
        await accounts.cook(f"chef{i}@example.com")
    page = (await client.get("/api/cooks", params={"limit": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    rest = (await client.get("/api/cooks", params={"limit": 2, "offset": 2})).json()
    assert len(rest["items"]) == 1
    assert {i["user_id"] for i in page["items"]} != {i["user_id"] for i in rest["items"]}
    assert (await client.get("/api/cooks", params={"limit": 0})).status_code == 422


async def test_public_cook_profile_page(client, accounts) -> None:
    await accounts.cook("chef-a@example.com")
    me = (await accounts.client.get("/api/me")).json()
    await accounts.client.patch(
        "/api/me/profile", json={"display_name": "Ayesha", "bio": "Biryani first."}
    )

    response = await client.get(f"/api/cooks/{me['id']}")  # public: no cookies
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == me["id"]
    assert body["display_name"] == "Ayesha"
    assert body["bio"] == "Biryani first."
    assert body["headline"] == COOK_BODY["headline"]

    missing = await client.get("/api/cooks/33333333-3333-3333-3333-333333333333")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_private_me_route_not_shadowed_by_id_route(accounts) -> None:
    """/api/cooks/me must keep resolving to the cook's own profile."""
    await accounts.customer("fan@example.com")
    assert (await accounts.client.get("/api/cooks/me")).status_code == 403

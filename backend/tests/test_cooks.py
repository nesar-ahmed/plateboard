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

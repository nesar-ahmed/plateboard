"""Cook applications: apply -> an admin accepts or rejects -> (re)apply.

Acceptance rules under test:

* applying (``POST /api/cooks``) creates the kitchen as ``pending``; the
  applicant sees it at ``GET /api/cooks/me/application`` (404 before
  applying) but gets nothing a cook has: no role, 403 on every cook
  endpoint, no dishes, no public page, not in the directory;
* admins review a queue (``GET /api/admin/cook-applications``: pending,
  oldest first; ``?status=`` filters) - admin only (401 before 403);
* accepting adds the ``cook`` role (roles grow) and opens the kitchen;
  rejecting needs a reason (trimmed, never blank) the applicant sees; both
  stamp the
  deciding admin and time, and only a pending application can be decided
  (409 ``application_not_pending``; unknown ids 404);
* a rejected applicant may apply again (back to ``pending``, the old
  decision cleared); an open application or an accepted kitchen is a 409;
* verification (the badge) exists only for accepted kitchens; the user list
  and the admin dashboard show where applications stand.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.core.db import get_sessionmaker
from app.modules.auth.models import CookProfile, User
from tests.conftest import COOK_BODY

APPLY = "/api/cooks"
MINE = "/api/cooks/me/application"
QUEUE = "/api/admin/cook-applications"
ADMIN = "admin@example.com"


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    return error


async def apply_as(accounts, email: str, body: dict | None = None) -> str:
    """Register + sign in + apply; returns the applicant's user id."""
    await accounts.customer(email)
    response = await accounts.become_cook(body)
    assert response.status_code == 201, response.text
    return response.json()["user_id"]


async def as_admin(accounts) -> None:
    accounts.client.cookies.clear()
    if (await accounts.login(ADMIN)).status_code != 200:
        await accounts.admin(ADMIN)


async def sign_in(accounts, email: str) -> None:
    accounts.client.cookies.clear()
    assert (await accounts.login(email)).status_code == 200


def accept(user_id: str) -> str:
    return f"{QUEUE}/{user_id}/accept"


def reject(user_id: str) -> str:
    return f"{QUEUE}/{user_id}/reject"


# --- applying --------------------------------------------------------------------------


async def test_an_application_starts_pending_and_grants_nothing(accounts) -> None:
    client = accounts.client
    await accounts.customer()
    assert_error(await client.get(MINE), 404, "no_application")

    applied = await accounts.become_cook({**COOK_BODY, "specialties": ["Soup"]})
    assert applied.status_code == 201, applied.text
    body = applied.json()
    assert body["status"] == "pending"
    assert body["specialties"] == ["soup"]
    assert (body["reviewed_at"], body["rejection_reason"]) == (None, None)
    assert body["submitted_at"] is not None
    assert (await client.get(MINE)).json() == body

    assert (await client.get("/api/me")).json()["roles"] == ["customer"]
    for method, url, payload in (
        ("GET", "/api/cooks/me", None),
        ("PATCH", "/api/cooks/me", {"headline": "Sneaky edit"}),
        ("GET", "/api/cooks/me/availability", None),
        ("GET", "/api/cooks/me/orders", None),
        ("GET", "/api/cooks/me/dashboard", None),
        ("GET", "/api/me/dishes", None),
        ("POST", "/api/me/dishes", {"name": "Soup", "price": 500, "portions": 2}),
    ):
        response = await client.request(method, url, json=payload)
        assert_error(response, 403, "forbidden")

    # Invisible to the public.
    assert (await client.get("/api/cooks")).json()["total"] == 0
    assert_error(await client.get(f"/api/cooks/{body['user_id']}"), 404, "not_found")


async def test_applying_needs_a_login(client) -> None:
    assert_error(await client.post(APPLY, json=COOK_BODY), 401, "unauthenticated")
    assert_error(await client.get(MINE), 401, "unauthenticated")


# --- the back office ------------------------------------------------------------------


async def test_the_queue_is_admin_only(accounts) -> None:
    client = accounts.client
    assert_error(await client.get(QUEUE), 401, "unauthenticated")
    some_id = str(uuid.uuid4())
    assert_error(await client.post(accept(some_id)), 401, "unauthenticated")
    await accounts.customer()
    assert_error(await client.get(QUEUE), 403, "forbidden")
    assert_error(await client.post(accept(some_id)), 403, "forbidden")
    assert_error(await client.post(reject(some_id)), 403, "forbidden")


async def test_the_queue_lists_pending_applications_oldest_first(accounts) -> None:
    first = await apply_as(accounts, "first@example.com")
    second = await apply_as(accounts, "second@example.com")
    await accounts.cook("kitchen@example.com")  # accepted - not in the queue
    await accounts.client.patch("/api/me/profile", json={"display_name": "Kit Chen"})

    await as_admin(accounts)
    queue = (await accounts.client.get(QUEUE)).json()
    assert [item["user_id"] for item in queue["items"]] == [first, second]
    assert queue["total"] == 2
    item = queue["items"][0]
    assert item["email"] == "first@example.com"
    assert (item["headline"], item["status"]) == (COOK_BODY["headline"], "pending")

    accepted = (await accounts.client.get(QUEUE, params={"status": "accepted"})).json()
    assert [item["display_name"] for item in accepted["items"]] == ["Kit Chen"]
    everything = (await accounts.client.get(QUEUE, params={"status": "all"})).json()
    assert everything["total"] == 3
    assert (
        await accounts.client.get(QUEUE, params={"status": "maybe"})
    ).status_code == 422
    paged = (await accounts.client.get(QUEUE, params={"limit": 1, "offset": 1})).json()
    assert [item["user_id"] for item in paged["items"]] == [second]


async def test_accepting_opens_the_kitchen(accounts) -> None:
    client = accounts.client
    applicant = await apply_as(accounts, "chef@example.com")
    await as_admin(accounts)
    admin_id = (await client.get("/api/me")).json()["id"]

    decided = await client.post(accept(applicant))
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert (body["status"], body["reviewed_by"]) == ("accepted", admin_id)
    assert body["reviewed_at"] is not None
    assert (await client.get(QUEUE)).json()["total"] == 0

    await sign_in(accounts, "chef@example.com")
    assert sorted((await client.get("/api/me")).json()["roles"]) == ["cook", "customer"]
    assert (await client.get("/api/cooks/me")).json()["status"] == "accepted"
    dish = await client.post(
        "/api/me/dishes", json={"name": "Soup", "price": 500, "portions": 2}
    )
    assert dish.status_code == 201
    assert (await client.get("/api/cooks")).json()["total"] == 1
    assert (await client.get(f"/api/cooks/{applicant}")).status_code == 200


async def test_rejecting_keeps_the_kitchen_closed_and_says_why(accounts) -> None:
    client = accounts.client
    applicant = await apply_as(accounts, "chef@example.com")
    await as_admin(accounts)
    decided = await client.post(
        reject(applicant), json={"reason": "  Please add a photo of your kitchen  "}
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "rejected"
    assert decided.json()["rejection_reason"] == "Please add a photo of your kitchen"
    assert (await client.get(QUEUE, params={"status": "rejected"})).json()["total"] == 1

    await sign_in(accounts, "chef@example.com")
    mine = (await client.get(MINE)).json()
    assert (mine["status"], mine["rejection_reason"]) == (
        "rejected",
        "Please add a photo of your kitchen",
    )
    assert (await client.get("/api/me")).json()["roles"] == ["customer"]
    assert_error(await client.get("/api/cooks/me"), 403, "forbidden")


async def test_a_reason_is_required_and_capped(accounts) -> None:
    client = accounts.client
    applicant = await apply_as(accounts, "chef@example.com")
    await as_admin(accounts)
    for body in (None, {}, {"reason": None}, {"reason": "   "}, {"reason": "x" * 301}):
        refused = await client.post(reject(applicant), json=body)
        error = assert_error(refused, 422, "validation_failed")
        assert [detail["field"] for detail in error["details"]] in (
            ["reason"],
            ["body"],
        )
    # Nothing was decided by the refused attempts.
    assert (await client.get(QUEUE)).json()["total"] == 1
    decided = await client.post(reject(applicant), json={"reason": "  Tell us more  "})
    assert decided.json()["rejection_reason"] == "Tell us more"


async def test_only_a_pending_application_can_be_decided(accounts) -> None:
    client = accounts.client
    applicant = await apply_as(accounts, "chef@example.com")
    await accounts.customer("never-applied@example.com")
    bystander = (await client.get("/api/me")).json()["id"]
    await as_admin(accounts)
    assert (await client.post(accept(applicant))).status_code == 200

    for url in (accept(applicant), reject(applicant)):
        error = assert_error(
            await client.post(url, json={"reason": "Changed my mind"}),
            409,
            "application_not_pending",
        )
        assert error["details"] == {"status": "accepted"}
    for user_id in (bystander, str(uuid.uuid4())):
        assert_error(await client.post(accept(user_id)), 404, "not_found")


# --- applying again ------------------------------------------------------------------


async def test_a_rejected_applicant_may_apply_again(accounts) -> None:
    client = accounts.client
    applicant = await apply_as(accounts, "chef@example.com")
    await as_admin(accounts)
    await client.post(reject(applicant), json={"reason": "Tell us more"})

    await sign_in(accounts, "chef@example.com")
    again = await accounts.become_cook(
        {"headline": "Soups, now with a story", "specialties": ["soup"]}
    )
    assert again.status_code == 201, again.text
    body = again.json()
    assert (body["status"], body["headline"]) == ("pending", "Soups, now with a story")
    assert (body["reviewed_at"], body["rejection_reason"]) == (None, None)
    assert_error(await accounts.become_cook(), 409, "application_pending")

    await as_admin(accounts)
    assert (await client.post(accept(applicant))).json()["status"] == "accepted"
    await sign_in(accounts, "chef@example.com")
    assert_error(await accounts.become_cook(), 409, "already_cook")


# --- verification, user list, dashboard --------------------------------------------------


async def test_only_accepted_kitchens_can_be_verified(accounts) -> None:
    client = accounts.client
    applicant = await apply_as(accounts, "chef@example.com")
    await as_admin(accounts)
    url = f"/api/admin/cooks/{applicant}/verification"
    assert_error(await client.post(url), 404, "not_found")
    await client.post(accept(applicant))
    assert (await client.post(url)).json()["verified"] is True


async def test_the_user_list_and_dashboard_show_applications(accounts) -> None:
    client = accounts.client
    await apply_as(accounts, "pending@example.com")
    rejected = await apply_as(accounts, "rejected@example.com")
    await accounts.cook("kitchen@example.com")
    await accounts.customer("shopper@example.com")
    await as_admin(accounts)
    await client.post(reject(rejected), json={"reason": "Add your kitchen set-up"})

    users = (await client.get("/api/admin/users", params={"limit": 100})).json()[
        "items"
    ]
    status = {user["email"]: user["cook_application"] for user in users}
    assert status == {
        "pending@example.com": "pending",
        "rejected@example.com": "rejected",
        "kitchen@example.com": "accepted",
        "shopper@example.com": None,
        ADMIN: None,
    }
    cooks = (await client.get("/api/admin/users", params={"role": "cook"})).json()
    assert [user["email"] for user in cooks["items"]] == ["kitchen@example.com"]

    stats = (await client.get("/api/admin/dashboard")).json()["users"]
    assert (stats["cooks"], stats["pending_cook_applications"]) == (1, 1)


async def test_a_decision_outlives_the_admin_account(accounts) -> None:
    """``reviewed_by_id`` is SET NULL: deleting the admin keeps the decision."""
    applicant = await apply_as(accounts, "chef@example.com")
    await as_admin(accounts)
    await accounts.client.post(accept(applicant))
    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.email == ADMIN))
        await session.commit()
        profile = await session.get(CookProfile, uuid.UUID(applicant))
    assert profile is not None
    assert (profile.status, profile.reviewed_by_id) == ("accepted", None)
    assert profile.reviewed_at is not None

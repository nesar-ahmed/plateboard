"""Notifications written by the features - who hears about what, through the
real API (the inbox itself is ``tests/test_notifications.py``).

Acceptance rules under test:

* account: a welcome on registration, a security notice on a password change;
* cook applications: every admin hears about a new (or renewed) application;
  the applicant hears the decision (with the reason); once decided, the
  admins' "new application" notices are marked read for all of them;
* verification: the cook hears when the badge is granted or taken away -
  once (the endpoints are idempotent, the notifications too);
* orders: placed -> customer (confirmation, /account) + cook (request,
  /cook); accepted / rejected (+ reason) / ready (pickup) -> customer;
  cancelled by the customer -> cook; cancelled by the cook after accepting
  -> customer + every admin; received (the customer's confirmation) -> cook;
* answered requests are resolved: the cook's "new request" is read once
  accepted / rejected / withdrawn, the customer's "ready" once confirmed;
* a refused or rolled-back action notifies nobody.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.db import get_sessionmaker
from app.modules.notifications.models import Notification
from tests.conftest import (
    BUYER,
    CHEF_A,
    COOK_BODY,
    COOK_ORDERS,
    DEFAULT_PASSWORD,
    ORDERS,
    OTHER_BUYER,
    receive,
)

NOTIFICATIONS = "/api/me/notifications"
ADMIN, SECOND_ADMIN = "admin@example.com", "admin-2@example.com"


async def items(client, audience: str | None = None) -> list[dict]:
    params = {"limit": 100, **({"audience": audience} if audience else {})}
    response = await client.get(NOTIFICATIONS, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def of_type(client, kind: str, audience: str | None = None) -> list[dict]:
    return [item for item in await items(client, audience) if item["type"] == kind]


async def total_rows() -> int:
    async with get_sessionmaker()() as session:
        return await session.scalar(select(func.count()).select_from(Notification)) or 0


async def cook_moves(market, order: dict, *statuses: str, **body) -> None:
    await market.login(CHEF_A)
    for status in statuses:
        moved = await market.client.patch(
            f"{COOK_ORDERS}/{order['id']}", json={"status": status, **body}
        )
        assert moved.status_code == 200, moved.text


# --- the account --------------------------------------------------------------------------


async def test_registration_and_password_change(accounts, make_client) -> None:
    client = accounts.client
    await accounts.customer()
    [welcome] = await items(client)
    assert (welcome["type"], welcome["audience"]) == ("account.welcome", "account")

    other_device = make_client()
    await other_device.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": DEFAULT_PASSWORD},
    )
    changed = await client.post(
        "/api/me/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "a-brand-new-one"},
    )
    assert changed.status_code == 200, changed.text
    [notice] = await of_type(client, "account.password_changed")
    assert notice["title"] == "Your password was changed"
    assert notice["body"] == (
        "If this wasn't you, change it again now. 1 other session was signed out."
    )
    assert notice["data"] == {"signed_out_sessions": 1}

    # A wrong current password changes nothing - and notifies nobody.
    before = await total_rows()
    refused = await client.post(
        "/api/me/password",
        json={"current_password": "not-it-at-all", "new_password": "whatever-else"},
    )
    assert refused.status_code == 422
    assert await total_rows() == before


async def test_a_duplicate_registration_writes_nothing(accounts) -> None:
    await accounts.register()
    before = await total_rows()
    assert (await accounts.register()).status_code == 409
    assert await total_rows() == before


# --- cook applications ---------------------------------------------------------------------


async def test_the_application_round_trip(accounts, make_client) -> None:
    client = accounts.client
    admins = {}
    for email in (ADMIN, SECOND_ADMIN):
        admins[email] = make_client()
        await accounts.register(email)
        await accounts.grant_role(email, "admin")
        await admins[email].post(
            "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
        )

    await accounts.customer("chef@example.com")
    await client.patch("/api/me/profile", json={"display_name": "Chef Ana"})
    applicant = (await accounts.become_cook()).json()["user_id"]

    for admin in admins.values():
        [note] = await of_type(admin, "cook_application.submitted", "admin")
        assert note["title"] == "New cook application"
        assert note["body"] == (
            f'Chef Ana wants to open a kitchen: "{COOK_BODY["headline"]}". '
            "Review it to accept or reject."
        )
        assert note["subject"] == {"kind": "kitchen", "id": applicant}
        assert note["actor_id"] == applicant and note["read"] is False

    first = admins[ADMIN]
    rejected = await first.post(
        f"/api/admin/cook-applications/{applicant}/reject",
        json={"reason": "Add photos"},
    )
    assert rejected.status_code == 200
    # Decided: every admin's notice is resolved, not just the decider's.
    for admin in admins.values():
        [note] = await of_type(admin, "cook_application.submitted", "admin")
        assert note["read"] is True

    [answer] = await of_type(client, "cook_application.rejected")
    assert answer["audience"] == "account"
    assert answer["body"] == (
        "The platform team reviewed your kitchen and could not approve it. "
        'Reason: "Add photos"'
    )

    # Applying again tells the admins again; accepting answers the applicant.
    assert (await accounts.become_cook()).status_code == 201
    for admin in admins.values():
        notes = await of_type(admin, "cook_application.submitted", "admin")
        assert [note["read"] for note in notes] == [False, True]
    await admins[SECOND_ADMIN].post(f"/api/admin/cook-applications/{applicant}/accept")
    [accepted] = await of_type(client, "cook_application.accepted")
    assert accepted["title"] == "Your kitchen is approved"
    assert (
        await client.get(NOTIFICATIONS, params={"audience": "cook"})
    ).status_code == 200


async def test_a_stale_decision_notifies_nobody(accounts) -> None:
    await accounts.customer("chef@example.com")
    applicant = (await accounts.become_cook()).json()["user_id"]
    await accounts.approve("chef@example.com")
    accounts.client.cookies.clear()
    await accounts.admin(ADMIN)
    before = await total_rows()
    late = await accounts.client.post(
        f"/api/admin/cook-applications/{applicant}/reject",
        json={"reason": "Too late - already accepted"},
    )
    assert late.status_code == 409
    assert await total_rows() == before


# --- verification --------------------------------------------------------------------------


async def test_the_cook_hears_about_the_badge_once(market, accounts) -> None:
    client = market.client
    await market.login(CHEF_A)
    chef = (await client.get("/api/me")).json()["id"]
    client.cookies.clear()
    await accounts.admin(ADMIN)
    url = f"/api/admin/cooks/{chef}/verification"
    for _ in range(2):  # idempotent: the second call changes (and says) nothing
        assert (await client.post(url)).status_code == 200
    for _ in range(2):
        assert (await client.delete(url)).status_code == 200

    await market.login(CHEF_A)
    kitchen = await items(client, "cook")
    assert [item["type"] for item in kitchen] == [
        "kitchen.verification_revoked",
        "kitchen.verified",
    ]
    assert all(item["subject"] == {"kind": "kitchen", "id": chef} for item in kitchen)


# --- orders ------------------------------------------------------------------------------------


async def test_placing_tells_both_sides(market) -> None:
    order = await market.order(("curry", 2))  # BUYER, signed in
    [mine] = await of_type(market.client, "order.placed", "account")
    assert mine["title"] == f"Order #{order['id'][:8].upper()} placed with Chef Ana"
    assert mine["subject"] == {"kind": "order", "id": order["id"]}
    assert mine["data"]["total"] == order["total"] == 1600
    assert mine["data"]["fulfilment"] == "pickup"

    await market.login(CHEF_A)
    [request] = await of_type(market.client, "order.placed", "cook")
    assert request["title"] == "New order request from Bea Buyer"
    assert request["read"] is False
    # The cook's own /account inbox holds no copy of the request.
    assert await of_type(market.client, "order.placed", "account") == []


async def test_the_happy_path_notifies_each_step(market) -> None:
    order = await market.order(("curry", 1))
    await cook_moves(market, order, "accepted")
    [request] = await of_type(market.client, "order.placed", "cook")
    assert request["read"] is True  # answered: nothing left to act on
    await market.login(BUYER)
    [accepted] = await of_type(market.client, "order.accepted", "account")
    assert accepted["subject"] == {"kind": "order", "id": order["id"]}
    assert accepted["body"] == f"Order #{order['id'][:8].upper()} is being prepared."

    await cook_moves(market, order, "ready")
    await market.login(BUYER)
    titles = [item["title"] for item in await items(market.client, "account")]
    assert titles[:2] == [
        "Your order is ready for pickup",
        "Chef Ana accepted your order",
    ]
    [ready] = await of_type(market.client, "order.ready")
    assert ready["read"] is False

    assert (await receive(market.client, order["id"])).status_code == 200
    [ready] = await of_type(market.client, "order.ready")
    assert ready["read"] is True  # confirmed: resolved

    await market.login(CHEF_A)
    [received] = await of_type(market.client, "order.received", "cook")
    assert received["title"] == "Bea Buyer received their order"
    assert received["read"] is False


async def test_rejections_and_cancellations(market, accounts) -> None:
    client = market.client
    await accounts.register(ADMIN)
    await accounts.grant_role(ADMIN, "admin")

    rejected = await market.order(("curry", 1))
    await cook_moves(market, rejected, "cancelled", reason="Sold out")
    withdrawn = await market.order(("tart", 1), buyer=OTHER_BUYER)
    await client.post(f"{ORDERS}/{withdrawn['id']}/cancel")
    dropped = await market.order(("curry", 1))
    await cook_moves(market, dropped, "accepted")
    await cook_moves(market, dropped, "cancelled", reason="Ran out of rice")

    await market.login(BUYER)
    [no] = await of_type(client, "order.rejected")
    assert no["title"] == "Chef Ana couldn't take your order"
    assert no["body"].endswith('Reason: "Sold out"')
    [late] = await of_type(client, "order.cancelled_by_cook")
    assert late["body"].endswith('Reason: "Ran out of rice"')

    await market.login(CHEF_A)
    [gone] = await of_type(client, "order.cancelled_by_customer", "cook")
    assert gone["title"] == "Otto Other cancelled their order"
    requests = await of_type(client, "order.placed", "cook")
    assert len(requests) == 3 and all(item["read"] for item in requests)

    client.cookies.clear()
    await accounts.login(ADMIN)
    [flag] = await of_type(client, "order.cancelled_by_cook", "admin")
    assert flag["title"] == "Chef Ana cancelled an accepted order"
    assert flag["subject"]["id"] == dropped["id"]
    # Rejections and customer cancellations are not admin business.
    assert len(await items(client, "admin")) == 1


async def test_refused_moves_notify_nobody(market) -> None:
    order = await market.order(("curry", 1))
    before = await total_rows()
    assert (await receive(market.client, order["id"])).status_code == 409
    await market.login(CHEF_A)
    skip = await market.client.patch(
        f"{COOK_ORDERS}/{order['id']}", json={"status": "ready"}
    )
    assert skip.status_code == 409
    assert await total_rows() == before


async def test_a_refused_order_notifies_nobody(market) -> None:
    await market.login(BUYER)
    await market.add("curry", 1)
    before = await total_rows()
    assert (await market.place(fulfilment="delivery")).status_code == 422
    empty = await market.order(("tart", 1))  # places (and empties) the cart...
    after_one = await total_rows()
    assert after_one == before + 2  # ...one confirmation + one request
    assert (await market.place()).status_code == 409  # cart_empty
    assert await total_rows() == after_one
    assert empty["status"] == "placed"

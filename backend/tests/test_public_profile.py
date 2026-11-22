"""The public cook profile: the verified badge and the stats strip.

Acceptance rules under test:

* only admins verify or revoke a kitchen (401 before 403; 404 for an id
  without a cook profile); both are idempotent - verifying again keeps the
  first date; the badge shows on the public card and page, the cook sees
  ``verified_at`` on ``/api/cooks/me``, the back office on its user list;
* deleting the verifying admin keeps the kitchen verified (SET NULL);
* the stats strip counts - never money; rates and times stay null until the
  kitchen answered ``PUBLIC_STATS_MIN_ORDERS`` requests (``new_kitchen``),
  then use the dashboard's definitions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.db import get_sessionmaker
from app.modules.auth.models import CookProfile, User
from app.modules.cooks.service import PUBLIC_STATS_MIN_ORDERS
from app.shared.base import utcnow
from tests.conftest import BUYER, CHEF_A, COOK_ORDERS, OTHER_BUYER, set_order_times

ADMIN = "admin@example.com"


def verification(cook_id: str) -> str:
    return f"/api/admin/cooks/{cook_id}/verification"


async def cook_id_of(client, email: str) -> str:
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email))
    assert user is not None
    return str(user.id)


# --- verification ----------------------------------------------------------------------------


async def test_only_admins_verify(market, accounts) -> None:
    client = market.client
    chef = await cook_id_of(client, CHEF_A)
    assert (await client.post(verification(chef))).status_code == 401
    await market.login(CHEF_A)  # a cook cannot verify themselves
    assert (await client.post(verification(chef))).status_code == 403
    assert (await client.delete(verification(chef))).status_code == 403


async def test_verify_and_revoke_show_everywhere(market, accounts) -> None:
    client = market.client
    chef = await cook_id_of(client, CHEF_A)
    client.cookies.clear()
    await accounts.admin(ADMIN)
    admin_id = (await client.get("/api/me")).json()["id"]

    public = (await client.get(f"/api/cooks/{chef}")).json()
    assert (public["verified"], public["verified_at"]) == (False, None)

    first = await client.post(verification(chef))
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["user_id"], body["verified"], body["verified_by"]) == (chef, True, admin_id)
    again = (await client.post(verification(chef))).json()
    assert again["verified_at"] == body["verified_at"]  # idempotent: first date stays

    public = (await client.get(f"/api/cooks/{chef}")).json()
    assert public["verified"] is True and public["verified_at"] == body["verified_at"]
    listed = {c["user_id"]: c for c in (await client.get("/api/cooks")).json()["items"]}
    assert listed[chef]["verified"] is True
    users = {u["email"]: u for u in (await client.get("/api/admin/users")).json()["items"]}
    assert users[CHEF_A]["verified_at"] == body["verified_at"]
    assert users[BUYER]["verified_at"] is None  # not a cook

    await market.login(CHEF_A)
    assert (await client.get("/api/cooks/me")).json()["verified_at"] == body["verified_at"]

    client.cookies.clear()
    await accounts.login(ADMIN)
    revoked = (await client.delete(verification(chef))).json()
    assert (revoked["verified"], revoked["verified_at"], revoked["verified_by"]) == (False, None, None)
    assert (await client.delete(verification(chef))).status_code == 200  # idempotent
    assert (await client.get(f"/api/cooks/{chef}")).json()["verified"] is False


async def test_verifying_a_non_kitchen_is_404(market, accounts) -> None:
    client = market.client
    buyer = await cook_id_of(client, BUYER)
    client.cookies.clear()
    await accounts.admin(ADMIN)
    for target in (buyer, str(uuid.uuid4())):
        response = await client.post(verification(target))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


async def test_deleting_the_admin_keeps_the_badge(market, accounts) -> None:
    client = market.client
    chef = await cook_id_of(client, CHEF_A)
    client.cookies.clear()
    await accounts.admin(ADMIN)
    await client.post(verification(chef))
    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.email == ADMIN))
        await session.commit()
        profile = await session.get(CookProfile, uuid.UUID(chef))
    assert profile is not None
    assert profile.verified_at is not None and profile.verified_by_id is None


# --- stats strip -------------------------------------------------------------------------------


async def test_a_new_kitchen_has_counts_but_no_rates(market) -> None:
    chef = await cook_id_of(market.client, CHEF_A)
    await market.order(("curry", 1))
    stats = (await market.client.get(f"/api/cooks/{chef}")).json()["stats"]
    assert stats == {
        "orders_completed": 0,
        "customers": 1,
        "returning_customers": 0,
        "acceptance_rate": None,
        "average_ready_minutes": None,
        "new_kitchen": True,
    }


async def test_stats_follow_the_dashboard_definitions(market) -> None:
    """Six answered requests: five accepted (three handed over), one rejected."""
    client = market.client
    chef = await cook_id_of(client, CHEF_A)
    placed = [
        await market.order(("curry", 1)),
        await market.order(("tart", 1)),
        await market.order(("curry", 2), buyer=OTHER_BUYER),
        await market.order(("tart", 2), buyer=OTHER_BUYER),
        await market.order(("curry", 1), buyer=OTHER_BUYER),
        await market.order(("tart", 1)),
    ]
    for order in placed[:3]:  # accepted, ready, received by the customer
        await market.complete(order)
    await market.login(CHEF_A)
    for order in placed[3:5]:
        moved = await client.patch(f"{COOK_ORDERS}/{order['id']}", json={"status": "accepted"})
        assert moved.status_code == 200, moved.text
    await client.patch(
        f"{COOK_ORDERS}/{placed[5]['id']}", json={"status": "cancelled", "reason": "Sold out"}
    )
    # Ready after 20, 40 and 60 minutes -> 40 on average.
    start = datetime.combine(utcnow().date(), time())
    for order, minutes in zip(placed[:3], (20, 40, 60), strict=True):
        await set_order_times(order["id"], created_at=start, ready_at=start + timedelta(minutes=minutes))

    stats = (await client.get(f"/api/cooks/{chef}")).json()["stats"]
    assert PUBLIC_STATS_MIN_ORDERS <= 6
    assert stats["orders_completed"] == 3
    assert (stats["customers"], stats["returning_customers"]) == (2, 2)
    assert stats["acceptance_rate"] == pytest.approx(5 / 6, abs=0.001)
    assert stats["average_ready_minutes"] == pytest.approx(40.0, abs=0.1)
    assert stats["new_kitchen"] is False
    assert not any("value" in key or "earn" in key for key in stats)  # never money

    # The public list is the light version: no stats there.
    assert "stats" not in (await client.get("/api/cooks")).json()["items"][0]

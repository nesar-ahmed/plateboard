"""Dashboards (customer / cook / admin) and the admin back-office lists.

Acceptance rules under test:

* each dashboard is gated to its audience: customer = any login, cook =
  cook role, admin = admin role (401 before 403);
* the numbers follow one set of definitions: cancelled orders never count as
  value, ``open`` = placed + accepted + ready, rankings by portions / value;
* time series are zero-filled, oldest first, over ``?days=`` / ``?months=``
  (validated), and bucket orders by the UTC day/month they were placed;
* the cook dashboard adds the kitchen's money (earned = completed orders by
  completion day; open orders split into requests vs in progress), request
  handling (acceptance rate, rejections, timings), top customers, the open
  queue oldest first and the set-up checklist;
* admin lists filter by role / search text / status / party.

The ``history`` fixture builds a small, hand-checkable data set (see its
docstring) on top of ``market`` (tests/conftest.py).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from app.modules.dashboards.service import make_window
from app.shared.base import utcnow
from tests.conftest import (
    BUYER,
    CHEF_A,
    CHEF_B,
    COOK_ORDERS,
    ORDERS,
    OTHER_BUYER,
    receive,
    set_order_times,
)

CUSTOMER_DASH = "/api/me/dashboard"
COOK_DASH = "/api/cooks/me/dashboard"
ADMIN_DASH = "/api/admin/dashboard"
ADMIN = "admin@example.com"


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


@pytest.fixture
async def history(market, accounts) -> SimpleNamespace:
    """Five orders, all placed today:

    ====  ===========  ==========================  =====  =========
    id    customer     lines (Chef Ana unless ...)  total  status
    ====  ===========  ==========================  =====  =========
    a     BUYER        curry x2                     1600  completed
    b     BUYER        pizza x1 (Chef Bruno)         900  cancelled
    c     BUYER        tart x1                       500  placed
    d     OTHER_BUYER  curry x1 + tart x2           1800  accepted
    e     OTHER_BUYER  curry x1                      800  completed
    ====  ===========  ==========================  =====  =========

    Plus an open cart: BUYER (account) has tart x3. Nobody is signed in.
    """
    orders = {
        "a": await market.order(("curry", 2)),
        "b": await market.order(("pizza", 1)),
        "c": await market.order(("tart", 1)),
        "d": await market.order(("curry", 1), ("tart", 2), buyer=OTHER_BUYER),
        "e": await market.order(("curry", 1), buyer=OTHER_BUYER),
    }
    await market.login(BUYER)
    await market.client.post(f"{ORDERS}/{orders['b']['id']}/cancel")
    await market.add("tart", 3)

    for key in ("a", "e"):  # cook: accept + ready; customer: received
        await market.complete(orders[key])
    await market.login(CHEF_A)
    moved = await market.client.patch(
        f"{COOK_ORDERS}/{orders['d']['id']}", json={"status": "accepted"}
    )
    assert moved.status_code == 200, moved.text
    market.client.cookies.clear()
    return SimpleNamespace(
        **vars(market),
        orders={k: v["id"] for k, v in orders.items()},
        accounts=accounts,
    )


# --- access --------------------------------------------------------------------------------


async def test_dashboards_are_gated_to_their_audience(market, accounts) -> None:
    client = market.client
    for url in (CUSTOMER_DASH, COOK_DASH, ADMIN_DASH):
        assert_error(await client.get(url), 401, "unauthenticated")

    await market.login(BUYER)
    assert (await client.get(CUSTOMER_DASH)).status_code == 200
    assert_error(await client.get(COOK_DASH), 403, "forbidden")
    assert_error(await client.get(ADMIN_DASH), 403, "forbidden")

    await market.login(CHEF_A)
    assert (await client.get(CUSTOMER_DASH)).status_code == 200  # cooks buy too
    assert (await client.get(COOK_DASH)).status_code == 200
    assert_error(await client.get(ADMIN_DASH), 403, "forbidden")

    client.cookies.clear()
    await accounts.admin(ADMIN)
    assert (await client.get(ADMIN_DASH)).status_code == 200
    assert_error(await client.get(COOK_DASH), 403, "forbidden")  # admin is not a cook


@pytest.mark.parametrize(
    ("url", "params"),
    [
        (CUSTOMER_DASH, {"months": 0}),
        (CUSTOMER_DASH, {"months": 25}),
        (COOK_DASH, {"days": 0}),
        (COOK_DASH, {"days": 366}),
    ],
)
async def test_window_parameters_are_validated(market, url, params) -> None:
    await market.login(CHEF_A)
    assert_error(await market.client.get(url, params=params), 422, "validation_failed")


# --- windows ---------------------------------------------------------------------------------


def test_month_windows_cross_the_year_boundary() -> None:
    window = make_window("month", 3, today=date(2026, 1, 15))
    assert (window.start, window.end, window.periods) == (
        date(2025, 11, 1),
        date(2026, 1, 15),
        3,
    )


def test_day_windows_end_today() -> None:
    window = make_window("day", 7, today=date(2026, 3, 2))
    assert (window.start, window.end) == (date(2026, 2, 24), date(2026, 3, 2))


# --- customer --------------------------------------------------------------------------------


async def test_a_new_customer_gets_an_empty_but_complete_dashboard(market) -> None:
    await market.login(BUYER)
    body = (await market.client.get(CUSTOMER_DASH)).json()
    assert body["window"]["unit"] == "month" and body["window"]["periods"] == 6
    assert body["orders"] == {
        "orders": 0,
        "by_status": dict.fromkeys(
            ("placed", "accepted", "ready", "completed", "cancelled"), 0
        ),
        "open": 0,
        "booked_value": 0,
        "completed_value": 0,
        "average_order_value": 0,
    }
    assert [p["orders"] for p in body["spending"]] == [0] * 6
    assert (
        body["favourite_cooks"]
        == body["favourite_dishes"]
        == body["recent_orders"]
        == []
    )
    assert body["cart"] == {
        "cook": None,
        "lines": 0,
        "item_count": 0,
        "total": 0,
        "unavailable_count": 0,
    }


async def test_customer_dashboard_numbers(history) -> None:
    await history.login(BUYER)
    body = (await history.client.get(CUSTOMER_DASH)).json()

    assert body["orders"] == {
        "orders": 3,
        "by_status": {
            "placed": 1,
            "accepted": 0,
            "ready": 0,
            "completed": 1,
            "cancelled": 1,
        },
        "open": 1,
        "booked_value": 2100,  # a + c; the cancelled pizza never counts
        "completed_value": 1600,
        "average_order_value": 1050,
    }
    this_month = body["spending"][-1]
    assert this_month["period"] == utcnow().strftime("%Y-%m")
    assert (this_month["orders"], this_month["cancelled"], this_month["value"]) == (
        2,
        1,
        2100,
    )
    assert [(c["name"], c["orders"], c["value"]) for c in body["favourite_cooks"]] == [
        ("Chef Ana", 2, 2100)
    ]
    assert [
        (d["name"], d["quantity"], d["orders"], d["value"])
        for d in body["favourite_dishes"]
    ] == [
        ("Veg curry", 2, 1, 1600),
        ("Custard tart", 1, 1, 500),
    ]
    orders = history.orders
    assert [o["id"] for o in body["recent_orders"]] == [
        orders["c"],
        orders["b"],
        orders["a"],
    ]
    assert body["cart"]["cook"]["name"] == "Chef Ana"
    assert (
        body["cart"]["lines"],
        body["cart"]["item_count"],
        body["cart"]["total"],
    ) == (1, 3, 1500)


async def test_spending_is_bucketed_by_the_month_an_order_was_placed(history) -> None:
    placed = utcnow() - timedelta(days=40)  # always an earlier month
    await set_order_times(history.orders["a"], created_at=placed)
    await history.login(BUYER)

    three = (await history.client.get(CUSTOMER_DASH, params={"months": 3})).json()[
        "spending"
    ]
    assert len(three) == 3
    by_month = {p["period"]: p for p in three}
    assert by_month[placed.strftime("%Y-%m")]["value"] == 1600
    assert by_month[utcnow().strftime("%Y-%m")]["value"] == 500

    one = (await history.client.get(CUSTOMER_DASH, params={"months": 1})).json()[
        "spending"
    ]
    assert [(p["orders"], p["value"]) for p in one] == [(1, 500)]  # a left the window


# --- cook ------------------------------------------------------------------------------------


async def test_cook_dashboard_numbers(history) -> None:
    # Average fulfilment: a took 30 minutes, e took 60. Anchored at the start
    # of today (UTC) so both stay inside the days=1 window at any hour.
    start = datetime.combine(utcnow().date(), time())
    await set_order_times(
        history.orders["a"],
        created_at=start,
        completed_at=start + timedelta(minutes=30),
    )
    await set_order_times(
        history.orders["e"],
        created_at=start,
        completed_at=start + timedelta(minutes=60),
    )
    history.client.cookies.clear()
    await history.add("curry", 1)  # a guest cart holding Chef Ana's curry

    await history.login(CHEF_A)
    body = (await history.client.get(COOK_DASH, params={"days": 1})).json()

    assert body["orders"] == {
        "orders": 4,
        "by_status": {
            "placed": 1,
            "accepted": 1,
            "ready": 0,
            "completed": 2,
            "cancelled": 0,
        },
        "open": 2,
        "booked_value": 4700,
        "completed_value": 2400,
        "average_order_value": 1175,
    }
    assert [(p["orders"], p["value"]) for p in body["revenue"]] == [(4, 4700)]
    assert [
        (d["name"], d["quantity"], d["orders"], d["value"]) for d in body["top_dishes"]
    ] == [
        ("Veg curry", 4, 3, 3200),
        ("Custard tart", 3, 2, 1500),
    ]
    assert body["customers"] == {"unique": 2, "repeat": 2}
    assert body["average_fulfilment_minutes"] == pytest.approx(45.0, abs=0.1)
    # BUYER's tart x3 (account cart) + the guest's curry x1.
    assert body["demand"] == {"carts": 2, "portions": 4, "value": 2300}
    assert body["zone"] is None
    assert {o["id"] for o in body["recent_orders"]} == {
        history.orders[key] for key in ("a", "c", "d", "e")
    }


async def test_cook_menu_breakdown_counts_active_dishes_only(history, zones) -> None:
    await history.login(CHEF_A)
    client = history.client
    await client.patch(
        f"/api/me/dishes/{history.ids['curry']}",
        json={"allergens": ["milk"], "dietary_tags": ["vegan", "spicy"]},
    )
    await client.patch(
        f"/api/me/dishes/{history.ids['tart']}", json={"allergens": ["milk", "eggs"]}
    )
    retired = await client.post(
        "/api/me/dishes",
        json={
            "name": "Old stew",
            "price": 2000,
            "portions": 2,
            "allergens": ["celery"],
            "dietary_tags": ["vegan"],
        },
    )
    await client.patch(f"/api/me/dishes/{retired.json()['id']}", json={"active": False})
    await client.patch("/api/cooks/me", json={"zone": "old-town"})

    body = (await client.get(COOK_DASH)).json()
    menu = body["menu"]
    assert (menu["dishes"], menu["active"], menu["inactive"]) == (3, 2, 1)
    assert menu["price"] == {
        "min": 500,
        "avg": 650,
        "max": 800,
    }  # the 2000 stew is inactive
    assert menu["allergens"] == [
        {"name": "milk", "count": 2},
        {"name": "eggs", "count": 1},
    ]
    assert menu["dietary_tags"] == [
        {"name": "spicy", "count": 1},
        {"name": "vegan", "count": 1},
    ]
    assert body["zone"]["slug"] == "old-town"


async def test_cook_series_is_zero_filled_and_windowed(history) -> None:
    await set_order_times(history.orders["a"], created_at=utcnow() - timedelta(days=3))
    await history.login(CHEF_A)

    week = (await history.client.get(COOK_DASH, params={"days": 7})).json()
    assert len(week["revenue"]) == 7
    periods = [date.fromisoformat(p["period"]) for p in week["revenue"]]
    assert periods == [periods[0] + timedelta(days=i) for i in range(7)]  # contiguous
    assert periods[-1] == utcnow().date()
    assert [p["value"] for p in week["revenue"]] == [0, 0, 0, 1600, 0, 0, 3100]

    today = (await history.client.get(COOK_DASH, params={"days": 1})).json()
    assert [p["value"] for p in today["revenue"]] == [3100]
    assert today["orders"]["booked_value"] == 4700  # summaries stay all-time


async def test_cook_dashboard_money_queue_and_customers(history) -> None:
    await history.login(CHEF_A)
    body = (await history.client.get(COOK_DASH)).json()
    orders = history.orders

    # a (1600) and e (800) were completed just now; c is a request, d cooking.
    earned = {"orders": 2, "value": 2400}
    assert body["earnings"] == {
        "today": earned,
        "last_7_days": earned,
        "this_month": earned,
        "lifetime": earned,
        "awaiting_acceptance": {"orders": 1, "value": 500},
        "in_progress": {"orders": 1, "value": 1800},
    }
    # Open orders, first come first served: c was placed before d.
    assert [(o["id"], o["status"]) for o in body["queue"]] == [
        (orders["c"], "placed"),
        (orders["d"], "accepted"),
    ]
    # Both customers have 2 orders; Otto's are worth more (d + e vs a + c).
    assert [
        (c["name"], c["orders"], c["value"]) for c in body["top_customers"]
    ] == [("Otto Other", 2, 2600), ("Bea Buyer", 2, 2100)]
    assert body["top_customers"][0]["last_order_at"].endswith("Z")


async def test_cook_dashboard_earnings_count_by_completion_day(history) -> None:
    """An order placed weeks ago but completed today is today's money; one
    completed 10 days ago is in this month only if the month is that long."""
    today = utcnow().date()
    await set_order_times(
        history.orders["a"],
        created_at=utcnow() - timedelta(days=40),
        completed_at=datetime.combine(today, time()),
    )
    ten_days_ago = datetime.combine(today - timedelta(days=10), time(12))
    await set_order_times(history.orders["e"], completed_at=ten_days_ago)
    await history.login(CHEF_A)
    earnings = (await history.client.get(COOK_DASH)).json()["earnings"]
    assert earnings["today"] == {"orders": 1, "value": 1600}
    assert earnings["last_7_days"] == {"orders": 1, "value": 1600}
    in_month = ten_days_ago >= datetime.combine(today.replace(day=1), time())
    assert earnings["this_month"] == (
        {"orders": 2, "value": 2400} if in_month else {"orders": 1, "value": 1600}
    )
    assert earnings["lifetime"] == {"orders": 2, "value": 2400}


async def test_cook_performance_rejections_and_timings(market) -> None:
    client = market.client
    start = datetime.combine(utcnow().date(), time())
    served = await market.order(("curry", 1))
    rejected = await market.order(("curry", 1))
    dropped = await market.order(("tart", 1))
    changed_mind = await market.order(("tart", 1), buyer=OTHER_BUYER)
    await market.client.post(f"{ORDERS}/{changed_mind['id']}/cancel")

    await market.login(CHEF_A)
    for order_id, steps in {
        served["id"]: [{"status": "accepted"}, {"status": "ready"}],
        rejected["id"]: [{"status": "cancelled", "reason": "Sold out"}],
        dropped["id"]: [{"status": "accepted"}, {"status": "cancelled"}],
    }.items():
        for step in steps:
            moved = await client.patch(f"{COOK_ORDERS}/{order_id}", json=step)
            assert moved.status_code == 200, moved.text
    await market.login(BUYER)  # the customer confirms the served one
    assert (await receive(client, served["id"])).status_code == 200
    await market.login(CHEF_A)
    # Accepting took 10 and 20 minutes; preparing took 40.
    await set_order_times(
        served["id"],
        created_at=start,
        accepted_at=start + timedelta(minutes=10),
        ready_at=start + timedelta(minutes=50),
    )
    await set_order_times(
        dropped["id"], created_at=start, accepted_at=start + timedelta(minutes=20)
    )

    performance = (await client.get(COOK_DASH)).json()["performance"]
    assert performance == {
        "accepted": 2,
        "rejected": 1,
        "acceptance_rate": pytest.approx(0.667),
        "cancelled_after_accepting": 1,
        "cancelled_by_customer": 1,
        "cancellation_rate": 0.75,
        "average_accept_minutes": pytest.approx(15.0, abs=0.1),
        "average_prep_minutes": pytest.approx(40.0, abs=0.1),
    }


async def test_a_new_kitchen_gets_an_empty_dashboard_and_a_checklist(
    market, accounts, zones
) -> None:
    client = market.client
    await accounts.cook("fresh@example.com")
    body = (await client.get(COOK_DASH)).json()
    zero = {"orders": 0, "value": 0}
    assert all(amount == zero for amount in body["earnings"].values())
    assert body["performance"] == {
        "accepted": 0,
        "rejected": 0,
        "acceptance_rate": None,
        "cancelled_after_accepting": 0,
        "cancelled_by_customer": 0,
        "cancellation_rate": None,
        "average_accept_minutes": None,
        "average_prep_minutes": None,
    }
    assert body["queue"] == body["top_customers"] == []

    def steps(checklist: dict) -> dict[str, bool]:
        assert checklist["done"] == sum(s["done"] for s in checklist["steps"])
        assert checklist["total"] == len(checklist["steps"]) == 6
        return {s["key"]: s["done"] for s in checklist["steps"]}

    # COOK_BODY has specialties; nothing else is set up yet.
    assert steps(body["checklist"]) == {
        "display_name": False,
        "bio": False,
        "specialties": True,
        "zone": False,
        "public_dish": False,
        "dish_descriptions": False,
    }

    await client.patch("/api/me/profile", json={"display_name": "Fresh", "bio": "Hi!"})
    await client.patch("/api/cooks/me", json={"zone": "old-town"})
    bare = await client.post(
        "/api/me/dishes", json={"name": "Soup", "price": 500, "portions": 4}
    )
    await client.post(
        "/api/me/dishes",
        json={"name": "Draft", "price": 500, "portions": 4, "active": False},
    )
    halfway = steps((await client.get(COOK_DASH)).json()["checklist"])
    assert halfway["public_dish"] and not halfway["dish_descriptions"]

    await client.patch(
        f"/api/me/dishes/{bare.json()['id']}", json={"description": "Warming."}
    )
    done = (await client.get(COOK_DASH)).json()["checklist"]
    assert done["done"] == done["total"] == 6  # private drafts need no description


# --- admin -----------------------------------------------------------------------------------


async def test_admin_dashboard_numbers(history, zones) -> None:
    await history.login(CHEF_A)
    await history.client.patch("/api/cooks/me", json={"zone": "old-town"})
    history.client.cookies.clear()
    await history.accounts.admin(ADMIN)

    body = (await history.client.get(ADMIN_DASH, params={"days": 7})).json()
    users = body["users"]
    assert (users["total"], users["customers"], users["cooks"], users["admins"]) == (
        5,
        5,
        2,
        1,
    )
    assert users["new_in_window"] == 5 and users["active_sessions"] >= 1
    assert body["signups"][-1] == {"period": utcnow().date().isoformat(), "count": 5}
    assert sum(p["count"] for p in body["signups"]) == 5

    assert body["orders"] == {
        "orders": 5,
        "by_status": {
            "placed": 1,
            "accepted": 1,
            "ready": 0,
            "completed": 2,
            "cancelled": 1,
        },
        "open": 2,
        "booked_value": 4700,
        "completed_value": 2400,
        "average_order_value": 1175,
    }
    today = body["order_series"][-1]
    assert (today["orders"], today["cancelled"], today["value"]) == (4, 1, 4700)
    assert [(c["name"], c["orders"], c["value"]) for c in body["top_cooks"]] == [
        ("Chef Ana", 4, 4700)  # Chef Bruno's only order was cancelled
    ]
    assert [d["name"] for d in body["top_dishes"]] == ["Veg curry", "Custard tart"]

    tiles = {z["slug"]: z for z in body["zones"]}
    assert (
        len(body["zones"]) == 9 and body["zones"][0]["slug"] == "north-gate"
    )  # grid order
    assert {
        k: tiles["old-town"][k] for k in ("cooks", "active_dishes", "orders", "value")
    } == {"cooks": 1, "active_dishes": 2, "orders": 4, "value": 4700}
    assert tiles["harbour"]["cooks"] == tiles["harbour"]["orders"] == 0
    assert (body["menu"]["dishes"], body["menu"]["active"]) == (3, 3)
    assert body["carts"] == {
        "carts": 1,
        "portions": 3,
        "value": 1500,
        "guest_carts": 0,
        "account_carts": 1,
    }


async def test_rankings_follow_renamed_and_deleted_dishes(history, accounts) -> None:
    await history.login(CHEF_A)
    await history.client.patch(
        f"/api/me/dishes/{history.ids['curry']}", json={"name": "Curry v2"}
    )
    await history.client.delete(f"/api/me/dishes/{history.ids['tart']}")
    history.client.cookies.clear()
    await accounts.admin(ADMIN)

    ranking = (await history.client.get(ADMIN_DASH)).json()["top_dishes"]
    assert [(d["name"], d["dish_id"], d["quantity"]) for d in ranking] == [
        ("Curry v2", history.ids["curry"], 4),  # one entry, current name
        ("Custard tart", None, 3),  # deleted: grouped by the ordered name
    ]


# --- admin lists -----------------------------------------------------------------------------


async def test_admin_user_list_filters_and_activity(history) -> None:
    client = history.client
    await history.accounts.admin(ADMIN)
    everyone = (await client.get("/api/admin/users")).json()
    assert everyone["total"] == 5
    assert everyone["items"][0]["email"] == ADMIN  # newest first

    by_email = {u["email"]: u for u in everyone["items"]}
    assert (by_email[BUYER]["orders_placed"], by_email[BUYER]["orders_received"]) == (
        3,
        0,
    )
    assert (by_email[CHEF_A]["orders_placed"], by_email[CHEF_A]["orders_received"]) == (
        0,
        4,
    )
    assert by_email[CHEF_B]["last_login_at"] is not None
    assert "password_hash" not in by_email[BUYER]

    cooks = (await client.get("/api/admin/users", params={"role": "cook"})).json()
    assert {u["email"] for u in cooks["items"]} == {CHEF_A, CHEF_B}
    found = (await client.get("/api/admin/users", params={"q": "BÉA"})).json()
    assert [u["email"] for u in found["items"]] == [
        BUYER
    ]  # accent/case-insensitive name match
    paged = (
        await client.get("/api/admin/users", params={"limit": 2, "offset": 4})
    ).json()
    assert (paged["total"], len(paged["items"])) == (5, 1)
    assert_error(
        await client.get("/api/admin/users", params={"role": "chef"}),
        422,
        "validation_failed",
    )


async def test_admin_order_list_filters(history) -> None:
    client = history.client
    await history.accounts.admin(ADMIN)
    assert (await client.get("/api/admin/orders")).json()["total"] == 5

    cancelled = (
        await client.get("/api/admin/orders", params={"status": "cancelled"})
    ).json()
    assert [o["id"] for o in cancelled["items"]] == [history.orders["b"]]

    await history.login(OTHER_BUYER)
    other_id = (await client.get("/api/me")).json()["id"]
    client.cookies.clear()
    await history.accounts.login(ADMIN)
    theirs = (
        await client.get("/api/admin/orders", params={"customer_id": other_id})
    ).json()
    assert {o["id"] for o in theirs["items"]} == {
        history.orders["d"],
        history.orders["e"],
    }


async def test_admin_lists_are_admin_only(history) -> None:
    client = history.client
    for url in ("/api/admin/users", "/api/admin/orders"):
        assert_error(await client.get(url), 401, "unauthenticated")
    await history.login(CHEF_A)
    for url in ("/api/admin/users", "/api/admin/orders"):
        assert_error(await client.get(url), 403, "forbidden")

"""The cook's earnings (``GET /api/cooks/me/earnings``).

Acceptance rules under test:

* cook only (401 anonymous, 403 for non-cooks); only the cook's own orders;
* an order is *earned* on the UTC day it was **completed** (not placed);
  cancellations count by when they were cancelled, rejections (cancelled by
  the cook before accepting) separately;
* the range defaults to the last 30 days ending today; ``start`` alone means
  "from then until today"; start after end, more than 366 days or an unknown
  ``group`` are 422s naming the field;
* ``previous`` is the same number of days right before ``start``;
* the series is zero-filled per day / ISO week (labelled by its Monday) /
  month; ``dishes`` splits the range's earnings per dish, by value;
* ``lifetime`` and the open pipeline (requests vs in progress) ignore the range.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from app.modules.dashboards.service import earnings_labels
from app.shared.base import utcnow
from tests.conftest import (
    BUYER,
    CHEF_A,
    COOK_ORDERS,
    OTHER_BUYER,
    set_order_times,
)

EARNINGS = "/api/cooks/me/earnings"


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    return error


def noon(day: date) -> datetime:
    return datetime.combine(day, time(12))


async def cook_moves(market, order: dict, *steps: dict, cook: str = CHEF_A) -> None:
    await market.login(cook)
    for step in steps:
        moved = await market.client.patch(f"{COOK_ORDERS}/{order['id']}", json=step)
        assert moved.status_code == 200, moved.text


ACCEPTED = {"status": "accepted"}


@pytest.fixture
async def books(market) -> SimpleNamespace:
    """Chef Ana's orders, relative to today (UTC):

    ==  ===========================  =====  ===================================
    id  lines                        total  what happened
    ==  ===========================  =====  ===================================
    o1  curry x2                      1600  placed 35 days ago, completed today
    o2  tart x1                        500  completed 3 days ago
    o3  curry x1 + tart x1            1300  completed 40 days ago
    o4  curry x1                       800  rejected by the cook 2 days ago
    o5  tart x2                       1000  placed - a request
    o6  curry x3                      2400  accepted - cooking
    ==  ===========================  =====  ===================================

    Plus Chef Bruno's completed pizza (900), which never shows up for Ana.
    """
    today = utcnow().date()
    o1 = await market.order(("curry", 2))
    o2 = await market.order(("tart", 1), buyer=OTHER_BUYER)
    o3 = await market.order(("curry", 1), ("tart", 1))
    o4 = await market.order(("curry", 1), buyer=OTHER_BUYER)
    await market.order(("tart", 2))  # o5 - stays a request
    o6 = await market.order(("curry", 3), buyer=OTHER_BUYER)
    pizza = await market.order(("pizza", 1))
    for order in (o1, o2, o3, pizza):  # accepted, ready, received
        await market.complete(order)
    await cook_moves(market, o4, {"status": "cancelled", "reason": "Sold out"})
    await cook_moves(market, o6, ACCEPTED)

    await set_order_times(
        o1["id"],
        created_at=noon(today - timedelta(days=35)),
        completed_at=datetime.combine(today, time()),
    )
    await set_order_times(o2["id"], completed_at=noon(today - timedelta(days=3)))
    await set_order_times(o3["id"], completed_at=noon(today - timedelta(days=40)))
    await set_order_times(o4["id"], cancelled_at=noon(today - timedelta(days=2)))
    await market.login(CHEF_A)
    return SimpleNamespace(**vars(market), today=today)


# --- access + validation --------------------------------------------------------------------


async def test_earnings_are_for_cooks_only(market) -> None:
    assert_error(await market.client.get(EARNINGS), 401, "unauthenticated")
    await market.login(BUYER)
    assert_error(await market.client.get(EARNINGS), 403, "forbidden")
    await market.login(CHEF_A)
    assert (await market.client.get(EARNINGS)).status_code == 200


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"start": "2026-03-10", "end": "2026-03-01"}, "end"),
        ({"start": "2024-01-01", "end": "2025-01-02"}, "end"),  # 368 days
        ({"start": (date.today() + timedelta(days=5)).isoformat()}, "end"),
        ({"group": "year"}, "group"),
        ({"start": "yesterday"}, "start"),
    ],
)
async def test_bad_ranges_are_422s_naming_the_field(market, params, field) -> None:
    await market.login(CHEF_A)
    error = assert_error(
        await market.client.get(EARNINGS, params=params), 422, "validation_failed"
    )
    assert [d["field"] for d in error["details"]] == [field]


async def test_a_whole_year_is_allowed(market) -> None:
    await market.login(CHEF_A)
    body = (
        await market.client.get(
            EARNINGS,
            params={"start": "2024-01-01", "end": "2024-12-31", "group": "month"},
        )
    ).json()
    assert body["range"]["days"] == 366  # a leap year, the longest range
    assert len(body["series"]) == 12


# --- numbers ---------------------------------------------------------------------------------


async def test_default_range_summary_previous_and_pipeline(books) -> None:
    body = (await books.client.get(EARNINGS)).json()
    assert body["range"] == {
        "start": (books.today - timedelta(days=29)).isoformat(),
        "end": books.today.isoformat(),
        "days": 30,
        "group": "day",
    }
    # o1 counts: it was placed 35 days ago but completed today.
    assert body["summary"] == {
        "earned": 2100,
        "orders": 2,
        "portions": 3,
        "average_order_value": 1050,
        "cancelled_orders": 1,
        "cancelled_value": 800,
        "rejected_orders": 1,
    }
    assert body["previous"] == {  # the 30 days before: o3
        "earned": 1300,
        "orders": 1,
        "portions": 2,
        "average_order_value": 1300,
        "cancelled_orders": 0,
        "cancelled_value": 0,
        "rejected_orders": 0,
    }
    assert body["lifetime"] == {"orders": 3, "value": 3400}
    assert body["awaiting_acceptance"] == {"orders": 1, "value": 1000}
    assert body["in_progress"] == {"orders": 1, "value": 2400}


async def test_daily_series_is_zero_filled_by_completion_day(books) -> None:
    series = (await books.client.get(EARNINGS)).json()["series"]
    assert len(series) == 30
    assert series[-1] == {
        "period": books.today.isoformat(),
        "orders": 1,
        "earned": 1600,
    }
    assert series[-4]["earned"] == 500  # o2, three days ago
    assert sum(point["earned"] for point in series) == 2100
    periods = [date.fromisoformat(point["period"]) for point in series]
    assert periods == [periods[0] + timedelta(days=i) for i in range(30)]


async def test_dishes_split_the_range_by_value(books) -> None:
    dishes = (await books.client.get(EARNINGS)).json()["dishes"]
    assert [(d["name"], d["quantity"], d["orders"], d["value"]) for d in dishes] == [
        ("Veg curry", 2, 1, 1600),
        ("Custard tart", 1, 1, 500),
    ]
    wide = (
        await books.client.get(
            EARNINGS,
            params={"start": (books.today - timedelta(days=60)).isoformat()},
        )
    ).json()["dishes"]
    # o1 + o3 curry (3 portions, 2400) vs o2 + o3 tart (2 portions, 1000)
    assert [(d["name"], d["quantity"], d["orders"], d["value"]) for d in wide] == [
        ("Veg curry", 3, 2, 2400),
        ("Custard tart", 2, 2, 1000),
    ]


async def test_start_alone_runs_until_today(books) -> None:
    start = books.today - timedelta(days=45)
    body = (
        await books.client.get(EARNINGS, params={"start": start.isoformat()})
    ).json()
    assert (body["range"]["start"], body["range"]["end"], body["range"]["days"]) == (
        start.isoformat(),
        books.today.isoformat(),
        46,
    )
    assert body["summary"]["earned"] == 3400  # o1 + o2 + o3


async def test_week_and_month_groups(market) -> None:
    """Fixed past dates: 2025-03-01 is a Saturday, 03-03 and 03-10 Mondays."""
    completed = {
        "2025-03-03": ("curry", 1),  # Monday      -> week of 03-03
        "2025-03-09": ("tart", 1),  # Sunday      -> week of 03-03
        "2025-03-10": ("curry", 2),  # Monday      -> week of 03-10
        "2025-04-01": ("tart", 2),  # Tuesday     -> week of 03-31, April
    }
    for day, line in completed.items():
        order = await market.order(line)
        await market.complete(order)
        await set_order_times(order["id"], completed_at=noon(date.fromisoformat(day)))
    await market.login(CHEF_A)

    params = {"start": "2025-03-01", "end": "2025-04-02"}
    weeks = (
        await market.client.get(EARNINGS, params={**params, "group": "week"})
    ).json()
    by_week = {p["period"]: (p["orders"], p["earned"]) for p in weeks["series"]}
    labels = list(by_week)
    assert (labels[0], labels[-1]) == (
        "2025-02-24",
        "2025-03-31",
    )  # 02-24: 03-01's Monday
    assert by_week["2025-03-03"] == (2, 1300)
    assert by_week["2025-03-10"] == (1, 1600)
    assert by_week["2025-03-17"] == (0, 0)
    assert by_week["2025-03-31"] == (1, 1000)

    months = (
        await market.client.get(EARNINGS, params={**params, "group": "month"})
    ).json()
    assert [(p["period"], p["orders"], p["earned"]) for p in months["series"]] == [
        ("2025-03", 3, 2900),
        ("2025-04", 1, 1000),
    ]


def test_labels_cover_the_range_and_cross_the_year() -> None:
    start, end = date(2025, 12, 30), date(2026, 1, 2)
    assert earnings_labels("day", start, end) == [
        "2025-12-30",
        "2025-12-31",
        "2026-01-01",
        "2026-01-02",
    ]
    assert earnings_labels("week", start, end) == ["2025-12-29"]
    assert earnings_labels("month", start, end) == ["2025-12", "2026-01"]

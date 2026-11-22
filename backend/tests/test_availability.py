"""Kitchen availability: weekly hours, time zones, pause - and what they allow.

Acceptance rules under test:

* the pure computation (pinned clock): ``anytime`` without hours, ``paused``
  beats hours, ``open`` until the window ends, ``closed`` until the next
  window; back-to-back windows merge across midnight; hours are wall-clock
  in the kitchen's zone (also across a daylight-saving change); the next
  24 hours are clipped to ``[now, now + 24h]``;
* ``GET|PUT /api/cooks/me/availability`` - cook only; validation of zones,
  times and overlaps are 422s naming the field;
* every public card carries the availability;
* an order is only placed while the kitchen takes orders (409
  ``kitchen_closed`` with ``opens_at``; nothing changes) - filling the cart
  stays possible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.cooks.availability import compute_availability
from app.shared.base import utcnow
from tests.conftest import BUYER, CHEF_A, ORDERS

AVAILABILITY = "/api/cooks/me/availability"

#: Wednesday 11 November 2026, noon UTC (weekday 2).
WEDNESDAY_NOON = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def window(day: int, opens: str, closes: str) -> dict:
    return {"day": day, "opens": opens, "closes": closes}


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """A UTC instant in the week of WEDNESDAY_NOON (Monday = 9 Nov)."""
    return datetime(2026, 11, 9 + day, hour, minute, tzinfo=UTC)


def compute(hours: list[dict], now: datetime = WEDNESDAY_NOON, tz: str = "UTC", paused: bool = False):
    return compute_availability(hours=hours, timezone=tz, paused=paused, now=now)


# --- the computation ------------------------------------------------------------------------


def test_no_hours_means_orders_any_time() -> None:
    state = compute([])
    assert (state.status, state.accepting_orders) == ("anytime", True)
    assert state.as_of == WEDNESDAY_NOON
    assert [(w.starts_at, w.ends_at) for w in state.next_24h] == [
        (WEDNESDAY_NOON, WEDNESDAY_NOON + timedelta(hours=24))
    ]


def test_pause_beats_the_hours() -> None:
    state = compute([window(2, "00:00", "24:00")], paused=True)
    assert (state.status, state.accepting_orders) == ("paused", False)
    assert state.opens_at is None and state.next_24h == []


def test_open_inside_a_window_until_it_ends() -> None:
    state = compute([window(2, "11:00", "14:00")])
    assert (state.status, state.accepting_orders, state.closes_at) == ("open", True, at(2, 14))
    assert [(w.starts_at, w.ends_at) for w in state.next_24h] == [(WEDNESDAY_NOON, at(2, 14))]


def test_closed_between_windows_opens_at_the_next_one() -> None:
    hours = [window(2, "11:00", "14:00"), window(2, "17:00", "21:00"), window(3, "11:00", "14:00")]
    state = compute(hours, now=at(2, 15))
    assert (state.status, state.accepting_orders, state.opens_at) == ("closed", False, at(2, 17))
    # next 24 h (until Thursday 15:00): tonight and Thursday lunch, clipped
    assert [(w.starts_at, w.ends_at) for w in state.next_24h] == [
        (at(2, 17), at(2, 21)),
        (at(3, 11), at(3, 14)),
    ]


def test_back_to_back_windows_merge_across_midnight() -> None:
    state = compute([window(2, "18:00", "24:00"), window(3, "00:00", "02:00")], now=at(2, 23))
    assert (state.status, state.closes_at) == ("open", at(3, 2))


def test_next_opening_beyond_24_hours() -> None:
    state = compute([window(0, "09:00", "17:00")])  # Mondays only
    assert state.status == "closed"
    assert state.opens_at == at(7, 9)  # next Monday
    assert state.next_24h == []


def test_hours_are_kitchen_wall_time() -> None:
    """Dhaka is UTC+6: 09:00-17:00 there is 03:00-11:00 UTC."""
    state = compute([window(2, "09:00", "17:00"), window(3, "09:00", "17:00")], tz="Asia/Dhaka")
    assert state.status == "closed"
    assert state.opens_at == at(3, 3)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # London on BST (UTC+1): Sunday 09:00 is 08:00 UTC...
        (datetime(2026, 10, 17, 12, tzinfo=UTC), datetime(2026, 10, 18, 8, tzinfo=UTC)),
        # ...and after the clocks go back (25 Oct 2026, GMT) it is 09:00 UTC.
        (datetime(2026, 10, 24, 12, tzinfo=UTC), datetime(2026, 10, 25, 9, tzinfo=UTC)),
    ],
)
def test_wall_time_survives_daylight_saving(now: datetime, expected: datetime) -> None:
    state = compute([window(6, "09:00", "17:00")], now=now, tz="Europe/London")
    assert state.opens_at == expected


def test_naive_now_is_utc() -> None:
    naive = WEDNESDAY_NOON.replace(tzinfo=None)
    assert compute([window(2, "11:00", "14:00")], now=naive).status == "open"


# --- the cook's settings ----------------------------------------------------------------------


async def test_availability_is_cook_only(accounts) -> None:
    assert (await accounts.client.get(AVAILABILITY)).status_code == 401
    await accounts.customer()
    assert (await accounts.client.get(AVAILABILITY)).status_code == 403
    put = await accounts.client.put(AVAILABILITY, json={"timezone": "UTC"})
    assert put.status_code == 403


async def test_new_kitchens_take_orders_any_time(accounts) -> None:
    await accounts.cook()
    body = (await accounts.client.get(AVAILABILITY)).json()
    assert (body["timezone"], body["orders_paused"], body["hours"]) == ("UTC", False, [])
    assert body["availability"]["status"] == "anytime"
    assert body["availability"]["accepting_orders"] is True


async def test_put_replaces_hours_sorted_and_reports_now(accounts) -> None:
    await accounts.cook()
    all_week = [window(day, "00:00", "24:00") for day in reversed(range(7))]
    body = (
        await accounts.client.put(
            AVAILABILITY, json={"timezone": "Europe/London", "hours": all_week}
        )
    ).json()
    assert body["timezone"] == "Europe/London"
    assert [w["day"] for w in body["hours"]] == list(range(7))  # stored sorted
    assert body["availability"]["status"] == "open"
    assert body["availability"]["closes_at"] is not None

    paused = (
        await accounts.client.put(
            AVAILABILITY,
            json={"timezone": "Europe/London", "hours": all_week, "orders_paused": True},
        )
    ).json()
    assert paused["availability"]["status"] == "paused"
    assert (await accounts.client.get(AVAILABILITY)).json()["orders_paused"] is True


async def test_a_future_day_only_schedule_is_closed_until_then(accounts) -> None:
    await accounts.cook()
    later = (utcnow().weekday() + 3) % 7
    body = (
        await accounts.client.put(
            AVAILABILITY, json={"timezone": "UTC", "hours": [window(later, "10:00", "12:00")]}
        )
    ).json()["availability"]
    assert (body["status"], body["accepting_orders"]) == ("closed", False)
    opens = datetime.fromisoformat(body["opens_at"])
    assert opens.weekday() == later and (opens.hour, opens.minute) == (10, 0)
    assert body["next_24h"] == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"timezone": "Mars/Olympus_Mons"}, "timezone"),
        ({"timezone": "../../etc/passwd"}, "timezone"),
        ({"timezone": "UTC", "hours": [window(0, "12:00", "11:00")]}, "hours.0"),
        ({"timezone": "UTC", "hours": [window(0, "25:00", "23:00")]}, "hours.0.opens"),
        ({"timezone": "UTC", "hours": [window(7, "10:00", "11:00")]}, "hours.0.day"),
        (
            {"timezone": "UTC", "hours": [window(1, "10:00", "14:00"), window(1, "13:00", "15:00")]},
            "hours",
        ),
        ({"timezone": "UTC", "hours": [window(1, f"0{h}:00", f"0{h}:30") for h in range(4)]}, "hours"),
    ],
)
async def test_bad_settings_are_422s_naming_the_field(accounts, body, field) -> None:
    await accounts.cook()
    response = await accounts.client.put(AVAILABILITY, json=body)
    assert response.status_code == 422, response.text
    assert [d["field"] for d in response.json()["error"]["details"]] == [field]


# --- public + ordering ------------------------------------------------------------------------


async def test_public_cards_carry_the_availability(accounts) -> None:
    created = await accounts.cook()
    cook_id = created.json()["user_id"]
    await accounts.client.put(AVAILABILITY, json={"timezone": "UTC", "orders_paused": True})
    listed = (await accounts.client.get("/api/cooks")).json()["items"][0]
    detail = (await accounts.client.get(f"/api/cooks/{cook_id}")).json()
    for card in (listed, detail):
        assert card["availability"]["status"] == "paused"
        assert card["availability"]["accepting_orders"] is False


async def test_orders_are_placed_only_while_the_kitchen_takes_them(market) -> None:
    client = market.client
    await market.login(CHEF_A)
    await client.put(AVAILABILITY, json={"timezone": "UTC", "orders_paused": True})

    await market.login(BUYER)
    await market.add("curry", 2)  # filling the bag is always fine
    refused = await market.place()
    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == "kitchen_closed"
    assert error["details"] == {"status": "paused", "opens_at": None}
    cart = (await client.get("/api/cart")).json()
    assert cart["item_count"] == 2  # nothing changed
    assert (await client.get(ORDERS)).json()["total"] == 0

    later = (utcnow().weekday() + 3) % 7
    await market.login(CHEF_A)
    await client.put(
        AVAILABILITY, json={"timezone": "UTC", "hours": [window(later, "10:00", "12:00")]}
    )
    await market.login(BUYER)
    closed = (await market.place()).json()["error"]
    assert closed["code"] == "kitchen_closed"
    assert closed["details"]["status"] == "closed"
    assert datetime.fromisoformat(closed["details"]["opens_at"]).weekday() == later

    await market.login(CHEF_A)
    await client.put(AVAILABILITY, json={"timezone": "UTC", "hours": []})
    await market.login(BUYER)
    assert (await market.place()).status_code == 201

"""Orders: placing the cart, who sees what, and the status flow.

Acceptance rules under test:

* placing needs a login and turns the *account* cart into a ``placed`` order:
  names and current prices are copied, totals stored, the cart emptied; an
  empty cart or unavailable lines are 409s, and nothing changes then;
* a concurrent cart change rolls the whole placement back (409
  ``cart_changed``);
* orders outlive later dish edits and deletion (snapshot lines, ``dish_id``
  SET NULL);
* customers see their own orders, cooks the ones placed with them - anyone
  else's id is a 404; cook endpoints are 403 for non-cooks, 401 anonymous;
* status moves: placed -> accepted | cancelled, accepted -> ready |
  cancelled (cook); the customer cancels only ``placed`` and confirms receipt
  of a ``ready`` order - the only way to ``completed`` (never the cook's);
  every step is stamped; a move from a stale status loses (409);
* fulfilment: ``pickup`` by default and stored on the order; ``delivery`` is
  part of the contract but refused for now (422 ``fulfilment_unavailable``);
* a cook rejecting (placed -> cancelled) or cancelling an order may say why:
  the ``reason`` is trimmed, capped, only allowed when cancelling, and shown
  to the customer as ``cancel_reason``;
* the cook's list can be sorted oldest first - the queue of requests.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.core.db import get_sessionmaker
from app.modules.cart import service as cart_service
from app.modules.cart.models import CartItem
from app.modules.orders import service as order_service
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.orders.schemas import OrderPlaceRequest
from tests.conftest import (
    BUYER,
    CHEF_A,
    CHEF_B,
    COOK_ORDERS,
    ORDERS,
    OTHER_BUYER,
    receive,
)


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    return error


async def order_rows() -> int:
    async with get_sessionmaker()() as session:
        return await session.scalar(select(func.count()).select_from(Order)) or 0


# --- placing -------------------------------------------------------------------------------


async def test_placing_freezes_the_cart_into_an_order(market) -> None:
    await market.login(BUYER)
    await market.add("curry", 2)
    await market.add("tart", 1)

    response = await market.place()
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "placed"
    assert order["cook"] == {"id": order["cook"]["id"], "name": "Chef Ana"}
    assert order["customer"]["name"] == "Bea Buyer"
    # Lines keep the cart's order (newest first) and copy name + price.
    assert [
        (i["name"], i["unit_price"], i["quantity"], i["line_total"])
        for i in order["items"]
    ] == [
        ("Custard tart", 500, 1, 500),
        ("Veg curry", 800, 2, 1600),
    ]
    assert (order["item_count"], order["total"]) == (3, 2100)
    assert order["note"] is None
    assert order["created_at"].endswith("Z") or order["created_at"].endswith("+00:00")
    assert all(
        order[k] is None
        for k in ("accepted_at", "ready_at", "completed_at", "cancelled_at")
    )

    cart = (await market.client.get("/api/cart")).json()
    assert cart["items"] == [] and cart["total"] == 0  # emptied


async def test_note_is_trimmed_blank_is_none_and_length_is_capped(market) -> None:
    order = await market.order(("curry", 1), note="  no onions please  ")
    assert order["note"] == "no onions please"

    await market.add("curry", 1)
    blank = await market.place(note="   ")
    assert blank.status_code == 201 and blank.json()["note"] is None

    await market.add("curry", 1)
    too_long = await market.place(note="x" * 301)
    assert_error(too_long, 422, "validation_failed")


async def test_guests_must_log_in_and_keep_their_cart(market) -> None:
    await market.add("curry", 2)  # a guest cart (cookie)
    assert_error(await market.client.post(ORDERS), 401, "unauthenticated")
    assert (await market.client.get("/api/cart")).json()["item_count"] == 2
    assert await order_rows() == 0


async def test_an_empty_cart_cannot_be_ordered(market) -> None:
    await market.login(BUYER)
    assert_error(await market.place(), 409, "cart_empty")


async def test_unavailable_lines_block_placing_and_nothing_changes(market) -> None:
    await market.login(BUYER)
    await market.add("curry", 1)
    await market.add("tart", 2)
    await market.login(CHEF_A)
    await market.client.patch(
        f"/api/me/dishes/{market.ids['tart']}", json={"active": False}
    )

    await market.login(BUYER)
    error = assert_error(await market.place(), 409, "cart_has_unavailable")
    assert error["details"] == [{"dish_id": market.ids["tart"], "name": "Custard tart"}]
    assert await order_rows() == 0
    assert len((await market.client.get("/api/cart")).json()["items"]) == 2


async def test_a_cart_changed_mid_placement_rolls_everything_back(
    market, monkeypatch
) -> None:
    """Read the cart, then an add lands before the cart is emptied: the
    placement must not go through (no order, cart untouched)."""
    await market.login(BUYER)
    address_id = uuid.UUID(await market.address())
    await market.add("curry", 1)
    async with get_sessionmaker()() as session:
        me = (await market.client.get("/api/me")).json()["id"]
        owner = cart_service.CartOwner(user_id=uuid.UUID(me))
        stale = await cart_service.get_cart(session, owner)
    await market.add("tart", 1)  # the concurrent change

    async def stale_cart(*_args, **_kwargs):
        return stale

    monkeypatch.setattr(order_service.cart_service, "get_cart", stale_cart)
    async with get_sessionmaker()() as session:
        with pytest.raises(order_service.CartChangedError):
            await order_service.place_order(
                session, owner.user_id, OrderPlaceRequest(address_id=address_id)
            )
    monkeypatch.undo()

    assert await order_rows() == 0
    async with get_sessionmaker()() as session:
        lines = await session.scalar(select(func.count()).select_from(CartItem))
    assert lines == 2


async def test_orders_outlive_dish_edits_and_deletion(market) -> None:
    order = await market.order(("curry", 2))
    await market.login(CHEF_A)
    dish = market.ids["curry"]
    await market.client.patch(
        f"/api/me/dishes/{dish}", json={"name": "Curry v2", "price": 1200}
    )
    edited = (await market.client.get(f"{COOK_ORDERS}/{order['id']}")).json()
    assert edited["items"] == [
        {
            "dish_id": dish,
            "name": "Veg curry",  # not "Curry v2"
            "unit_price": 800,  # not 1200
            "quantity": 2,
            "line_total": 1600,
        }
    ]

    assert (await market.client.delete(f"/api/me/dishes/{dish}")).status_code == 204
    kept = (await market.client.get(f"{COOK_ORDERS}/{order['id']}")).json()
    assert kept["items"][0]["dish_id"] is None  # SET NULL, the line stays
    assert (kept["items"][0]["name"], kept["total"]) == ("Veg curry", 1600)


# --- visibility ----------------------------------------------------------------------------


async def test_customers_list_and_read_only_their_own_orders(market) -> None:
    first = await market.order(("curry", 1))
    second = await market.order(("pizza", 1))
    theirs = await market.order(("tart", 1), buyer=OTHER_BUYER)

    await market.login(BUYER)
    page = (await market.client.get(ORDERS)).json()
    assert page["total"] == 2
    assert [o["id"] for o in page["items"]] == [
        second["id"],
        first["id"],
    ]  # newest first
    assert (await market.client.get(f"{ORDERS}/{first['id']}")).status_code == 200
    assert_error(await market.client.get(f"{ORDERS}/{theirs['id']}"), 404, "not_found")
    assert_error(
        await market.client.post(f"{ORDERS}/{theirs['id']}/cancel"), 404, "not_found"
    )

    small = (await market.client.get(ORDERS, params={"limit": 1, "offset": 1})).json()
    assert (small["total"], [o["id"] for o in small["items"]]) == (2, [first["id"]])


async def test_status_filter_and_its_validation(market) -> None:
    order = await market.order(("curry", 1))
    await market.order(("tart", 1))
    await market.client.post(f"{ORDERS}/{order['id']}/cancel")

    cancelled = (await market.client.get(ORDERS, params={"status": "cancelled"})).json()
    assert [o["id"] for o in cancelled["items"]] == [order["id"]]
    assert_error(
        await market.client.get(ORDERS, params={"status": "lost"}),
        422,
        "validation_failed",
    )


async def test_status_filter_repeats_to_mean_any_of_them(market) -> None:
    """``?status=placed&status=accepted`` - the frontend's "active" tab."""
    placed = await market.order(("curry", 1))
    accepted = await market.order(("tart", 1))
    done = await market.order(("curry", 2))
    await market.login(CHEF_A)
    await market.client.patch(
        f"{COOK_ORDERS}/{accepted['id']}", json={"status": "accepted"}
    )
    for status in ("accepted", "ready", "completed"):
        await market.client.patch(
            f"{COOK_ORDERS}/{done['id']}", json={"status": status}
        )

    await market.login(BUYER)
    active = (
        await market.client.get(
            ORDERS, params=[("status", "placed"), ("status", "accepted")]
        )
    ).json()
    assert {o["id"] for o in active["items"]} == {placed["id"], accepted["id"]}
    assert active["total"] == 2
    assert (await market.client.get(ORDERS)).json()["total"] == 3  # none = all


async def test_cooks_see_only_orders_placed_with_them(market) -> None:
    order = await market.order(("curry", 1))

    await market.login(CHEF_A)
    mine = (await market.client.get(COOK_ORDERS)).json()
    assert [o["id"] for o in mine["items"]] == [order["id"]]
    assert mine["items"][0]["customer"]["name"] == "Bea Buyer"

    await market.login(CHEF_B)
    assert (await market.client.get(COOK_ORDERS)).json()["total"] == 0
    assert_error(
        await market.client.get(f"{COOK_ORDERS}/{order['id']}"), 404, "not_found"
    )
    assert_error(
        await market.client.patch(
            f"{COOK_ORDERS}/{order['id']}", json={"status": "accepted"}
        ),
        404,
        "not_found",
    )


async def test_cook_order_endpoints_are_role_gated(market) -> None:
    assert_error(await market.client.get(COOK_ORDERS), 401, "unauthenticated")
    await market.login(BUYER)
    assert_error(await market.client.get(COOK_ORDERS), 403, "forbidden")


# --- status flow -----------------------------------------------------------------------------


async def test_cook_prepares_and_the_customer_completes_step_by_step(market) -> None:
    order = await market.order(("curry", 1))
    await market.login(CHEF_A)
    url = f"{COOK_ORDERS}/{order['id']}"

    skip = assert_error(
        await market.client.patch(url, json={"status": "completed"}),
        409,
        "invalid_status_transition",
    )
    assert skip["details"] == {
        "status": "placed",
        "requested": "completed",
        "allowed": ["accepted", "cancelled"],
    }
    for status, stamp in (("accepted", "accepted_at"), ("ready", "ready_at")):
        response = await market.client.patch(url, json={"status": status})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status
        assert response.json()[stamp] is not None

    # A ready order waits for the customer: the cook cannot complete it.
    not_yours = assert_error(
        await market.client.patch(url, json={"status": "completed"}),
        409,
        "invalid_status_transition",
    )
    assert not_yours["details"] == {
        "status": "ready",
        "requested": "completed",
        "allowed": [],
    }
    assert "customer" in not_yours["message"]

    await market.login(BUYER)
    received = await receive(market.client, order["id"])
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "completed"
    assert received.json()["completed_at"] is not None

    await market.login(CHEF_A)
    done = (await market.client.get(url)).json()
    assert done["accepted_at"] <= done["ready_at"] <= done["completed_at"]
    final = assert_error(
        await market.client.patch(url, json={"status": "cancelled"}),
        409,
        "invalid_status_transition",
    )
    assert final["details"]["allowed"] == []
    assert_error(
        await market.client.patch(url, json={"status": "placed"}),
        422,
        "validation_failed",
    )


async def test_customer_cancels_only_while_placed(market) -> None:
    first = await market.order(("curry", 1))
    cancelled = await market.client.post(f"{ORDERS}/{first['id']}/cancel")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert (body["status"], body["cancelled_by"]) == ("cancelled", "customer")
    assert body["cancelled_at"] is not None

    second = await market.order(("curry", 1))
    await market.login(CHEF_A)
    await market.client.patch(
        f"{COOK_ORDERS}/{second['id']}", json={"status": "accepted"}
    )
    await market.login(BUYER)
    refused = assert_error(
        await market.client.post(f"{ORDERS}/{second['id']}/cancel"),
        409,
        "invalid_status_transition",
    )
    assert "only placed orders can be cancelled" in refused["message"]


async def test_cook_can_cancel_an_accepted_order(market) -> None:
    order = await market.order(("curry", 1))
    await market.login(CHEF_A)
    url = f"{COOK_ORDERS}/{order['id']}"
    await market.client.patch(url, json={"status": "accepted"})
    body = (await market.client.patch(url, json={"status": "cancelled"})).json()
    assert (body["status"], body["cancelled_by"]) == ("cancelled", "cook")


async def test_a_move_from_a_stale_status_loses(market) -> None:
    """Compare-and-set: the customer's cancel is decided against a stale
    'placed' while the cook already accepted - it must not overwrite."""
    order = await market.order(("curry", 1))
    async with get_sessionmaker()() as session:
        stale = await order_service.get_order(session, uuid.UUID(order["id"]))
    await market.login(CHEF_A)
    await market.client.patch(
        f"{COOK_ORDERS}/{order['id']}", json={"status": "accepted"}
    )

    async with get_sessionmaker()() as session:
        with pytest.raises(order_service.InvalidStatusTransitionError) as lost:
            await order_service.cancel_by_customer(session, stale)
    assert lost.value.details["status"] == "accepted"
    async with get_sessionmaker()() as session:
        status = await session.scalar(select(Order.status))
    assert status == OrderStatus.ACCEPTED.value


async def test_deleting_an_order_deletes_its_lines(market) -> None:
    order = await market.order(("curry", 1), ("tart", 1))
    async with get_sessionmaker()() as session:
        row = await session.get(Order, uuid.UUID(order["id"]))
        await session.delete(row)
        await session.commit()
        left = await session.scalar(select(func.count()).select_from(OrderItem))
    assert left == 0


# --- accept / reject with a reason ---------------------------------------------------------


async def test_cook_rejects_a_request_and_the_customer_sees_why(market) -> None:
    order = await market.order(("curry", 1))
    assert order["cancel_reason"] is None
    await market.login(CHEF_A)
    rejected = await market.client.patch(
        f"{COOK_ORDERS}/{order['id']}",
        json={"status": "cancelled", "reason": "  Sold out for today  "},
    )
    assert rejected.status_code == 200, rejected.text
    body = rejected.json()
    assert (body["status"], body["cancelled_by"], body["cancel_reason"]) == (
        "cancelled",
        "cook",
        "Sold out for today",
    )
    assert body["accepted_at"] is None  # a rejection: never accepted

    await market.login(BUYER)
    seen = (await market.client.get(f"{ORDERS}/{order['id']}")).json()
    assert seen["cancel_reason"] == "Sold out for today"


async def test_cook_cancels_after_accepting_with_a_reason(market) -> None:
    order = await market.order(("curry", 1))
    await market.login(CHEF_A)
    url = f"{COOK_ORDERS}/{order['id']}"
    await market.client.patch(url, json={"status": "accepted"})
    body = (
        await market.client.patch(
            url, json={"status": "cancelled", "reason": "Ran out of rice"}
        )
    ).json()
    assert body["accepted_at"] is not None
    assert (body["cancelled_by"], body["cancel_reason"]) == ("cook", "Ran out of rice")


async def test_reason_rules(market) -> None:
    order = await market.order(("curry", 1))
    await market.login(CHEF_A)
    url = f"{COOK_ORDERS}/{order['id']}"

    only_cancelling = assert_error(
        await market.client.patch(url, json={"status": "accepted", "reason": "yes!"}),
        422,
        "validation_failed",
    )
    assert "only be given when cancelling" in only_cancelling["details"][0]["message"]
    too_long = assert_error(
        await market.client.patch(url, json={"status": "cancelled", "reason": "x" * 201}),
        422,
        "validation_failed",
    )
    assert too_long["details"][0]["field"] == "reason"
    assert (await market.client.get(url)).json()["status"] == "placed"  # untouched

    blank = await market.client.patch(url, json={"status": "cancelled", "reason": "  "})
    assert blank.status_code == 200
    assert blank.json()["cancel_reason"] is None  # blank means no reason


async def test_customer_cancellations_carry_no_reason(market) -> None:
    order = await market.order(("curry", 1))
    body = (await market.client.post(f"{ORDERS}/{order['id']}/cancel")).json()
    assert (body["cancelled_by"], body["cancel_reason"]) == ("customer", None)


# --- the cook's queue ------------------------------------------------------------------------


async def test_cook_queue_lists_requests_oldest_first(market) -> None:
    first = await market.order(("curry", 1))
    second = await market.order(("tart", 1), buyer=OTHER_BUYER)
    third = await market.order(("curry", 2))
    await market.order(("pizza", 1))  # Chef Bruno's - never in Chef Ana's queue
    await market.login(CHEF_A)
    await market.client.patch(
        f"{COOK_ORDERS}/{second['id']}", json={"status": "accepted"}
    )

    def ids(response) -> list[str]:
        assert response.status_code == 200, response.text
        return [o["id"] for o in response.json()["items"]]

    queue = await market.client.get(
        COOK_ORDERS, params={"status": "placed", "sort": "oldest"}
    )
    assert ids(queue) == [first["id"], third["id"]]
    assert ids(await market.client.get(COOK_ORDERS)) == [
        third["id"],
        second["id"],
        first["id"],
    ]  # newest first by default
    assert ids(
        await market.client.get(COOK_ORDERS, params={"sort": "oldest", "limit": 1, "offset": 1})
    ) == [second["id"]]
    assert_error(
        await market.client.get(COOK_ORDERS, params={"sort": "random"}),
        422,
        "validation_failed",
    )


# --- receipt: the customer completes the order ---------------------------------------


async def test_the_customer_confirms_receipt_only_when_ready(market) -> None:
    order = await market.order(("curry", 1))
    for status in ("placed", "accepted"):
        if status == "accepted":
            await market.login(CHEF_A)
            await market.client.patch(
                f"{COOK_ORDERS}/{order['id']}", json={"status": "accepted"}
            )
            await market.login(BUYER)
        early = assert_error(
            await receive(market.client, order["id"]), 409, "invalid_status_transition"
        )
        assert early["details"] == {
            "status": status,
            "requested": "completed",
            "allowed": ["cancelled"] if status == "placed" else [],
        }
        assert "once the cook marks it ready" in early["message"]

    await market.login(CHEF_A)
    await market.client.patch(f"{COOK_ORDERS}/{order['id']}", json={"status": "ready"})
    await market.login(BUYER)
    assert (await receive(market.client, order["id"])).status_code == 200
    again = assert_error(
        await receive(market.client, order["id"]), 409, "invalid_status_transition"
    )
    assert again["details"]["status"] == "completed"


async def test_only_the_orders_customer_can_confirm_it(market) -> None:
    order = await market.order(("curry", 1))
    await market.login(CHEF_A)
    for status in ("accepted", "ready"):
        await market.client.patch(
            f"{COOK_ORDERS}/{order['id']}", json={"status": status}
        )
    # The cook has no such order among *their purchases*; another buyer
    # neither - same 404 as every foreign order.
    assert_error(await receive(market.client, order["id"]), 404, "not_found")
    await market.login(OTHER_BUYER)
    assert_error(await receive(market.client, order["id"]), 404, "not_found")
    market.client.cookies.clear()
    assert_error(await receive(market.client, order["id"]), 401, "unauthenticated")


# --- fulfilment ---------------------------------------------------------------------


async def test_orders_are_pickup_by_default(market) -> None:
    order = await market.order(("curry", 1))
    assert order["fulfilment"] == "pickup"
    await market.login(BUYER)
    await market.add("curry", 1)
    explicit = await market.place(fulfilment="pickup")
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["fulfilment"] == "pickup"


async def test_delivery_is_not_offered_yet(market) -> None:
    await market.login(BUYER)
    await market.add("curry", 1)
    refused = assert_error(await market.place(fulfilment="delivery"), 422, "validation_failed")
    assert refused["details"] == [
        {
            "field": "fulfilment",
            "type": "fulfilment_unavailable",
            "message": "delivery is not available yet (offered: pickup)",
        }
    ]
    # Nothing was placed: the cart is intact.
    assert (await market.client.get("/api/cart")).json()["item_count"] == 1
    unknown = assert_error(await market.place(fulfilment="drone"), 422, "validation_failed")
    assert unknown["details"][0]["field"] == "fulfilment"

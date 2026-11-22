"""Address book (``/api/me/addresses``) and the address on an order.

Acceptance rules under test:

* login required; someone else's address id is a 404;
* validation: required fields never blank, optional blanks become null,
  phones need 6+ digits, an unknown zone slug is a 422 ``unknown_zone``;
* exactly one default: the first address is the default, ``is_default:
  true`` moves it, ``false`` is refused, deleting the default promotes the
  newest remaining address; the database refuses two defaults;
* at most 10 addresses (409 ``address_limit``);
* placing an order needs one of *my* addresses (422 ``unknown_address``)
  and keeps a copy of it - editing or deleting the address later changes
  nothing on the order.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.db import get_sessionmaker
from app.modules.addresses.models import MAX_ADDRESSES, Address
from tests.conftest import ADDRESSES, BUYER, HOME, ORDERS, OTHER_BUYER

WORK = {
    "label": "Work",
    "recipient": "Bea at the office",
    "phone": "(555) 010-2000",
    "line1": "1 Market Street",
    "line2": "Floor 4",
    "city": "Springfield",
    "postal_code": "12345",
    "instructions": "Ask the front desk",
}


def assert_error(response, status: int, code: str, detail_type: str | None = None):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    if detail_type is not None:
        assert detail_type in {d["type"] for d in error["details"]}, error
    return error


async def add(client, body: dict) -> dict:
    response = await client.post(ADDRESSES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def listing(client) -> list[dict]:
    response = await client.get(ADDRESSES)
    assert response.status_code == 200, response.text
    return response.json()


# --- access + validation -----------------------------------------------------------------


async def test_address_book_requires_login(client) -> None:
    assert_error(await client.get(ADDRESSES), 401, "unauthenticated")
    assert_error(await client.post(ADDRESSES, json=HOME), 401, "unauthenticated")


async def test_addresses_are_private(market) -> None:
    await market.login(BUYER)
    mine = await add(market.client, HOME)
    await market.login(OTHER_BUYER)
    assert await listing(market.client) == []
    url = f"{ADDRESSES}/{mine['id']}"
    assert_error(await market.client.patch(url, json={"label": "x"}), 404, "not_found")
    assert_error(await market.client.delete(url), 404, "not_found")


async def test_create_trims_and_normalizes(market, zones) -> None:
    await market.login(BUYER)
    body = await add(
        market.client,
        {**WORK, "recipient": "  Bea  ", "line2": "   ", "zone": " Old-Town "},
    )
    assert body["recipient"] == "Bea"
    assert body["line2"] is None  # blank optional -> null
    assert body["zone"] == {"slug": "old-town", "name": "Old Town", "x": 1, "y": 0}
    assert body["is_default"] is True  # first address


@pytest.mark.parametrize(
    ("change", "detail_type"),
    [
        ({"recipient": "   "}, "value_error"),
        ({"line1": ""}, "value_error"),
        ({"phone": "12345"}, "value_error"),  # fewer than 6 digits
        ({"phone": "call me maybe"}, "value_error"),
        ({"city": "x" * 81}, "string_too_long"),
        ({"zone": "atlantis"}, "unknown_zone"),
    ],
)
async def test_create_validation(market, zones, change, detail_type) -> None:
    await market.login(BUYER)
    response = await market.client.post(ADDRESSES, json={**HOME, **change})
    assert_error(response, 422, "validation_failed", detail_type)


async def test_patch_edits_clears_and_refuses_clearing_required(market) -> None:
    await market.login(BUYER)
    created = await add(market.client, WORK)
    url = f"{ADDRESSES}/{created['id']}"

    edited = (
        await market.client.patch(url, json={"city": "Shelbyville", "line2": None})
    ).json()
    assert (edited["city"], edited["line2"], edited["line1"]) == (
        "Shelbyville",
        None,
        WORK["line1"],
    )
    assert_error(
        await market.client.patch(url, json={"city": None}), 422, "validation_failed"
    )
    assert_error(await market.client.patch(url, json={}), 422, "validation_failed")


# --- default ------------------------------------------------------------------------------


async def test_exactly_one_default_at_all_times(market) -> None:
    await market.login(BUYER)
    home = await add(market.client, HOME)
    work = await add(market.client, WORK)
    assert (home["is_default"], work["is_default"]) == (True, False)

    moved = await market.client.patch(
        f"{ADDRESSES}/{work['id']}", json={"is_default": True}
    )
    assert moved.json()["is_default"] is True
    book = await listing(market.client)
    assert [a["id"] for a in book] == [work["id"], home["id"]]  # default first
    assert [a["is_default"] for a in book] == [True, False]

    refused = await market.client.patch(
        f"{ADDRESSES}/{work['id']}", json={"is_default": False}
    )
    assert_error(refused, 422, "validation_failed")

    third = await add(market.client, {**HOME, "label": "Gym", "is_default": True})
    assert [a["id"] for a in await listing(market.client) if a["is_default"]] == [
        third["id"]
    ]


async def test_deleting_the_default_promotes_the_newest(market) -> None:
    await market.login(BUYER)
    home = await add(market.client, HOME)
    older = await add(market.client, WORK)
    newest = await add(market.client, {**WORK, "label": "Studio"})
    assert home["is_default"]

    assert (await market.client.delete(f"{ADDRESSES}/{home['id']}")).status_code == 204
    book = await listing(market.client)
    assert {a["id"]: a["is_default"] for a in book} == {
        newest["id"]: True,
        older["id"]: False,
    }


async def test_database_refuses_a_second_default(market) -> None:
    await market.login(BUYER)
    home = await add(market.client, HOME)
    async with get_sessionmaker()() as session:
        first = await session.get(Address, uuid.UUID(home["id"]))
        assert first is not None
        session.add(
            Address(
                user_id=first.user_id,
                recipient="x",
                phone="5550100",
                line1="y",
                city="z",
                is_default=True,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_at_most_ten_addresses(market) -> None:
    await market.login(BUYER)
    for index in range(MAX_ADDRESSES):
        await add(market.client, {**HOME, "label": f"Place {index}"})
    assert_error(await market.client.post(ADDRESSES, json=HOME), 409, "address_limit")


# --- orders ---------------------------------------------------------------------------------


async def test_orders_need_one_of_my_addresses(market) -> None:
    await market.login(OTHER_BUYER)
    theirs = await add(market.client, HOME)
    await market.login(BUYER)
    await market.add("curry", 1)

    missing = await market.client.post(ORDERS, json={})
    assert_error(missing, 422, "validation_failed")
    foreign = await market.client.post(ORDERS, json={"address_id": theirs["id"]})
    assert_error(foreign, 422, "validation_failed", "unknown_address")
    assert (await market.client.get("/api/cart")).json()["item_count"] == 1  # untouched


async def test_an_order_keeps_a_copy_of_its_address(market, zones) -> None:
    await market.login(BUYER)
    address = await add(market.client, {**WORK, "zone": "harbour"})
    await market.add("curry", 1)
    order = (
        await market.client.post(ORDERS, json={"address_id": address["id"]})
    ).json()
    expected = {
        **{
            k: WORK[k]
            for k in ("label", "recipient", "phone", "line1", "line2", "city")
        },
        "postal_code": WORK["postal_code"],
        "instructions": WORK["instructions"],
        "zone": {"slug": "harbour", "name": "Harbour", "x": 0, "y": 2},
    }
    assert order["delivery_address"] == expected

    url = f"{ADDRESSES}/{address['id']}"
    await market.client.patch(url, json={"line1": "Somewhere else"})
    await market.client.delete(url)
    again = (await market.client.get(f"{ORDERS}/{order['id']}")).json()
    assert again["delivery_address"] == expected

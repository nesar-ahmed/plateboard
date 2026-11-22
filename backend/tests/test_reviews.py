from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import update

from app.core.db import get_sessionmaker
from app.modules.auth.models import ROLE_ADMIN, User
from app.shared.base import utcnow
from tests.conftest import (
    BUYER,
    CHEF_A,
    CHEF_B,
    COOK_ORDERS,
    OTHER_BUYER,
    receive,
    set_order_times,
)

MY_REVIEWS = "/api/me/reviews"
PENDING = "/api/me/reviews/pending"
COOK_REVIEWS = "/api/cooks/me/reviews"


def assert_error(response, status: int, code: str, detail_type: str | None = None):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    if detail_type is not None:
        assert detail_type in {d["type"] for d in error["details"]}, error
    return error


async def write(client, order: dict, dish_id: str, rating: int = 5, **body):
    return await client.post(
        MY_REVIEWS,
        json={"order_id": order["id"], "dish_id": dish_id, "rating": rating, **body},
    )


async def review(market, order: dict, key: str, rating: int = 5, **body) -> dict:
    response = await write(market.client, order, market.ids[key], rating, **body)
    assert response.status_code == 201, response.text
    return response.json()


async def completed(market, *lines: tuple[str, int], buyer: str = BUYER) -> dict:
    return await market.complete(await market.order(*lines, buyer=buyer))


async def move(market, order: dict, *statuses: str) -> None:
    await market.login(CHEF_A if order["cook"]["name"] == "Chef Ana" else CHEF_B)
    for status in statuses:
        moved = await market.client.patch(
            f"{COOK_ORDERS}/{order['id']}", json={"status": status}
        )
        assert moved.status_code == 200, moved.text


async def inbox(client, audience: str) -> list[dict]:
    response = await client.get(
        "/api/me/notifications", params={"audience": audience, "limit": 50}
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- access ------------------------------------------------------------------------------


async def test_reviews_require_login(client) -> None:
    some = str(uuid.uuid4())
    for response in (
        await client.get(MY_REVIEWS),
        await client.get(PENDING),
        await client.post(MY_REVIEWS, json={}),
        await client.patch(f"{MY_REVIEWS}/{some}", json={"rating": 3}),
        await client.delete(f"{MY_REVIEWS}/{some}"),
        await client.get(COOK_REVIEWS),
        await client.put(f"{COOK_REVIEWS}/{some}/reply", json={"reply": "Thanks"}),
    ):
        assert_error(response, 401, "unauthenticated")


async def test_writing_needs_the_customer_role_and_replying_the_cook_role(market) -> None:
    await market.login(BUYER)
    assert_error(await market.client.get(COOK_REVIEWS), 403, "forbidden")
    async with get_sessionmaker()() as session:
        await session.execute(
            update(User).where(User.email == BUYER).values(roles=[ROLE_ADMIN])
        )
        await session.commit()
    assert_error(await market.client.get(MY_REVIEWS), 403, "forbidden")


# --- who may review what ------------------------------------------------------------------


async def test_review_a_dish_after_the_whole_order_cycle(market) -> None:
    order = await completed(market, ("curry", 1), ("tart", 2))
    assert order["status"] == "completed"
    assert order["accepted_at"] and order["ready_at"] and order["completed_at"]

    created = await review(market, order, "curry", 4, comment="  Lovely and warming  ")
    assert created["rating"] == 4
    assert created["comment"] == "Lovely and warming"  # trimmed
    assert created["dish_id"] == market.ids["curry"]
    assert created["dish_name"] == "Veg curry"
    assert created["order_id"] == order["id"]
    assert created["cook_name"] == "Chef Ana"
    assert created["author_name"] == "Bea B."
    assert created["edited_at"] is None and created["reply"] is None

    mine = (await market.client.get(MY_REVIEWS)).json()
    assert [item["id"] for item in mine["items"]] == [created["id"]]
    one = await market.client.get(f"{MY_REVIEWS}/{created['id']}")
    assert one.status_code == 200 and one.json() == created


async def test_orders_that_have_not_completed_the_cycle_cannot_be_reviewed(market) -> None:
    curry = market.ids["curry"]

    placed = await market.order(("curry", 1))
    error = assert_error(
        await write(market.client, placed, curry), 409, "order_not_completed"
    )
    assert error["details"]["status"] == "placed"
    assert set(error["details"]["missing"]) == {
        "status",
        "accepted_at",
        "ready_at",
        "completed_at",
    }

    await move(market, placed, "accepted")
    await market.login(BUYER)
    error = assert_error(await write(market.client, placed, curry), 409, "order_not_completed")
    assert error["details"]["status"] == "accepted"

    await move(market, placed, "ready")  # ready, but not yet received
    await market.login(BUYER)
    error = assert_error(await write(market.client, placed, curry), 409, "order_not_completed")
    assert error["details"]["missing"] == ["status", "completed_at"]

    assert (await receive(market.client, placed["id"])).status_code == 200
    assert (await write(market.client, placed, curry)).status_code == 201


async def test_cancelled_orders_cannot_be_reviewed(market) -> None:
    curry = market.ids["curry"]
    withdrawn = await market.order(("curry", 1))
    assert (await market.client.post(f"/api/me/orders/{withdrawn['id']}/cancel")).status_code == 200
    assert_error(await write(market.client, withdrawn, curry), 409, "order_not_completed")

    rejected = await market.order(("curry", 1))
    await move(market, rejected, "cancelled")
    await market.login(BUYER)
    assert_error(await write(market.client, rejected, curry), 409, "order_not_completed")

    cancelled_late = await market.order(("curry", 1))
    await move(market, cancelled_late, "accepted", "ready")
    await set_order_times(cancelled_late["id"], status="cancelled", cancelled_at=utcnow())
    await market.login(BUYER)
    assert_error(await write(market.client, cancelled_late, curry), 409, "order_not_completed")


async def test_a_completed_status_without_every_step_is_not_enough(market) -> None:
    # "completed" written without the cook's accept/ready steps must not count.
    order = await market.order(("curry", 1))
    await set_order_times(order["id"], status="completed", completed_at=utcnow())
    error = assert_error(
        await write(market.client, order, market.ids["curry"]), 409, "order_not_completed"
    )
    assert error["details"] == {
        "status": "completed",
        "missing": ["accepted_at", "ready_at"],
    }


async def test_only_my_orders_and_their_dishes(market) -> None:
    theirs = await completed(market, ("curry", 1), buyer=OTHER_BUYER)
    await market.login(BUYER)
    assert_error(
        await write(market.client, theirs, market.ids["curry"]),
        422,
        "validation_failed",
        "unknown_order",
    )
    assert_error(
        await write(market.client, {"id": str(uuid.uuid4())}, market.ids["curry"]),
        422,
        "validation_failed",
        "unknown_order",
    )

    mine = await completed(market, ("curry", 1))
    assert_error(
        await write(market.client, mine, market.ids["tart"]),  # same kitchen, not ordered
        422,
        "validation_failed",
        "not_in_order",
    )


async def test_rating_and_comment_validation(market) -> None:
    order = await completed(market, ("curry", 1), ("tart", 1))
    curry = market.ids["curry"]
    for rating in (0, 6, None):
        assert_error(
            await market.client.post(
                MY_REVIEWS,
                json={"order_id": order["id"], "dish_id": curry, "rating": rating},
            ),
            422,
            "validation_failed",
        )
    assert_error(
        await write(market.client, order, curry, 5, comment="x" * 1001),
        422,
        "validation_failed",
    )
    blank = await review(market, order, "tart", 3, comment="   ")
    assert blank["comment"] is None  # blank words = no words


async def test_one_review_per_dish(market) -> None:
    first_order = await completed(market, ("curry", 1))
    created = await review(market, first_order, "curry")
    error = assert_error(
        await write(market.client, first_order, market.ids["curry"]), 409, "already_reviewed"
    )
    assert error["details"] == {"review_id": created["id"]}

    # Another completed order with the same dish: still one review.
    second_order = await completed(market, ("curry", 2))
    error = assert_error(
        await write(market.client, second_order, market.ids["curry"]), 409, "already_reviewed"
    )
    assert error["details"]["review_id"] == created["id"]


async def test_parallel_duplicate_reviews_store_one(market) -> None:
    order = await completed(market, ("curry", 1))
    responses = await asyncio.gather(
        write(market.client, order, market.ids["curry"], 5),
        write(market.client, order, market.ids["curry"], 4),
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert (await market.client.get(MY_REVIEWS)).json()["total"] == 1


# --- what to review next ------------------------------------------------------------------


async def test_pending_lists_received_dishes_not_yet_reviewed(market) -> None:
    await market.order(("pizza", 1))  # an open order: nothing to review there
    older = await completed(market, ("curry", 1))
    newer = await completed(market, ("curry", 1), ("tart", 1))

    pending = (await market.client.get(PENDING)).json()
    assert pending["total"] == 2
    by_dish = {item["dish_id"]: item for item in pending["items"]}
    assert set(by_dish) == {market.ids["curry"], market.ids["tart"]}
    # Each dish once, with my latest completed order that had it.
    assert by_dish[market.ids["curry"]]["order_id"] == newer["id"]
    assert by_dish[market.ids["curry"]]["cook_name"] == "Chef Ana"
    assert by_dish[market.ids["curry"]]["dish_available"] is True
    assert older["id"] not in {item["order_id"] for item in pending["items"]}

    await review(market, newer, "tart")
    pending = (await market.client.get(PENDING)).json()
    assert [item["dish_id"] for item in pending["items"]] == [market.ids["curry"]]


async def test_my_reviews_and_pending_filter_by_dish(market) -> None:
    order = await completed(market, ("curry", 1), ("tart", 1))
    created = await review(market, order, "curry")
    curry, tart = market.ids["curry"], market.ids["tart"]

    mine = (await market.client.get(MY_REVIEWS, params={"dish_id": curry})).json()
    assert [i["id"] for i in mine["items"]] == [created["id"]]
    assert (await market.client.get(MY_REVIEWS, params={"dish_id": tart})).json()["total"] == 0

    pending = (await market.client.get(PENDING, params={"dish_id": tart})).json()
    assert [(i["dish_id"], i["order_id"]) for i in pending["items"]] == [(tart, order["id"])]
    assert (await market.client.get(PENDING, params={"dish_id": curry})).json()["total"] == 0


async def test_pending_skips_deleted_dishes_but_keeps_hidden_ones(market) -> None:
    await completed(market, ("curry", 1), ("tart", 1))
    await market.login(CHEF_A)
    hide = await market.client.patch(f"/api/me/dishes/{market.ids['curry']}", json={"active": False})
    assert hide.status_code == 200
    assert (await market.client.delete(f"/api/me/dishes/{market.ids['tart']}")).status_code == 204

    await market.login(BUYER)
    pending = (await market.client.get(PENDING)).json()
    assert [(i["dish_id"], i["dish_available"]) for i in pending["items"]] == [
        (market.ids["curry"], False)
    ]


# --- editing + deleting ----------------------------------------------------------------------


async def test_the_author_edits_and_deletes(market) -> None:
    order = await completed(market, ("curry", 1))
    created = await review(market, order, "curry", 5, comment="Great")
    url = f"{MY_REVIEWS}/{created['id']}"

    unchanged = await market.client.patch(url, json={"rating": 5})
    assert unchanged.json()["edited_at"] is None  # same value: not an edit

    edited = await market.client.patch(url, json={"rating": 3, "comment": None})
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["rating"], body["comment"]) == (3, None)
    assert body["edited_at"] is not None

    assert_error(await market.client.patch(url, json={}), 422, "validation_failed")
    assert_error(await market.client.patch(url, json={"rating": None}), 422, "validation_failed")

    assert (await market.client.delete(url)).status_code == 204
    assert_error(await market.client.get(url), 404, "not_found")
    # ...and the dish can be reviewed again.
    again = await write(market.client, order, market.ids["curry"], 4)
    assert again.status_code == 201


async def test_someone_elses_review_is_a_404(market) -> None:
    order = await completed(market, ("curry", 1))
    created = await review(market, order, "curry")
    url = f"{MY_REVIEWS}/{created['id']}"
    await market.login(OTHER_BUYER)
    assert_error(await market.client.get(url), 404, "not_found")
    assert_error(await market.client.patch(url, json={"rating": 1}), 404, "not_found")
    assert_error(await market.client.delete(url), 404, "not_found")


# --- the cook's side -------------------------------------------------------------------------


async def test_the_cook_sees_and_answers_reviews_of_their_dishes(market) -> None:
    order = await completed(market, ("curry", 1), ("tart", 1))
    curry = await review(market, order, "curry", 5, comment="Best curry")
    await review(market, order, "tart", 2)

    await market.login(CHEF_A)
    page = (await market.client.get(COOK_REVIEWS)).json()
    assert page["total"] == 2 and page["unreplied"] == 2
    assert page["summary"]["average"] == 3.5 and page["summary"]["count"] == 2
    item = next(i for i in page["items"] if i["id"] == curry["id"])
    assert item["customer_name"] == "Bea Buyer"
    assert item["order_id"] == order["id"]

    url = f"{COOK_REVIEWS}/{curry['id']}/reply"
    replied = await market.client.put(url, json={"reply": "  Thank you, Bea!  "})
    assert replied.status_code == 200, replied.text
    assert replied.json()["reply"]["body"] == "Thank you, Bea!"

    page = (await market.client.get(COOK_REVIEWS, params={"replied": "false"})).json()
    assert page["total"] == 1 and page["unreplied"] == 1
    assert page["items"][0]["rating"] == 2
    assert (await market.client.get(COOK_REVIEWS, params={"rating": 5})).json()["total"] == 1

    rewritten = await market.client.put(url, json={"reply": "Thanks again!"})
    assert rewritten.json()["reply"]["body"] == "Thanks again!"
    assert_error(await market.client.put(url, json={"reply": "   "}), 422, "validation_failed")

    removed = await market.client.delete(url)
    assert removed.status_code == 200 and removed.json()["reply"] is None
    assert (await market.client.delete(url)).status_code == 200  # idempotent


async def test_a_rating_without_words_still_asks_the_cook_to_reply(market) -> None:
    order = await completed(market, ("curry", 1))
    await review(market, order, "curry", 3)
    await market.login(CHEF_A)
    notice = next(n for n in await inbox(market.client, "cook") if n["type"] == "review.posted")
    assert notice["body"].startswith("Bea Buyer left a rating. Reply")


async def test_another_kitchens_review_is_a_404(market) -> None:
    order = await completed(market, ("curry", 1))
    created = await review(market, order, "curry")
    await market.login(CHEF_B)
    assert (await market.client.get(COOK_REVIEWS)).json()["total"] == 0
    assert_error(await market.client.get(f"{COOK_REVIEWS}/{created['id']}"), 404, "not_found")
    assert_error(
        await market.client.put(f"{COOK_REVIEWS}/{created['id']}/reply", json={"reply": "Hi"}),
        404,
        "not_found",
    )


async def test_reviews_and_replies_notify_the_other_side(market) -> None:
    order = await completed(market, ("curry", 1), ("tart", 1))
    created = await review(market, order, "curry", 4, comment="Lovely, a bit mild")
    await review(market, order, "tart", 5, comment="x" * 300)

    await market.login(CHEF_A)
    posted = {
        n["subject"]["id"]: n
        for n in await inbox(market.client, "cook")
        if n["type"] == "review.posted"
    }
    assert len(posted) == 2
    notice = posted[created["id"]]
    assert notice["title"] == "New 4-star review of Veg curry"
    assert notice["body"].startswith('Bea Buyer wrote: "Lovely, a bit mild"')
    assert "Reply" in notice["body"]
    assert notice["subject"] == {"kind": "review", "id": created["id"]}
    assert notice["actor_id"] is not None and notice["read"] is False
    long = next(n for key, n in posted.items() if key != created["id"])
    assert len(long["data"]["comment"]) == 140 and long["data"]["comment"].endswith("…")

    url = f"{COOK_REVIEWS}/{created['id']}/reply"
    await market.client.put(url, json={"reply": "Thanks!"})
    await market.client.put(url, json={"reply": "Thanks a lot!"})  # an edit: no new notice
    posted = {
        n["subject"]["id"]: n
        for n in await inbox(market.client, "cook")
        if n["type"] == "review.posted"
    }
    assert posted[created["id"]]["read"] is True  # answered = resolved
    assert [n["read"] for key, n in posted.items() if key != created["id"]] == [False]

    await market.login(BUYER)
    replied = [n for n in await inbox(market.client, "account") if n["type"] == "review.replied"]
    assert len(replied) == 1
    assert replied[0]["title"] == "Chef Ana replied to your review"


# --- public lists + ratings ------------------------------------------------------------------


async def test_public_dish_reviews_and_summary(market) -> None:
    curry = market.ids["curry"]
    first = await completed(market, ("curry", 1))
    mine = await review(market, first, "curry", 5, comment="Superb")
    other = await completed(market, ("curry", 1), buyer=OTHER_BUYER)
    await review(market, other, "curry", 2)
    await market.login(CHEF_A)
    await market.client.put(f"{COOK_REVIEWS}/{mine['id']}/reply", json={"reply": "Thanks!"})
    market.client.cookies.clear()  # public: no login

    page = (await market.client.get(f"/api/dishes/{curry}/reviews")).json()
    assert page["total"] == 2
    assert page["summary"]["average"] == 3.5 and page["summary"]["count"] == 2
    assert page["summary"]["distribution"] == [
        {"rating": 5, "count": 1},
        {"rating": 4, "count": 0},
        {"rating": 3, "count": 0},
        {"rating": 2, "count": 1},
        {"rating": 1, "count": 0},
    ]
    assert [i["author_name"] for i in page["items"]] == ["Otto O.", "Bea B."]  # newest first
    superb = page["items"][1]
    assert superb["reply"]["body"] == "Thanks!"
    # Public: no customer id, no order.
    assert "order_id" not in superb and "customer_id" not in superb
    assert "customer_name" not in superb

    five = (await market.client.get(f"/api/dishes/{curry}/reviews", params={"rating": 5})).json()
    assert five["total"] == 1 and five["summary"]["count"] == 2  # summary stays whole


async def test_hidden_or_unknown_dish_reviews_are_a_404(market) -> None:
    order = await completed(market, ("curry", 1))
    await review(market, order, "curry")
    await market.login(CHEF_A)
    await market.client.patch(f"/api/me/dishes/{market.ids['curry']}", json={"active": False})
    market.client.cookies.clear()
    assert_error(
        await market.client.get(f"/api/dishes/{market.ids['curry']}/reviews"), 404, "not_found"
    )
    assert_error(
        await market.client.get(f"/api/dishes/{uuid.uuid4()}/reviews"), 404, "not_found"
    )


async def test_a_kitchen_keeps_reviews_of_hidden_and_deleted_dishes(market) -> None:
    order = await completed(market, ("curry", 1), ("tart", 1))
    await review(market, order, "curry", 4)
    await review(market, order, "tart", 2)
    await market.login(CHEF_A)
    await market.client.patch(f"/api/me/dishes/{market.ids['curry']}", json={"active": False})
    await market.client.delete(f"/api/me/dishes/{market.ids['tart']}")
    market.client.cookies.clear()

    cook_id = order["cook"]["id"]
    page = (await market.client.get(f"/api/cooks/{cook_id}/reviews")).json()
    assert page["total"] == 2 and page["summary"]["average"] == 3.0
    tart = next(i for i in page["items"] if i["dish_name"] == "Custard tart")
    assert tart["dish_id"] is None  # the dish is gone; its name stays

    card = (await market.client.get(f"/api/cooks/{cook_id}")).json()
    assert card["rating"] == {"average": 3.0, "count": 2}
    assert_error(await market.client.get(f"/api/cooks/{uuid.uuid4()}/reviews"), 404, "not_found")


async def test_ratings_ride_along_on_dishes_favourites_and_cooks(market) -> None:
    curry = market.ids["curry"]
    order = await completed(market, ("curry", 1))
    await review(market, order, "curry", 4)
    other = await completed(market, ("curry", 1), buyer=OTHER_BUYER)
    await review(market, other, "curry", 5)

    saved = await market.client.put(f"/api/me/favourites/{curry}")
    assert saved.json()["dish"]["rating"] == {"average": 4.5, "count": 2}
    favourites = (await market.client.get("/api/me/favourites")).json()
    assert favourites["items"][0]["dish"]["rating"] == {"average": 4.5, "count": 2}

    menu = (await market.client.get("/api/dishes")).json()
    ratings = {item["name"]: item["rating"] for item in menu["items"]}
    assert ratings["Veg curry"] == {"average": 4.5, "count": 2}
    assert ratings["Pizza margherita"] == {"average": None, "count": 0}
    detail = (await market.client.get(f"/api/dishes/{curry}")).json()
    assert detail["rating"] == {"average": 4.5, "count": 2}

    cooks = {c["display_name"]: c["rating"] for c in (await market.client.get("/api/cooks")).json()["items"]}
    assert cooks["Chef Ana"] == {"average": 4.5, "count": 2}
    assert cooks["Chef Bruno"] == {"average": None, "count": 0}

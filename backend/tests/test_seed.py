"""scripts/seed.py: idempotency and the acceptance flow it exists for.

The suite's temporary database (``environment`` fixture) is what gets seeded
- the script uses the same session factory the app does, and tests exercise
it in-process via ``seed()`` rather than as a subprocess.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import func, select

from app.core.config import reload_settings
from app.core.db import get_sessionmaker
from app.modules.addresses.models import Address
from app.modules.auth.models import CookProfile, User
from app.modules.auth.security import verify_password
from app.modules.dishes.models import Dish
from app.modules.notifications.models import Notification
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.reviews.models import Review
from app.modules.reviews.service import full_cycle_steps_missing
from app.modules.zones.grid import grid_distance
from app.shared.base import utcnow
from scripts.seed import (
    ADMINS,
    APPLICATIONS,
    CANCEL_REASONS,
    COOKS,
    CUSTOMERS,
    DEMO_CARTS,
    DEMO_FAVOURITES,
    DEMO_OPEN_ORDERS,
    DEMO_ORDERS,
    DEMO_PASSWORDS,
    DEMO_TODAY_ORDERS,
    KITCHENS,
    NOTIFICATION_DAYS,
    OPEN_ORDER_HOURS,
    REJECT_REASONS,
    REVIEWED_AFTER,
    SHOWCASE_COOK,
    SHOWCASE_CUSTOMER,
    SHOWCASE_OPEN_STATUSES,
    SHOWCASE_UNREVIEWED,
    UNREAD_HOURS,
    WORK_ADDRESSES,
    ZONES,
    email_for,
    report,
    seed,
)

TOTAL_DISHES = sum(len(cook.dishes) for cook in COOKS)
INACTIVE_DISHES = sum(1 for cook in COOKS for dish in cook.dishes if not dish.active)

NEW_DISH = {
    "name": "Test verifier's paya",
    "description": "Created straight after seeding, must show up publicly.",
    "price": 640,
    "portions": 4,
    "ingredients": ["lamb trotters", "ginger", "green chilli"],
    "allergens": [],
    "dietary_tags": ["halal"],
}


async def test_seeded_credentials_can_login_and_post_a_dish(client) -> None:
    """The acceptance flow: seed, log in with a printed credential, create a
    dish in the dashboard, see it on the public menu."""
    result = await seed()
    assert result.users_created == len(COOKS) + len(CUSTOMERS) + len(ADMINS) == 16
    assert result.dishes_created == TOTAL_DISHES == 40

    cook = next(account for account in result.accounts if account.kind == "cook")
    login = await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    assert login.status_code == 200, login.text
    assert "cook" in login.json()["roles"]

    created = await client.post("/api/me/dishes", json=NEW_DISH)
    assert created.status_code == 201, created.text

    page = (await client.get("/api/dishes?limit=100")).json()
    # 40 seeded minus the deliberately deactivated ones, plus this new dish.
    assert page["total"] == TOTAL_DISHES - INACTIVE_DISHES + 1
    public = next(dish for dish in page["items"] if dish["id"] == created.json()["id"])
    assert public["name"] == NEW_DISH["name"]
    assert public["cook_name"] == cook.display_name

    # The seeded menu also powers search: q=biryani finds Nadia's dish.
    found = await client.get("/api/dishes", params={"q": "biryani"})
    assert any("biryani" in d["name"].lower() for d in found.json()["items"])


async def test_seed_is_safe_to_rerun(client) -> None:
    first = await seed()
    second = await seed()

    assert second.users_created == 0
    assert second.dishes_created == 0
    assert second.users_existing == len(first.accounts)
    assert second.dishes_existing == TOTAL_DISHES

    # Re-run resets passwords (to the role's demo password) - and those are
    # the ones the operator sees printed, so they must work.
    cook = next(account for account in second.accounts if account.kind == "cook")
    login = await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    assert login.status_code == 200

    page = (await client.get("/api/dishes?limit=100")).json()
    assert page["total"] == TOTAL_DISHES - INACTIVE_DISHES  # nothing duplicated


async def test_rerun_keeps_dashboard_edits(client) -> None:
    """Existing dishes are never overwritten: a deactivation survives seeding."""
    first = await seed()
    cook = next(account for account in first.accounts if account.kind == "cook")
    await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    mine = (await client.get("/api/me/dishes")).json()
    target = mine[0]["id"]
    assert (
        await client.patch(f"/api/me/dishes/{target}", json={"active": False})
    ).status_code == 200

    # A later run regenerates the credential, logs back in, and the dish is
    # still deactivated - the seed left it alone.
    second = await seed()
    same = next(account for account in second.accounts if account.email == cook.email)
    await client.post(
        "/api/auth/login", json={"email": same.email, "password": same.password}
    )
    again = (await client.get("/api/me/dishes")).json()
    deactivated = next(dish for dish in again if dish["id"] == target)
    assert deactivated["active"] is False


# --- zones ------------------------------------------------------------------------


async def test_seed_creates_the_zone_grid_and_places_every_cook(client) -> None:
    result = await seed()
    assert result.zones_created == len(ZONES) == 9

    zones = (await client.get("/api/zones")).json()
    assert [(z["slug"], z["x"], z["y"]) for z in zones] == [
        (slug, x, y) for slug, _name, x, y in ZONES
    ]

    cooks = (await client.get("/api/cooks?limit=100")).json()["items"]
    assert len(cooks) == len(COOKS)
    placed = {cook["display_name"]: cook["zone"]["slug"] for cook in cooks}
    assert placed == {spec.name: spec.zone for spec in COOKS}


async def test_seeded_menu_answers_zone_and_distance_queries(client) -> None:
    await seed()
    zone_of = {spec.name: spec.zone for spec in COOKS}
    cells = {slug: SimpleNamespace(x=x, y=y) for slug, _name, x, y in ZONES}

    same_zone = (await client.get("/api/dishes?zone=market-square&limit=100")).json()
    assert same_zone["total"] > 0
    assert {d["cook_name"] for d in same_zone["items"]} == {
        name for name, slug in zone_of.items() if slug == "market-square"
    }

    near = (
        await client.get("/api/dishes?zone=north-gate&max_distance=1&limit=100")
    ).json()
    assert near["total"] > 0
    for dish in near["items"]:
        kitchen = cells[zone_of[dish["cook_name"]]]
        assert dish["distance"] == grid_distance(cells["north-gate"], kitchen) <= 1


async def test_rerun_keeps_zones_and_a_cooks_own_zone_choice(client) -> None:
    first = await seed()
    cook = next(account for account in first.accounts if account.kind == "cook")
    await client.post(
        "/api/auth/login", json={"email": cook.email, "password": cook.password}
    )
    moved = await client.patch("/api/cooks/me", json={"zone": "harbour"})
    assert moved.status_code == 200

    second = await seed()
    assert second.zones_created == 0
    assert second.zones_existing == len(ZONES)
    same = next(account for account in second.accounts if account.email == cook.email)
    await client.post(
        "/api/auth/login", json={"email": same.email, "password": same.password}
    )
    assert (await client.get("/api/cooks/me")).json()["zone"]["slug"] == "harbour"


# --- admin + dashboard history -----------------------------------------------------


async def test_seed_creates_an_admin_who_reaches_the_admin_dashboard(client) -> None:
    result = await seed()
    admins = [account for account in result.accounts if account.kind == "admin"]
    assert [a.display_name for a in admins] == list(ADMINS)

    login = await client.post(
        "/api/auth/login",
        json={"email": admins[0].email, "password": admins[0].password},
    )
    assert login.json()["roles"] == ["admin"]  # an operator, not a shopper or cook
    dashboard = await client.get("/api/admin/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["users"]["admins"] == 1


async def test_demo_history_is_consistent(client) -> None:
    result = await seed()
    assert result.orders_created == DEMO_ORDERS + DEMO_TODAY_ORDERS + DEMO_OPEN_ORDERS
    assert result.carts_created == len(DEMO_CARTS)

    now = utcnow()
    async with get_sessionmaker()() as session:
        orders = list((await session.scalars(select(Order))).all())
        items = list((await session.scalars(select(OrderItem))).all())
        users = {u.id: u for u in (await session.scalars(select(User))).all()}
        prices = {d.id: d.price for d in (await session.scalars(select(Dish))).all()}
    statuses = {order.status for order in orders}
    assert statuses == {s.value for s in OrderStatus}  # every status is represented

    lines: dict = {}
    for item in items:
        lines.setdefault(item.order_id, []).append(item)
        assert item.unit_price == prices[item.dish_id]  # snapshot = current price
    for order in orders:
        assert order.customer_id != order.cook_id
        assert users[order.cook_id].is_cook
        assert order.created_at >= users[order.customer_id].created_at
        assert order.total == sum(i.line_total for i in lines[order.id])
        assert order.item_count == sum(i.quantity for i in lines[order.id])
        steps = [
            order.created_at,
            order.accepted_at,
            order.ready_at,
            order.completed_at,
        ]
        stamped = [at for at in steps if at is not None]
        assert stamped == sorted(stamped) and max(stamped) <= now
        assert (order.status == "cancelled") == (order.cancelled_at is not None)
        assert order.delivery_address is not None
        assert (
            order.delivery_address["recipient"] == users[order.customer_id].display_name
        )
        if order.status in ("placed", "accepted", "ready"):
            assert now - order.created_at <= timedelta(hours=OPEN_ORDER_HOURS)
        # Only a cook turning an order down gives a reason - a rejection
        # (never accepted) or a cancellation after accepting.
        if order.cancelled_by == "cook":
            reasons = CANCEL_REASONS if order.accepted_at else REJECT_REASONS
            assert order.cancel_reason in reasons
        else:
            assert order.cancel_reason is None


async def test_every_seeded_shopper_has_one_default_address(client) -> None:
    result = await seed()
    shoppers = len(COOKS) + len(CUSTOMERS)
    assert result.addresses_created == shoppers + len(WORK_ADDRESSES)
    async with get_sessionmaker()() as session:
        addresses = list((await session.scalars(select(Address))).all())
    defaults = [a.user_id for a in addresses if a.is_default]
    assert len(defaults) == len(set(defaults)) == shoppers
    assert all(a.zone_id is not None for a in addresses)


async def test_rerun_never_adds_a_second_history(client) -> None:
    first = await seed()
    second = await seed()
    assert second.orders_created == 0 and second.carts_created == 0
    assert second.addresses_created == 0
    assert second.orders_existing == first.orders_created
    async with get_sessionmaker()() as session:
        total = await session.scalar(select(func.count()).select_from(Order))
    assert total == first.orders_created


async def test_demo_favourites_show_an_unavailable_dish(client) -> None:
    """The showcase customer's favourites, through the API: newest first, one
    of them hidden by its cook since (unavailable), and a re-run adds none."""
    result = await seed()
    assert result.favourites_created == sum(len(v) for v in DEMO_FAVOURITES.values())
    account = next(a for a in result.accounts if a.display_name == SHOWCASE_CUSTOMER)
    login = await client.post(
        "/api/auth/login", json={"email": account.email, "password": account.password}
    )
    assert login.status_code == 200, login.text

    page = (await client.get("/api/me/favourites")).json()
    expected = [dish for _cook, dish in DEMO_FAVOURITES[SHOWCASE_CUSTOMER]]
    assert [item["dish"]["name"] for item in page["items"]] == expected
    hidden = [item["dish"]["name"] for item in page["items"] if not item["available"]]
    assert hidden == ["Oden no Mono"] and page["unavailable"] == 1

    again = await seed()
    assert again.favourites_created == 0
    assert (await client.get("/api/me/favourites")).json()["total"] == len(expected)


async def test_demo_reviews_follow_the_review_rules(client) -> None:
    result = await seed()
    assert 0 < result.replies_created < result.reviews_created

    now = utcnow()
    async with get_sessionmaker()() as session:
        reviews = list((await session.scalars(select(Review))).all())
        orders = {o.id: o for o in (await session.scalars(select(Order))).all()}
        lines = {
            (item.order_id, item.dish_id)
            for item in (await session.scalars(select(OrderItem))).all()
        }
    assert len(reviews) == result.reviews_created
    assert len({(r.customer_id, r.dish_id) for r in reviews}) == len(reviews)
    for review in reviews:
        order = orders[review.order_id]
        assert order.customer_id == review.customer_id
        assert order.cook_id == review.cook_id
        assert full_cycle_steps_missing(order) == []
        assert (order.id, review.dish_id) in lines
        assert order.completed_at <= review.created_at <= now
        assert 1 <= review.rating <= 5
        if review.reply is not None:
            assert review.created_at <= review.replied_at <= now

    account = next(a for a in result.accounts if a.display_name == SHOWCASE_CUSTOMER)
    login = await client.post(
        "/api/auth/login", json={"email": account.email, "password": account.password}
    )
    assert login.status_code == 200, login.text
    assert (await client.get("/api/me/reviews")).json()["total"] > 0
    assert (await client.get("/api/me/reviews/pending")).json()["total"] >= SHOWCASE_UNREVIEWED

    again = await seed()
    assert again.reviews_created == 0 and again.replies_created == 0


async def test_recent_demo_reviews_notify_their_cooks(client) -> None:
    await seed()
    now = utcnow()
    async with get_sessionmaker()() as session:
        recent = [
            r
            for r in (await session.scalars(select(Review))).all()
            if r.created_at >= now - timedelta(days=NOTIFICATION_DAYS)
        ]
        notices = list(
            (
                await session.scalars(
                    select(Notification).where(Notification.type.like("review.%"))
                )
            ).all()
        )
    assert recent, "the seed history has reviews in the notification window"
    posted = {n.subject_id: n for n in notices if n.type == "review.posted"}
    replied = {n.subject_id: n for n in notices if n.type == "review.replied"}
    assert set(posted) == {r.id for r in recent}
    assert set(replied) == {r.id for r in recent if r.reply is not None}
    for review in recent:
        notice = posted[review.id]
        assert notice.recipient_id == review.cook_id
        assert notice.created_at == review.created_at
        if review.reply is not None:
            assert notice.read_at is not None  # answered: resolved
            assert replied[review.id].recipient_id == review.customer_id

    await seed()
    async with get_sessionmaker()() as session:
        again = await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type.like("review.%"))
        )
    assert again == len(notices)


async def test_the_showcase_kitchen_fills_every_cook_dashboard_block(client) -> None:
    """Log in as the showcase cook: money today, requests to answer, a
    rejection with a reason, regulars, a private dish and a full checklist."""
    result = await seed()
    account = next(a for a in result.accounts if a.display_name == SHOWCASE_COOK)
    login = await client.post(
        "/api/auth/login", json={"email": account.email, "password": account.password}
    )
    assert login.status_code == 200
    assert account.email == email_for(SHOWCASE_COOK)

    body = (await client.get("/api/cooks/me/dashboard")).json()
    earnings = body["earnings"]
    assert earnings["today"]["orders"] >= DEMO_TODAY_ORDERS
    assert earnings["today"]["value"] > 0
    assert earnings["lifetime"]["orders"] >= 40  # the busiest kitchen by far
    placed = SHOWCASE_OPEN_STATUSES.count(OrderStatus.PLACED)
    assert earnings["awaiting_acceptance"]["orders"] >= placed
    statuses = [order["status"] for order in body["queue"]]
    assert {"placed", "accepted", "ready"} <= set(statuses)
    assert [o["created_at"] for o in body["queue"]] == sorted(
        o["created_at"] for o in body["queue"]
    )  # oldest first
    assert sum(1 for p in body["revenue"] if p["orders"]) >= 10  # a lively month
    assert len(body["top_customers"]) == 5
    assert body["performance"]["rejected"] >= 1
    assert body["menu"]["inactive"] >= 1  # a private dish to publish
    assert body["checklist"]["done"] == body["checklist"]["total"]
    assert body["demand"]["carts"] >= 1

    rejected = (
        await client.get(
            "/api/cooks/me/orders", params={"status": "cancelled", "limit": 100}
        )
    ).json()["items"]
    assert any(
        o["cancelled_by"] == "cook" and o["accepted_at"] is None and o["cancel_reason"]
        for o in rejected
    )
    earnings_page = (await client.get("/api/cooks/me/earnings")).json()
    assert earnings_page["summary"]["earned"] > 0
    assert len(earnings_page["dishes"]) >= 3


async def test_every_open_showcase_order_is_fresh(client) -> None:
    await seed()
    async with get_sessionmaker()() as session:
        cook = await session.scalar(
            select(User).where(User.email == email_for(SHOWCASE_COOK))
        )
        assert cook is not None
        open_orders = list(
            (
                await session.scalars(
                    select(Order).where(
                        Order.cook_id == cook.id,
                        Order.status.in_(["placed", "accepted", "ready"]),
                    )
                )
            ).all()
        )
    assert len(open_orders) >= len(SHOWCASE_OPEN_STATUSES)
    now = utcnow()
    assert all(
        now - order.created_at <= timedelta(hours=OPEN_ORDER_HOURS)
        for order in open_orders
    )


# --- demo logins -------------------------------------------------------------------------

#: The dashboard each role opens (frontend panel -> API).
ROLE_DASHBOARDS = {
    "admin": "/api/admin/dashboard",
    "cook": "/api/cooks/me/dashboard",
    "customer": "/api/me/dashboard",
}


async def test_every_role_logs_in_with_its_demo_password(client) -> None:
    """One known password per role - and it opens that role's dashboard."""
    result = await seed()
    assert not result.random_passwords
    for account in result.accounts:
        assert account.password == DEMO_PASSWORDS[account.kind], account.email
    assert {a.kind for a in result.accounts} == set(DEMO_PASSWORDS)

    starters = {
        "admin": email_for(ADMINS[0]),
        "cook": email_for(SHOWCASE_COOK),
        "customer": email_for(SHOWCASE_CUSTOMER),
    }
    for kind, email in starters.items():
        client.cookies.clear()
        login = await client.post(
            "/api/auth/login", json={"email": email, "password": DEMO_PASSWORDS[kind]}
        )
        assert login.status_code == 200, (kind, login.text)
        assert kind in login.json()["roles"]
        dashboard = await client.get(ROLE_DASHBOARDS[kind])
        assert dashboard.status_code == 200, (kind, dashboard.text)
        # ...and nobody reaches a panel above their role.
        if kind == "customer":
            assert (await client.get(ROLE_DASHBOARDS["cook"])).status_code == 403
        if kind != "admin":
            assert (await client.get(ROLE_DASHBOARDS["admin"])).status_code == 403


async def test_demo_passwords_survive_a_password_change_and_rerun(client) -> None:
    """A re-run puts the documented password back, even after a change."""
    await seed()
    email = email_for(SHOWCASE_COOK)
    await client.post("/api/auth/login", json={"email": email, "password": "plateboard-cook"})
    changed = await client.post(
        "/api/me/password",
        json={"current_password": "plateboard-cook", "new_password": "something-else-1"},
    )
    assert changed.status_code == 200
    await seed()
    client.cookies.clear()
    again = await client.post(
        "/api/auth/login", json={"email": email, "password": "plateboard-cook"}
    )
    assert again.status_code == 200


async def test_random_passwords_on_request(client) -> None:
    result = await seed(random_passwords=True)
    assert result.random_passwords
    passwords = [account.password for account in result.accounts]
    assert not set(passwords) & set(DEMO_PASSWORDS.values())
    assert len(set(passwords)) == len(passwords)  # one per account
    admin = next(a for a in result.accounts if a.kind == "admin")
    login = await client.post(
        "/api/auth/login", json={"email": admin.email, "password": admin.password}
    )
    assert login.status_code == 200


async def test_production_never_gets_known_passwords(client, monkeypatch) -> None:
    """ENVIRONMENT=production forces random passwords, whatever the caller asks."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    reload_settings()
    try:
        result = await seed()
    finally:
        monkeypatch.setenv("ENVIRONMENT", "test")
        reload_settings()
    assert result.random_passwords
    async with get_sessionmaker()() as session:
        users = list((await session.scalars(select(User))).all())
    for user in users:
        for known in DEMO_PASSWORDS.values():
            assert not verify_password(known, user.password_hash), user.email


async def test_the_showcase_customer_has_a_full_account(client) -> None:
    await seed()
    login = await client.post(
        "/api/auth/login",
        json={
            "email": email_for(SHOWCASE_CUSTOMER),
            "password": DEMO_PASSWORDS["customer"],
        },
    )
    assert login.status_code == 200
    body = (await client.get("/api/me/dashboard")).json()
    assert body["orders"]["orders"] >= 10
    assert body["orders"]["open"] >= 1  # something to track
    assert body["cart"]["lines"] >= 1  # the bag nudge
    assert len(body["favourite_cooks"]) >= 2


async def test_report_prints_the_demo_logins(client, capsys) -> None:
    report(await seed(), "sqlite:///demo.db")
    out = capsys.readouterr().out
    assert "plateboard-admin     /admin    morgan.ellis@example.com" in out
    assert f"plateboard-cook      /cook     {email_for(SHOWCASE_COOK)}" in out
    assert f"plateboard-customer  /account  {email_for(SHOWCASE_CUSTOMER)}" in out

    report(await seed(random_passwords=True), "sqlite:///demo.db")
    assert "Random passwords" in capsys.readouterr().out


# --- kitchens: verification + hours -------------------------------------------------------


async def test_kitchens_show_every_badge_and_availability_state(client) -> None:
    await seed()
    cooks = {c["display_name"]: c for c in (await client.get("/api/cooks?limit=50")).json()["items"]}
    assert set(cooks) == set(KITCHENS)
    for name, (preset, verified, paused) in KITCHENS.items():
        card = cooks[name]
        assert card["verified"] is verified, name
        if paused:
            assert card["availability"]["status"] == "paused", name
        elif preset == "anytime":
            assert card["availability"]["status"] == "anytime", name
        else:
            assert card["availability"]["status"] in ("open", "closed"), name
    assert {c["verified"] for c in cooks.values()} == {True, False}  # both shown
    # There is always somewhere to order from, whatever the hour of the demo.
    assert any(c["availability"]["accepting_orders"] for c in cooks.values())
    showcase = cooks[SHOWCASE_COOK]
    assert showcase["verified"] is True


async def test_a_kitchen_opened_when_its_cook_joined(client) -> None:
    """ "Cooking since" on the public page is the join date, not the seed run."""
    await seed()
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(User, CookProfile)
                .join(CookProfile, CookProfile.user_id == User.id)
                .where(CookProfile.status == "accepted")  # kitchens, not applications
            )
        ).all()
    assert len(rows) == len(COOKS)
    for user, profile in rows:
        assert profile.created_at == user.created_at, user.email
        # Applied when they joined, accepted by the admin a day later.
        assert profile.submitted_at == user.created_at
        assert profile.reviewed_at == user.created_at + REVIEWED_AFTER
        assert profile.reviewed_by_id is not None
        if profile.verified_at is not None:
            assert profile.verified_at > profile.created_at
            assert profile.verified_by_id is not None


async def test_rerun_keeps_kitchen_settings_made_in_the_ui(client) -> None:
    await seed()
    login = await client.post(
        "/api/auth/login",
        json={"email": email_for(SHOWCASE_COOK), "password": DEMO_PASSWORDS["cook"]},
    )
    assert login.status_code == 200
    await client.put(
        "/api/cooks/me/availability", json={"timezone": "Asia/Dhaka", "orders_paused": True}
    )
    await seed()
    body = (await client.get("/api/cooks/me/availability")).json()
    assert (body["timezone"], body["orders_paused"], body["hours"]) == ("Asia/Dhaka", True, [])


# --- cook applications + notifications --------------------------------------------------


async def login_as(client, name: str) -> None:
    client.cookies.clear()
    role = "admin" if name in ADMINS else "cook" if name in KITCHENS else "customer"
    response = await client.post(
        "/api/auth/login",
        json={"email": email_for(name), "password": DEMO_PASSWORDS[role]},
    )
    assert response.status_code == 200, response.text


async def test_seed_files_a_pending_and_a_rejected_application(client) -> None:
    result = await seed()
    assert result.applications_created == len(APPLICATIONS) == 2
    pending, rejected = APPLICATIONS

    await login_as(client, ADMINS[0])
    queue = (await client.get("/api/admin/cook-applications")).json()
    assert [item["display_name"] for item in queue["items"]] == [pending.name]
    decided = (
        await client.get("/api/admin/cook-applications", params={"status": "rejected"})
    ).json()["items"]
    assert [(i["display_name"], i["rejection_reason"]) for i in decided] == [
        (rejected.name, rejected.reason)
    ]
    assert (await client.get("/api/admin/dashboard")).json()["users"][
        "pending_cook_applications"
    ] == 1
    # Applications are not kitchens: the public directory is the 10 cooks.
    assert (await client.get("/api/cooks")).json()["total"] == len(COOKS)

    await login_as(client, pending.name)
    mine = (await client.get("/api/cooks/me/application")).json()
    assert (mine["status"], mine["headline"]) == ("pending", pending.headline)
    assert (await client.get("/api/cooks/me")).status_code == 403

    # A re-run leaves applications alone (even one decided in the UI).
    again = await seed()
    assert again.applications_created == 0


async def test_seeded_inboxes_fill_every_panel(client) -> None:
    result = await seed()
    assert result.notifications_created > 0
    pending, rejected = APPLICATIONS

    # Admin: the pending application is unread, the decided one is not.
    await login_as(client, ADMINS[0])
    admin_inbox = (await client.get("/api/me/notifications", params={"audience": "admin"})).json()
    submitted = [i for i in admin_inbox["items"] if i["type"] == "cook_application.submitted"]
    assert {i["data"]["applicant_name"]: i["read"] for i in submitted} == {
        pending.name: False,
        rejected.name: True,
    }

    # The rejected applicant hears why.
    await login_as(client, rejected.name)
    items = (await client.get("/api/me/notifications")).json()["items"]
    answer = next(i for i in items if i["type"] == "cook_application.rejected")
    assert rejected.reason and rejected.reason in answer["body"]

    # The showcase kitchen: one unread "new request" per order still waiting
    # for an answer; answered requests are read.
    await login_as(client, SHOWCASE_COOK)
    requests = (
        await client.get(
            "/api/me/notifications",
            params={"audience": "cook", "limit": 100},
        )
    ).json()["items"]
    placed_notes = {i["subject"]["id"]: i["read"] for i in requests if i["type"] == "order.placed"}
    waiting = (
        await client.get("/api/cooks/me/orders", params={"status": "placed", "limit": 100})
    ).json()["items"]
    assert waiting and all(placed_notes[order["id"]] is False for order in waiting)
    assert any(i["type"] == "kitchen.verified" for i in requests)
    answered = [i for i in requests if i["type"] == "order.placed" and i["read"]]
    assert answered  # accepted / rejected requests were resolved

    # Only the last UNREAD_HOURS stay unread.
    cutoff = (utcnow() - timedelta(hours=UNREAD_HOURS)).isoformat()
    assert all(i["read"] for i in requests if i["created_at"][:26] < cutoff[:26])


async def test_seeded_notifications_follow_the_orders(client) -> None:
    """Every recent order has its steps in both inboxes - the same rules as
    live orders (one confirmation + one request per order, a "ready" for
    every ready order, a "received" for every completed one)."""
    await seed()
    async with get_sessionmaker()() as session:
        recent = (
            await session.scalars(
                select(Order).where(Order.created_at >= utcnow() - timedelta(days=7))
            )
        ).all()
        rows = (await session.scalars(select(Notification))).all()
    by_key = {(row.recipient_id, row.dedupe_key) for row in rows}
    assert recent
    for order in recent:
        assert (order.customer_id, f"order:{order.id}:order.placed") in by_key
        assert (order.cook_id, f"order:{order.id}:order.placed") in by_key
        if order.ready_at:
            assert (order.customer_id, f"order:{order.id}:order.ready") in by_key
        if order.completed_at:
            assert (order.cook_id, f"order:{order.id}:order.received") in by_key


async def test_rerun_never_duplicates_notifications(client) -> None:
    await seed()
    async with get_sessionmaker()() as session:
        before = await session.scalar(select(func.count()).select_from(Notification))
    again = await seed()
    async with get_sessionmaker()() as session:
        after = await session.scalar(select(func.count()).select_from(Notification))
    assert again.notifications_created == 0
    assert after == before

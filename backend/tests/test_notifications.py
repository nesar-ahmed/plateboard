"""In-app notifications: the catalog, writing (``service.notify``) and the
inbox API (``/api/me/notifications``).

Rules under test:

* writing: payloads, audiences and subjects must match the catalog; rows join
  the caller's transaction (no commit of their own - a rollback takes them
  away); a ``dedupe_key`` is stored once per recipient; admin fan-out skips
  the acting admin;
* reading: login required; ``account`` is everyone's inbox, ``cook`` and
  ``admin`` need the role (403 when asked for explicitly, hidden otherwise);
  newest first with paging, an ``unread`` filter and per-panel unread counts;
* changing: mark read (first read time kept) / unread, mark all read (per
  panel, up to ``before``), dismiss; someone else's id is a 404;
* rendering: every catalog entry renders for every audience it allows;
  retired types and outdated snapshots fall back instead of failing;
* the database: unknown audience / half a subject are refused; deleting the
  recipient deletes their notifications, deleting the actor keeps them.
"""

from __future__ import annotations

import uuid
from typing import Any, get_args

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.db import get_sessionmaker
from app.modules.auth.models import ROLE_ADMIN, ROLE_COOK, User
from app.modules.auth.security import hash_password
from app.modules.notifications import service
from app.modules.notifications.catalog import (
    CATALOG,
    FALLBACK,
    AccountPayload,
    CookApplicationPayload,
    Fulfilment,
    NoPayload,
    NotificationPayload,
    NotificationType,
    OrderPayload,
    PasswordChangedPayload,
    ReviewPayload,
    order_ref,
    render,
)
from app.modules.notifications.models import Audience, Notification
from app.modules.orders.models import FULFILMENT_VALUES
from tests.conftest import DEFAULT_PASSWORD

NOTIFICATIONS = "/api/me/notifications"
UNREAD = f"{NOTIFICATIONS}/unread-count"
READ_ALL = f"{NOTIFICATIONS}/read-all"

ORDER_ID = uuid.UUID("0ca946f8-1111-4222-8333-444455556666")


def order_payload(**changes: Any) -> OrderPayload:
    values: dict[str, Any] = {
        "cook_name": "Chef Ana",
        "customer_name": "Bea Buyer",
        "item_count": 2,
        "total": 1600,
    }
    return OrderPayload(**{**values, **changes})


async def clear_inbox() -> None:
    """Drop every notification - registration writes a real welcome, and
    these tests want to count only what they write themselves."""
    async with get_sessionmaker()() as session:
        await session.execute(delete(Notification))
        await session.commit()


async def fresh_customer(accounts, email: str = "user@example.com") -> uuid.UUID:
    """Register + sign in, start from an empty inbox; returns the user id."""
    await accounts.customer(email)
    await clear_inbox()
    return await me(accounts.client)


async def me(client) -> uuid.UUID:
    response = await client.get("/api/me")
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


async def write(
    recipient_id: uuid.UUID,
    *,
    audience: Audience = Audience.ACCOUNT,
    kind: NotificationType = NotificationType.ACCOUNT_WELCOME,
    payload: NotificationPayload | None = None,
    subject_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> uuid.UUID | None:
    """``service.notify`` in its own committed unit of work."""
    async with get_sessionmaker()() as session:
        created = await service.notify(
            session,
            recipient_id=recipient_id,
            audience=audience,
            kind=kind,
            payload=payload if payload is not None else AccountPayload(name="Bea"),
            subject_id=subject_id,
            actor_id=actor_id,
            dedupe_key=dedupe_key,
        )
        await session.commit()
    return created


async def write_order(
    recipient_id: uuid.UUID,
    kind: NotificationType = NotificationType.ORDER_PLACED,
    audience: Audience = Audience.ACCOUNT,
    **changes: Any,
) -> uuid.UUID | None:
    return await write(
        recipient_id,
        audience=audience,
        kind=kind,
        payload=order_payload(**changes),
        subject_id=ORDER_ID,
    )


async def inbox(client, **params: Any) -> dict:
    response = await client.get(NOTIFICATIONS, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def counts(client) -> dict:
    response = await client.get(UNREAD)
    assert response.status_code == 200, response.text
    return response.json()


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


# --- access ---------------------------------------------------------------------------


async def test_inbox_requires_login(client) -> None:
    some_id = uuid.uuid4()
    for response in (
        await client.get(NOTIFICATIONS),
        await client.get(UNREAD),
        await client.post(READ_ALL),
        await client.patch(f"{NOTIFICATIONS}/{some_id}", json={"read": True}),
        await client.delete(f"{NOTIFICATIONS}/{some_id}"),
    ):
        assert_error(response, 401, "unauthenticated")


async def test_a_new_account_is_welcomed(accounts) -> None:
    await accounts.customer()
    page = await inbox(accounts.client)
    assert [item["type"] for item in page["items"]] == ["account.welcome"]
    assert page["items"][0]["title"] == "Welcome to Plateboard!"
    assert page["items"][0]["actor_id"] == str(await me(accounts.client))


async def test_an_empty_inbox(accounts) -> None:
    await fresh_customer(accounts)
    assert await inbox(accounts.client) == {
        "items": [],
        "total": 0,
        "unread": 0,
        "limit": 20,
        "offset": 0,
    }
    assert await counts(accounts.client) == {
        "total": 0,
        "account": 0,
        "cook": 0,
        "admin": 0,
    }


# --- the inbox ------------------------------------------------------------------------


async def test_a_written_notification_is_listed_and_rendered(accounts) -> None:
    user_id = await fresh_customer(accounts)
    created = await write_order(user_id)

    page = await inbox(accounts.client)
    assert (page["total"], page["unread"]) == (1, 1)
    item = page["items"][0]
    assert item["id"] == str(created)
    assert item["type"] == "order.placed"
    assert item["audience"] == "account"
    assert item["title"] == "Order #0CA946F8 placed with Chef Ana"
    assert item["body"] == "2 portions - waiting for the cook to accept it."
    assert item["subject"] == {"kind": "order", "id": str(ORDER_ID)}
    assert item["actor_id"] is None
    assert item["data"] == {
        "cook_name": "Chef Ana",
        "customer_name": "Bea Buyer",
        "item_count": 2,
        "total": 1600,
        "fulfilment": "pickup",
        "reason": None,
    }
    assert (item["read"], item["read_at"]) == (False, None)
    assert item["created_at"].endswith(("Z", "+00:00"))
    assert (await counts(accounts.client))["account"] == 1


async def test_newest_first_with_paging_and_an_unread_filter(accounts) -> None:
    user_id = await fresh_customer(accounts)
    ids = [await write(user_id, payload=AccountPayload(name=f"n{i}")) for i in range(3)]

    first = await inbox(accounts.client, limit=2)
    assert [item["id"] for item in first["items"]] == [str(ids[2]), str(ids[1])]
    assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)
    rest = await inbox(accounts.client, limit=2, offset=2)
    assert [item["id"] for item in rest["items"]] == [str(ids[0])]

    patched = await accounts.client.patch(
        f"{NOTIFICATIONS}/{ids[1]}", json={"read": True}
    )
    assert patched.status_code == 200, patched.text
    unread = await inbox(accounts.client, unread="true")
    assert [item["id"] for item in unread["items"]] == [str(ids[2]), str(ids[0])]
    # ``unread`` counts the inbox, not the filtered page.
    assert (unread["total"], unread["unread"]) == (2, 2)
    assert (await inbox(accounts.client))["total"] == 3


async def test_inboxes_follow_the_roles(accounts) -> None:
    """``account`` is everyone's; ``cook``/``admin`` rows stay hidden (and
    403 when asked for) until the account holds the role."""
    client = accounts.client
    user_id = await fresh_customer(accounts)
    await write(user_id)
    cook_row = await write(
        user_id,
        audience=Audience.COOK,
        kind=NotificationType.KITCHEN_VERIFIED,
        payload=NoPayload(),
        subject_id=user_id,
    )
    await write(
        user_id,
        audience=Audience.ADMIN,
        kind=NotificationType.COOK_APPLICATION_SUBMITTED,
        payload=CookApplicationPayload(applicant_name="Chef Ana"),
        subject_id=uuid.uuid4(),
    )

    page = await inbox(client)
    assert [item["audience"] for item in page["items"]] == ["account"]
    assert await counts(client) == {"total": 1, "account": 1, "cook": 0, "admin": 0}
    assert_error(
        await client.get(NOTIFICATIONS, params={"audience": "cook"}), 403, "forbidden"
    )
    assert_error(
        await client.get(NOTIFICATIONS, params={"audience": "admin"}), 403, "forbidden"
    )
    assert_error(
        await client.post(READ_ALL, json={"audience": "cook"}), 403, "forbidden"
    )
    assert_error(
        await client.patch(f"{NOTIFICATIONS}/{cook_row}", json={"read": True}),
        404,
        "not_found",
    )

    await accounts.grant_role("user@example.com", ROLE_COOK)
    assert await counts(client) == {"total": 2, "account": 1, "cook": 1, "admin": 0}
    kitchen = await inbox(client, audience="cook")
    assert [item["type"] for item in kitchen["items"]] == ["kitchen.verified"]
    assert kitchen["items"][0]["subject"] == {"kind": "kitchen", "id": str(user_id)}

    await accounts.grant_role("user@example.com", ROLE_ADMIN)
    assert (await counts(client))["total"] == 3
    assert (await inbox(client))["total"] == 3
    admin = await inbox(client, audience="admin")
    assert admin["items"][0]["title"] == "New cook application"


async def test_one_event_reads_differently_per_panel(accounts) -> None:
    """A cook who also orders: ``order.placed`` is a confirmation in
    /account and a new request in /cook - separate inboxes."""
    await accounts.cook()
    await clear_inbox()
    user_id = await me(accounts.client)
    await write_order(user_id, audience=Audience.ACCOUNT)
    await write_order(user_id, audience=Audience.COOK)

    account = await inbox(accounts.client, audience="account")
    cook = await inbox(accounts.client, audience="cook")
    assert [item["title"] for item in account["items"]] == [
        "Order #0CA946F8 placed with Chef Ana"
    ]
    assert [item["title"] for item in cook["items"]] == [
        "New order request from Bea Buyer"
    ]
    assert (await inbox(accounts.client))["total"] == 2


# --- changing the inbox -------------------------------------------------------------


async def test_mark_read_keeps_the_first_read_time_and_can_undo(accounts) -> None:
    created = await write(await fresh_customer(accounts))
    url = f"{NOTIFICATIONS}/{created}"

    first = (await accounts.client.patch(url, json={"read": True})).json()
    assert first["read"] is True and first["read_at"] is not None
    again = (await accounts.client.patch(url, json={"read": True})).json()
    assert again["read_at"] == first["read_at"]
    assert (await counts(accounts.client))["total"] == 0

    undone = (await accounts.client.patch(url, json={"read": False})).json()
    assert (undone["read"], undone["read_at"]) == (False, None)
    assert (await counts(accounts.client))["total"] == 1

    assert_error(await accounts.client.patch(url, json={}), 422, "validation_failed")


async def test_someone_elses_notification_is_a_404(accounts, make_client) -> None:
    await accounts.customer()
    other = make_client()
    await other.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": DEFAULT_PASSWORD},
    )
    await other.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": DEFAULT_PASSWORD},
    )
    await clear_inbox()  # both welcomes
    mine = await write(await me(accounts.client))
    for response in (
        await other.patch(f"{NOTIFICATIONS}/{mine}", json={"read": True}),
        await other.delete(f"{NOTIFICATIONS}/{mine}"),
        await other.patch(f"{NOTIFICATIONS}/{uuid.uuid4()}", json={"read": True}),
    ):
        assert_error(response, 404, "not_found")
    assert (await inbox(other))["total"] == 0
    assert (await inbox(accounts.client))["items"][0]["read"] is False


async def test_read_all_per_panel_and_up_to_before(accounts) -> None:
    client = accounts.client
    await accounts.cook()
    await clear_inbox()
    user_id = await me(client)
    await write(user_id)
    await write_order(user_id, audience=Audience.ACCOUNT)
    await write_order(user_id, audience=Audience.COOK)

    marked = await client.post(READ_ALL, json={"audience": "account"})
    assert marked.status_code == 200, marked.text
    assert marked.json() == {"marked": 2}
    assert await counts(client) == {"total": 1, "account": 0, "cook": 1, "admin": 0}

    # No body: every visible inbox.
    assert (await client.post(READ_ALL)).json() == {"marked": 1}
    assert (await client.post(READ_ALL)).json() == {"marked": 0}

    # ``before``: what arrived after the user looked stays unread.
    seen = await write(user_id, payload=AccountPayload(name="seen"))
    seen_at = (await inbox(client, limit=1))["items"][0]["created_at"]
    later = await write(user_id, payload=AccountPayload(name="later"))
    assert (await client.post(READ_ALL, json={"before": seen_at})).json() == {
        "marked": 1
    }
    unread = await inbox(client, unread="true")
    assert [item["id"] for item in unread["items"]] == [str(later)]
    assert seen is not None


async def test_dismiss(accounts) -> None:
    created = await write(await fresh_customer(accounts))
    url = f"{NOTIFICATIONS}/{created}"
    assert (await accounts.client.delete(url)).status_code == 204
    assert (await inbox(accounts.client))["total"] == 0
    assert_error(await accounts.client.delete(url), 404, "not_found")


# --- writing --------------------------------------------------------------------------


async def test_a_dedupe_key_is_stored_once_per_recipient(accounts) -> None:
    user_id = await fresh_customer(accounts)
    key = f"order:{ORDER_ID}:placed"
    first = await write(user_id, dedupe_key=key)
    assert first is not None
    assert await write(user_id, dedupe_key=key) is None  # a duplicate, not an error

    async with get_sessionmaker()() as session:
        other = User(email="second@example.com", password_hash=hash_password("x" * 12))
        session.add(other)
        await session.commit()
        other_id = other.id
    assert await write(other_id, dedupe_key=key) is not None  # per recipient

    # No key, no deduplication.
    await write(user_id)
    await write(user_id)
    assert (await inbox(accounts.client))["total"] == 3


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"audience": Audience.COOK}, "goes to account, not cook"),
        ({"payload": NoPayload()}, "needs AccountPayload, got NoPayload"),
        ({"subject_id": ORDER_ID}, "has no subject"),
        (
            {
                "kind": NotificationType.ORDER_ACCEPTED,
                "payload": order_payload(),
                "subject_id": None,
            },
            "needs a subject_id: the order",
        ),
    ],
)
async def test_notify_enforces_the_catalog(
    environment, changes: dict[str, Any], message: str
) -> None:
    arguments: dict[str, Any] = {
        "recipient_id": uuid.uuid4(),
        "audience": Audience.ACCOUNT,
        "kind": NotificationType.ACCOUNT_WELCOME,
        "payload": AccountPayload(),
        "subject_id": None,
        **changes,
    }
    async with get_sessionmaker()() as session:
        with pytest.raises(service.InvalidNotificationError, match=message):
            await service.notify(session, **arguments)


async def test_notify_joins_the_callers_transaction(accounts) -> None:
    """No commit of its own: a rollback takes the notification away, and a
    recipient added in the same unit of work is flushed first."""
    user_id = await fresh_customer(accounts)
    async with get_sessionmaker()() as session:
        await service.notify(
            session,
            recipient_id=user_id,
            audience=Audience.ACCOUNT,
            kind=NotificationType.ACCOUNT_WELCOME,
            payload=AccountPayload(),
        )
        await session.rollback()
    assert (await inbox(accounts.client))["total"] == 0

    async with get_sessionmaker()() as session:
        newcomer = User(
            id=uuid.uuid4(),
            email="new@example.com",
            password_hash=hash_password("x" * 12),
        )
        session.add(newcomer)  # pending - notify() flushes it before inserting
        created = await service.notify(
            session,
            recipient_id=newcomer.id,
            audience=Audience.ACCOUNT,
            kind=NotificationType.ACCOUNT_WELCOME,
            payload=AccountPayload(name="Newcomer"),
        )
        await session.commit()
        row = await session.get(Notification, created)
        assert row is not None and row.recipient_id == newcomer.id


async def test_notify_admins_fans_out_and_skips_the_actor(accounts) -> None:
    for email in ("admin-1@example.com", "admin-2@example.com"):
        await accounts.register(email)
        await accounts.grant_role(email, ROLE_ADMIN)
    await accounts.register("customer@example.com")
    await clear_inbox()
    async with get_sessionmaker()() as session:
        ids = {
            user.email: user.id for user in (await session.scalars(select(User))).all()
        }
        written = await service.notify_admins(
            session,
            kind=NotificationType.COOK_APPLICATION_SUBMITTED,
            payload=CookApplicationPayload(applicant_name="Chef Ana", headline="Soups"),
            subject_id=ids["customer@example.com"],
            actor_id=ids["admin-1@example.com"],
        )
        await session.commit()
        rows = (await session.scalars(select(Notification))).all()
    assert len(written) == 1
    assert [(row.recipient_id, row.audience) for row in rows] == [
        (ids["admin-2@example.com"], "admin")
    ]

    await accounts.login("admin-2@example.com")
    item = (await inbox(accounts.client, audience="admin"))["items"][0]
    assert item["title"] == "New cook application"
    assert item["body"] == (
        'Chef Ana wants to open a kitchen: "Soups". Review it to accept or reject.'
    )
    assert item["actor_id"] == str(ids["admin-1@example.com"])

    async with get_sessionmaker()() as session:
        with pytest.raises(service.InvalidNotificationError):
            await service.notify_admins(  # not an admin-audience type
                session,
                kind=NotificationType.ORDER_ACCEPTED,
                payload=order_payload(),
                subject_id=ORDER_ID,
            )


# --- rendering ----------------------------------------------------------------------

SAMPLES: dict[type[NotificationPayload], NotificationPayload] = {
    NoPayload: NoPayload(),
    AccountPayload: AccountPayload(name="Sam"),
    PasswordChangedPayload: PasswordChangedPayload(signed_out_sessions=2),
    CookApplicationPayload: CookApplicationPayload(
        applicant_name="Chef Ana", headline="Soups", reason="Missing details"
    ),
    OrderPayload: order_payload(reason="Sold out"),
    ReviewPayload: ReviewPayload(
        dish_name="Veg curry", rating=4, customer_name="Bea Buyer", cook_name="Chef Ana"
    ),
}


def test_every_type_is_in_the_catalog() -> None:
    assert set(CATALOG) == set(NotificationType)
    for spec in CATALOG.values():
        assert spec.audiences, spec
        assert spec.payload in SAMPLES, spec.payload


@pytest.mark.parametrize(
    ("kind", "audience"),
    [
        (kind, audience)
        for kind, spec in CATALOG.items()
        for audience in sorted(spec.audiences, key=lambda a: a.value)  # stable ids
    ],
    ids=lambda value: value.value,
)
def test_every_catalog_entry_renders(
    kind: NotificationType, audience: Audience
) -> None:
    spec = CATALOG[kind]
    subject = ORDER_ID if spec.subject is not None else None
    data = SAMPLES[spec.payload].model_dump(mode="json")
    rendered = render(kind.value, audience.value, subject, data)
    assert rendered != FALLBACK
    assert rendered.title and rendered.body


def _render(kind: NotificationType, audience: Audience, payload: NotificationPayload):
    subject = ORDER_ID if CATALOG[kind].subject is not None else None
    return render(kind.value, audience.value, subject, payload.model_dump(mode="json"))


def test_rendering_details() -> None:
    account, cook, admin = Audience.ACCOUNT, Audience.COOK, Audience.ADMIN
    assert order_ref(ORDER_ID) == "#0CA946F8"  # same as the frontend's orderRef

    rejected = _render(NotificationType.ORDER_REJECTED, account, order_payload())
    assert rejected.title == "Chef Ana couldn't take your order"
    assert rejected.body == "Order #0CA946F8 was declined."
    with_reason = _render(
        NotificationType.ORDER_REJECTED, account, order_payload(reason="Sold out")
    )
    assert with_reason.body == 'Order #0CA946F8 was declined. Reason: "Sold out"'

    pickup = _render(NotificationType.ORDER_READY, account, order_payload())
    assert pickup.title == "Your order is ready for pickup"
    delivery = _render(
        NotificationType.ORDER_READY, account, order_payload(fulfilment="delivery")
    )
    assert delivery.title == "Your order is on its way"

    nameless = order_payload(cook_name=None, customer_name=None)
    assert _render(NotificationType.ORDER_ACCEPTED, account, nameless).title == (
        "Your cook accepted your order"
    )
    assert _render(NotificationType.ORDER_RECEIVED, cook, nameless).title == (
        "A customer received their order"
    )
    assert _render(
        NotificationType.ORDER_CANCELLED_BY_COOK, admin, order_payload()
    ).title == ("Chef Ana cancelled an accepted order")
    assert _render(
        NotificationType.ORDER_PLACED, account, order_payload(item_count=1)
    ).body == ("1 portion - waiting for the cook to accept it.")

    assert _render(
        NotificationType.ACCOUNT_WELCOME, account, AccountPayload()
    ).title == ("Welcome to Plateboard!")
    one = _render(
        NotificationType.ACCOUNT_PASSWORD_CHANGED,
        account,
        PasswordChangedPayload(signed_out_sessions=1),
    )
    assert (
        one.body
        == "If this wasn't you, change it again now. 1 other session was signed out."
    )
    none = _render(
        NotificationType.ACCOUNT_PASSWORD_CHANGED, account, PasswordChangedPayload()
    )
    assert none.body == "If this wasn't you, change it again now."

    no_reason = _render(
        NotificationType.COOK_APPLICATION_REJECTED, account, CookApplicationPayload()
    )
    assert no_reason.body and "Reason" not in no_reason.body


def test_the_fulfilment_vocabulary_matches_the_orders() -> None:
    """The catalog keeps its own copy of the modes (``notifications`` must not
    import ``orders`` - see the package docstring); this keeps them equal."""
    assert set(get_args(Fulfilment)) == set(FULFILMENT_VALUES)


def test_payloads_refuse_unknown_fields() -> None:
    with pytest.raises(ValueError, match="extra"):
        OrderPayload(item_count=1, total=100, surprise=True)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="fulfilment"):
        order_payload(fulfilment="drone")


async def test_unrenderable_rows_fall_back(accounts) -> None:
    """A retired type / subject kind or an outdated snapshot still lists."""
    user_id = await fresh_customer(accounts)
    async with get_sessionmaker()() as session:
        session.add_all(
            [
                Notification(
                    recipient_id=user_id,
                    audience="account",
                    type="retired.type",
                    subject_kind="gone",
                    subject_id=uuid.uuid4(),
                    data={},
                ),
                Notification(
                    recipient_id=user_id,
                    audience="account",
                    type="order.accepted",
                    subject_kind="order",
                    subject_id=ORDER_ID,
                    data={"total": "not a number"},
                ),
            ]
        )
        await session.commit()
    items = (await inbox(accounts.client))["items"]
    assert {(item["title"], item["body"]) for item in items} == {("Notification", None)}
    assert {item["type"] for item in items} == {"retired.type", "order.accepted"}
    subjects = {item["type"]: item["subject"] for item in items}
    assert subjects["retired.type"] is None
    assert subjects["order.accepted"] == {"kind": "order", "id": str(ORDER_ID)}


# --- database rules -------------------------------------------------------------------


@pytest.mark.parametrize(
    "columns",
    [
        {"audience": "everyone"},
        {"subject_kind": "order"},  # without subject_id
        {"subject_id": ORDER_ID},  # without subject_kind
    ],
)
async def test_the_database_refuses_broken_rows(
    accounts, columns: dict[str, Any]
) -> None:
    user_id = await fresh_customer(accounts)
    values: dict[str, Any] = {
        "recipient_id": user_id,
        "audience": "account",
        "type": "account.welcome",
        "data": {},
        **columns,
    }
    async with get_sessionmaker()() as session:
        session.add(Notification(**values))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_deleting_accounts(accounts) -> None:
    """The recipient's inbox goes with the account; an actor's deletion
    keeps the notification (``actor_id`` becomes null)."""
    user_id = await fresh_customer(accounts)
    async with get_sessionmaker()() as session:
        actor = User(email="actor@example.com", password_hash=hash_password("x" * 12))
        session.add(actor)
        await session.commit()
        actor_id = actor.id
    await write(user_id, actor_id=actor_id)
    await write(actor_id)

    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.id == actor_id))
        await session.commit()
        rows = (await session.scalars(select(Notification))).all()
    assert [(row.recipient_id, row.actor_id) for row in rows] == [(user_id, None)]

    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()
        assert (await session.scalars(select(Notification))).all() == []

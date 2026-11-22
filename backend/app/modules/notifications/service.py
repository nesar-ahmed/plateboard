"""Notification business logic: writing (for other modules) and the inbox.

**Writing** - :func:`notify` / :func:`notify_admins` are what feature
services call when something happens. They only *add* rows to the caller's
session and never commit: the caller calls them just before its own
``commit()``, so a notification exists if and only if the change it reports
was committed. A rolled-back order (``cart_changed``), a lost
compare-and-set (``invalid_status_transition``) or any later error takes its
notifications with it. Rules for callers:

* notify only on a *real* state change (idempotent endpoints such as
  verifying an already verified kitchen must not notify again);
* do not notify people about their own actions, except where a record on
  their other devices helps (the order confirmation, security events) -
  :func:`notify_admins` skips the acting admin by itself;
* pass a ``dedupe_key`` for events that could be written twice (retries,
  scheduled reminders): the same key for the same recipient is stored once,
  *whatever the type or audience* - so a key must name the event, e.g.
  ``order:{order_id}:ready``. Events that may legitimately repeat
  (verified -> revoked -> verified) must not share a key.

Payloads are validated against the catalog (``catalog.CATALOG``); a wrong
audience, payload model or missing subject raises
:class:`InvalidNotificationError` - a programming error, surfaced as a 500
and by the tests, never a silently odd inbox.

**Reading** - every signed-in user has the ``account`` inbox; ``cook`` and
``admin`` need those roles. Rows in an inbox the caller cannot see (a cook
role that was taken away) are hidden - listed nowhere, 404 by id - but kept.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, Insert, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.auth.exceptions import ForbiddenError
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.notifications.catalog import (
    CATALOG,
    NotificationPayload,
    NotificationType,
)
from app.modules.notifications.models import Audience, Notification
from app.shared.base import utcnow
from app.shared.sql import json_array_contains

__all__ = [
    "InvalidNotificationError",
    "NotificationNotFoundError",
    "delete_notification",
    "get_visible",
    "mark_all_read",
    "notify",
    "notify_admins",
    "page_notifications",
    "resolve",
    "resolve_audiences",
    "set_read",
    "unread_counts",
    "visible_audiences",
]


class InvalidNotificationError(ValueError):
    """A caller broke the catalog's contract (audience, payload, subject)."""


class NotificationNotFoundError(NotFoundError):
    """Unknown id, someone else's notification, or an inbox the caller can no
    longer see - the same 404 for all three."""

    default_message = "Notification not found"


# --- writing ---------------------------------------------------------------------------


def _insert(session: AsyncSession) -> Insert:
    """``INSERT ... ON CONFLICT (recipient_id, dedupe_key) DO NOTHING``.

    A conflict is a duplicate event, not an error, and must never break the
    caller's transaction - hence the native upsert clause rather than
    catching ``IntegrityError`` (which would poison the session). SQLite and
    PostgreSQL spell it the same way in SQLAlchemy.
    """
    dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
    return dialect.insert(Notification).on_conflict_do_nothing(
        index_elements=[Notification.recipient_id, Notification.dedupe_key]
    )


def _check(
    kind: NotificationType,
    audience: Audience,
    payload: NotificationPayload,
    subject_id: uuid.UUID | None,
) -> None:
    spec = CATALOG[kind]
    if audience not in spec.audiences:
        allowed = ", ".join(sorted(a.value for a in spec.audiences))
        msg = f"{kind.value} goes to {allowed}, not {audience.value}"
        raise InvalidNotificationError(msg)
    if type(payload) is not spec.payload:
        msg = (
            f"{kind.value} needs {spec.payload.__name__}, got {type(payload).__name__}"
        )
        raise InvalidNotificationError(msg)
    if (spec.subject is None) != (subject_id is None):
        msg = (
            f"{kind.value} needs a subject_id: the {spec.subject.value}"
            if spec.subject is not None
            else f"{kind.value} has no subject: subject_id must be None"
        )
        raise InvalidNotificationError(msg)


async def notify(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    audience: Audience,
    kind: NotificationType,
    payload: NotificationPayload,
    subject_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID | None:
    """Add one notification to the caller's transaction (no commit).

    Returns the new id, or ``None`` when ``dedupe_key`` was already used for
    this recipient. Pending ORM changes are flushed first, so the recipient,
    actor or subject created in the same unit of work already exist.
    ``created_at`` backdates the row (the seed's demo history); live events
    leave it to "now".
    """
    _check(kind, audience, payload, subject_id)
    spec = CATALOG[kind]
    await session.flush()
    result = await session.execute(
        _insert(session)
        .values(
            id=uuid.uuid4(),
            recipient_id=recipient_id,
            audience=audience.value,
            type=kind.value,
            subject_kind=spec.subject.value if spec.subject is not None else None,
            subject_id=subject_id,
            actor_id=actor_id,
            data=payload.model_dump(mode="json"),
            dedupe_key=dedupe_key,
            created_at=created_at or utcnow(),
        )
        .returning(Notification.id)
    )
    return result.scalar_one_or_none()


async def notify_admins(
    session: AsyncSession,
    *,
    kind: NotificationType,
    payload: NotificationPayload,
    subject_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    created_at: datetime | None = None,
) -> list[uuid.UUID]:
    """Fan one event out to every admin's ``admin`` inbox (each admin reads
    and dismisses their own copy), except ``actor_id`` - an admin is never
    told about what they just did. Returns the ids written."""
    _check(kind, Audience.ADMIN, payload, subject_id)
    admins = await session.scalars(
        select(User.id)
        .where(json_array_contains(User.roles, ROLE_ADMIN))
        .order_by(User.created_at, User.id)
    )
    written: list[uuid.UUID] = []
    for admin_id in admins.all():
        if admin_id == actor_id:
            continue
        created = await notify(
            session,
            recipient_id=admin_id,
            audience=Audience.ADMIN,
            kind=kind,
            payload=payload,
            subject_id=subject_id,
            actor_id=actor_id,
            dedupe_key=dedupe_key,
            created_at=created_at,
        )
        if created is not None:
            written.append(created)
    return written


async def resolve(
    session: AsyncSession,
    *,
    kind: NotificationType,
    subject_id: uuid.UUID,
    recipient_id: uuid.UUID | None = None,
) -> int:
    """Mark the unread ``kind`` notifications about ``subject_id`` read - for
    the recipient, or for everyone (e.g. every admin) when ``None``.

    For *actionable* notifications whose action just happened: the cook's
    "new order request" once they answered it, every admin's "new cook
    application" once one of them decided it. Joins the caller's transaction
    like :func:`notify`; returns how many rows changed.
    """
    conditions: list[Any] = [
        Notification.type == kind.value,
        Notification.subject_id == subject_id,
        Notification.read_at.is_(None),
    ]
    if recipient_id is not None:
        conditions.append(Notification.recipient_id == recipient_id)
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Notification)
            .where(*conditions)
            .values(read_at=utcnow())
            .execution_options(synchronize_session=False)
        ),
    )
    return result.rowcount


# --- reading: which inboxes ----------------------------------------------------------


def visible_audiences(user: User) -> tuple[Audience, ...]:
    """The inboxes this account can read right now, in panel order."""
    audiences = [Audience.ACCOUNT]
    if user.is_cook:
        audiences.append(Audience.COOK)
    if user.is_admin:
        audiences.append(Audience.ADMIN)
    return tuple(audiences)


def resolve_audiences(user: User, requested: Audience | None) -> tuple[Audience, ...]:
    """``requested`` alone (403 without its role), or every visible inbox."""
    visible = visible_audiences(user)
    if requested is None:
        return visible
    if requested not in visible:
        raise ForbiddenError(
            f"The {requested.value} inbox requires the {requested.value} role"
        )
    return (requested,)


def _inbox(
    user_id: uuid.UUID, audiences: Sequence[Audience]
) -> list[ColumnElement[bool]]:
    return [
        Notification.recipient_id == user_id,
        Notification.audience.in_([audience.value for audience in audiences]),
    ]


# --- reading: lists and counts ----------------------------------------------------------


async def page_notifications(
    session: AsyncSession,
    user: User,
    *,
    audience: Audience | None = None,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, int, list[Notification]]:
    """Newest first: ``(total_matching, unread_in_those_inboxes, page)``."""
    conditions = _inbox(user.id, resolve_audiences(user, audience))
    unread = (
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(*conditions, Notification.read_at.is_(None))
        )
    ) or 0
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    total = (
        await session.scalar(
            select(func.count()).select_from(Notification).where(*conditions)
        )
    ) or 0
    rows = await session.scalars(
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(limit)
        .offset(offset)
    )
    return total, unread, list(rows.all())


async def unread_counts(session: AsyncSession, user: User) -> dict[Audience, int]:
    """Unread per inbox; inboxes the user cannot see count 0."""
    counts = dict.fromkeys(Audience, 0)
    rows = await session.execute(
        select(Notification.audience, func.count())
        .where(
            *_inbox(user.id, visible_audiences(user)), Notification.read_at.is_(None)
        )
        .group_by(Notification.audience)
    )
    for audience, count in rows.all():
        counts[Audience(audience)] = count
    return counts


async def get_visible(
    session: AsyncSession, notification_id: uuid.UUID, user: User
) -> Notification:
    """One of the caller's notifications in an inbox they can see, else 404."""
    row = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            *_inbox(user.id, visible_audiences(user)),
        )
    )
    if row is None:
        raise NotificationNotFoundError
    return row


# --- changing the inbox ------------------------------------------------------------


async def set_read(
    session: AsyncSession, row: Notification, *, read: bool
) -> Notification:
    """Mark read (the first read time is kept) or unread again."""
    if read and row.read_at is None:
        row.read_at = utcnow()
    elif not read:
        row.read_at = None
    await session.commit()
    await session.refresh(row)
    return row


async def mark_all_read(
    session: AsyncSession,
    user: User,
    *,
    audience: Audience | None = None,
    before: datetime | None = None,
) -> int:
    """Mark every unread notification in the given inbox(es) read - only those
    created at or before ``before`` when given. Returns how many changed."""
    conditions: list[Any] = [
        *_inbox(user.id, resolve_audiences(user, audience)),
        Notification.read_at.is_(None),
    ]
    if before is not None:
        conditions.append(Notification.created_at <= before)
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Notification)
            .where(*conditions)
            .values(read_at=utcnow())
            .execution_options(synchronize_session=False)
        ),
    )
    await session.commit()
    return result.rowcount


async def delete_notification(session: AsyncSession, row: Notification) -> None:
    """Dismiss for good (the caller's own copy only)."""
    await session.delete(row)
    await session.commit()

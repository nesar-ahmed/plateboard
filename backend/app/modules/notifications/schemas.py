"""Schemas for the notification inbox (``/api/me/notifications``).

A notification reads the same in every panel: ``title`` and ``body`` are
rendered by the backend (``catalog.render``), ``subject`` says what to link
to and ``data`` is the raw snapshot (names, totals, reason) for clients that
want more than the text.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.modules.notifications.catalog import render
from app.modules.notifications.models import Audience, Notification, SubjectKind
from app.shared.types import UTCDateTime

__all__ = [
    "MarkAllReadOut",
    "MarkAllReadRequest",
    "NotificationOut",
    "NotificationPage",
    "NotificationPatch",
    "NotificationSubjectOut",
    "UnreadCountOut",
    "notification_out",
]


class NotificationSubjectOut(BaseModel):
    kind: SubjectKind = Field(description="order | kitchen | review")
    id: uuid.UUID = Field(
        description="orders.id, the cook's user id for a kitchen, or reviews.id"
    )


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str = Field(
        description="what happened, e.g. order.accepted "
        "(see NotificationType in app/modules/notifications/catalog.py)"
    )
    audience: Audience = Field(description="the panel inbox: account | cook | admin")
    title: str
    body: str | None
    subject: NotificationSubjectOut | None = Field(
        description="what it is about - may no longer exist (deleted order, kitchen)"
    )
    actor_id: uuid.UUID | None = Field(
        description="who caused it (null: the platform, or a deleted account)"
    )
    data: dict[str, Any] = Field(description="snapshot taken when it happened")
    read: bool
    read_at: UTCDateTime | None
    created_at: UTCDateTime


class NotificationPage(BaseModel):
    """Same pagination contract as orders and dishes, plus the unread count
    of the inbox being listed (regardless of the ``unread`` filter)."""

    items: list[NotificationOut]
    total: int
    unread: int
    limit: int
    offset: int


class UnreadCountOut(BaseModel):
    """Unread notifications per panel - one cheap call for every badge. A
    panel the caller has no role for is always 0."""

    total: int
    account: int
    cook: int
    admin: int


class NotificationPatch(BaseModel):
    """Body for ``PATCH /api/me/notifications/{id}``."""

    read: bool = Field(description="true = mark read, false = mark unread again")


class MarkAllReadRequest(BaseModel):
    """Body for ``POST /api/me/notifications/read-all`` (every field optional)."""

    audience: Audience | None = Field(
        default=None, description="only this panel's inbox (default: every visible one)"
    )
    before: UTCDateTime | None = Field(
        default=None,
        description="only notifications created at or before this instant - pass "
        "the newest one the user saw, so later arrivals stay unread",
    )


class MarkAllReadOut(BaseModel):
    marked: int = Field(description="notifications that were unread and now are read")


def notification_out(row: Notification) -> NotificationOut:
    rendered = render(row.type, row.audience, row.subject_id, row.data or {})
    return NotificationOut(
        id=row.id,
        type=row.type,
        audience=Audience(row.audience),
        title=rendered.title,
        body=rendered.body,
        subject=_subject(row),
        actor_id=row.actor_id,
        data=row.data or {},
        read=row.read_at is not None,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def _subject(row: Notification) -> NotificationSubjectOut | None:
    """The link target; a kind this build no longer knows is simply no link."""
    if row.subject_kind is None or row.subject_id is None:
        return None
    try:
        kind = SubjectKind(row.subject_kind)
    except ValueError:
        return None
    return NotificationSubjectOut(kind=kind, id=row.subject_id)

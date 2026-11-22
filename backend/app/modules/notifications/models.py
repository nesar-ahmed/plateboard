"""ORM model for in-app notifications: one row per recipient, per event.

* ``recipient_id`` - who reads it (CASCADE: an account's inbox dies with it).
* ``audience`` - which panel's inbox it belongs to. One account can be a
  customer, a cook *and* an admin at once, so the panel is part of the row,
  not derived from the recipient's roles: ``account`` (``/account`` - every
  signed-in user, admins included), ``cook`` (``/cook``) and ``admin``
  (``/admin``). A CHECK keeps it to :class:`Audience`.
* ``type`` - what happened (``order.accepted``, ...), one of
  ``catalog.NotificationType``. Deliberately *not* CHECK-constrained: new
  types are added in Python without a migration, and a retired type still
  renders (with a generic title) instead of breaking the inbox.
* ``subject_kind`` + ``subject_id`` - what it is about (an order, a kitchen),
  for the client to link to. No foreign key on purpose: the notification
  outlives its subject, exactly like an order outlives its dishes.
* ``actor_id`` - who caused it, if anyone (SET NULL: deleting that account
  keeps the notification).
* ``data`` - a JSON snapshot of what the text needs (names, totals, the
  cook's reason), validated against the type's payload model when written.
  Titles/bodies are rendered from it at read time (``catalog.render``), so
  copy can change without rewriting rows - and later edits to the order or
  profile never change what a notification said (same rule as the order's
  dish and address snapshots).
* ``dedupe_key`` - optional idempotency key, unique *per recipient*: writing
  the same event twice (a retry, a re-run seed, a scheduled reminder) keeps
  one row. NULL keys never collide (SQL NULLs are distinct).
* ``read_at`` - NULL while unread.

No ``updated_at``: a notification is written once; only ``read_at`` moves.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, UUIDPrimaryKeyMixin, utcnow

TYPE_MAX_LENGTH = 60
SUBJECT_KIND_MAX_LENGTH = 20
DEDUPE_KEY_MAX_LENGTH = 200


class Audience(str, Enum):
    """The panel whose inbox a notification lands in."""

    ACCOUNT = "account"  # /account - every signed-in user
    COOK = "cook"  # /cook - role: cook
    ADMIN = "admin"  # /admin - role: admin


AUDIENCE_VALUES: tuple[str, ...] = tuple(audience.value for audience in Audience)


class SubjectKind(str, Enum):
    """What a notification is about - the client turns ``(kind, id)`` into a
    link for its panel (``/account/orders/{id}``, ``/cook/orders/{id}``, ...)."""

    ORDER = "order"  # id: orders.id
    KITCHEN = "kitchen"  # id: the cook's user id (cooks.user_id)
    REVIEW = "review"  # id: reviews.id


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Notification(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"audience IN ({_in(AUDIENCE_VALUES)})", name="audience_known"),
        # A subject is a pair: both set or both NULL.
        CheckConstraint(
            "(subject_kind IS NULL) = (subject_id IS NULL)", name="subject_complete"
        ),
        # One row per (recipient, event key); NULL keys are never duplicates.
        UniqueConstraint(
            "recipient_id", "dedupe_key", name="uq_notifications_recipient_dedupe_key"
        ),
        # The inbox: one panel of one account, newest first.
        Index("ix_notifications_inbox", "recipient_id", "audience", "created_at"),
        # The unread badges: only unread rows are indexed, so the count stays
        # cheap however long the history grows.
        Index(
            "ix_notifications_unread",
            "recipient_id",
            "audience",
            sqlite_where=text("read_at IS NULL"),
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    # Indexed through ix_notifications_inbox (leading column), which also
    # serves the users -> notifications CASCADE.
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    audience: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(TYPE_MAX_LENGTH), nullable=False)
    subject_kind: Mapped[str | None] = mapped_column(
        String(SUBJECT_KIND_MAX_LENGTH), nullable=True
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(
        String(DEDUPE_KEY_MAX_LENGTH), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, server_default=func.now(), nullable=False
    )

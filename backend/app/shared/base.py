"""Shared kernel: declarative base and column mixins used by every model.

Rule of thumb for the layout: code in ``app/shared`` may not import from
``app.api``. Feature packages (``app/api/<feature>``) may import from here
freely, which keeps the dependency graph pointing in one direction and makes
features easy to lift out into services later.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import DateTime, MetaData, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Consistent constraint names are what makes `alembic revision --autogenerate`
# produce reviewable diffs instead of dropping/recreating everything.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Naive "now" in UTC.

    SQLite has no timezone-aware storage: ``DATETIME`` values come back without
    ``tzinfo`` (verified against SQLAlchemy 2.1). Storing naive UTC everywhere
    keeps a single unambiguous convention in the database; the API layer adds
    the offset back on the way out (see :mod:`app.shared.types`).
    """
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Python annotation -> SQLAlchemy column type, so models stay declarative.
    type_annotation_map: ClassVar[dict[object, object]] = {
        uuid.UUID: Uuid(),
        datetime: DateTime(),
        str: String(),
    }

    def __repr__(self) -> str:
        identity = getattr(self, "id", None)
        state = "transient" if identity is None else str(identity)
        return f"<{type(self).__name__} {state}>"


class UUIDPrimaryKeyMixin:
    """Surrogate primary key: UUIDs survive data export and sharding."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """``created_at`` / ``updated_at`` maintained by Python *and* the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )

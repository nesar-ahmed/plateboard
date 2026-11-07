"""Reusable Pydantic/typing helpers for API schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer


def _to_utc_naive(value: datetime) -> datetime:
    """Normalise incoming datetimes to naive UTC before they hit the database.

    A client posting ``2026-01-01T12:00:00+05:00`` must not be stored as
    ``12:00`` - SQLite would drop the offset silently.
    """
    if value.tzinfo is None:
        # Naive input is interpreted as UTC, matching how values are stored.
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _with_utc_offset(value: datetime) -> datetime:
    """Attach UTC on the way out so JSON always carries an explicit offset."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


UTCDateTime = Annotated[
    datetime,
    AfterValidator(_to_utc_naive),
    PlainSerializer(_with_utc_offset, when_used="json"),
]
"""``datetime`` that accepts any offset, stores naive UTC, returns ``+00:00``.

Use it for every timestamp field exposed by the API
(``created_at``, ``due_at``, ...) instead of bare ``datetime``.
"""

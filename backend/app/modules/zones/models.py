"""ORM model for zones: named cells on the platform's service grid.

A zone is one cell of an integer grid (``x`` = column, ``y`` = row, both
>= 0); at most one zone per cell. Cooks are placed in a zone (see
``CookProfile.zone``), which is what gives dishes a location for the public
menu's zone / distance filters. Distances live in :mod:`app.modules.zones.grid`.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SLUG_MAX_LENGTH = 40
NAME_MAX_LENGTH = 60


class Zone(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Reference data (seeded, not user-created). ``slug`` is the public,
    stable identifier used in URLs and query strings (``?zone=old-town``)."""

    __tablename__ = "zones"
    __table_args__ = (
        # One zone per grid cell; named explicitly because the project's "uq"
        # naming convention only covers the first column.
        UniqueConstraint("x", "y", name="uq_zones_x_y"),
        CheckConstraint("x >= 0", name="x_non_negative"),
        CheckConstraint("y >= 0", name="y_non_negative"),
    )

    slug: Mapped[str] = mapped_column(
        String(SLUG_MAX_LENGTH), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)

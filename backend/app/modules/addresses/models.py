"""ORM model for delivery addresses (an account's address book).

An account keeps up to :data:`MAX_ADDRESSES` addresses; at most one is the
default - a partial unique index makes "one default per user" a database
rule, not just a service convention. An address may sit in a service-grid
zone (optional), which is what lets the platform relate a delivery to a
cook's kitchen later on.

Orders never point at an address row: placing an order copies the address
into the order (``Order.delivery_address``), so editing or deleting an
address never rewrites order history - same idea as the dish snapshot.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.zones.models import Zone
from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MAX_ADDRESSES = 10
LABEL_MAX_LENGTH = 40
RECIPIENT_MAX_LENGTH = 80
PHONE_MAX_LENGTH = 30
LINE_MAX_LENGTH = 120
CITY_MAX_LENGTH = 80
POSTAL_CODE_MAX_LENGTH = 20
INSTRUCTIONS_MAX_LENGTH = 200


class Address(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "addresses"
    __table_args__ = (
        # At most one default address per account.
        Index(
            "uq_addresses_one_default_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(LABEL_MAX_LENGTH), nullable=True)
    recipient: Mapped[str] = mapped_column(String(RECIPIENT_MAX_LENGTH), nullable=False)
    phone: Mapped[str] = mapped_column(String(PHONE_MAX_LENGTH), nullable=False)
    line1: Mapped[str] = mapped_column(String(LINE_MAX_LENGTH), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(LINE_MAX_LENGTH), nullable=True)
    city: Mapped[str] = mapped_column(String(CITY_MAX_LENGTH), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(
        String(POSTAL_CODE_MAX_LENGTH), nullable=True
    )
    instructions: Mapped[str | None] = mapped_column(
        String(INSTRUCTIONS_MAX_LENGTH), nullable=True
    )
    # SET NULL: retiring a zone keeps the address, just un-placed.
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("zones.id", ondelete="SET NULL"), index=True, nullable=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Eager like CookProfile.zone: every address response shows the zone.
    zone: Mapped[Zone | None] = relationship(lazy="joined")

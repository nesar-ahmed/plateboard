"""ORM models for accounts (with roles + profile) and server-side sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

# A real import (not TYPE_CHECKING-only): the CookProfile.zone relationship
# must resolve even when a caller imports these models without app.models.
from app.modules.zones.models import Zone
from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

# The roles a user account may hold. New roles are added here.
ROLE_CUSTOMER = "customer"
ROLE_COOK = "cook"
ALL_ROLES = (ROLE_CUSTOMER, ROLE_COOK)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An account. ``email`` is stored normalized to lowercase, which is what
    makes uniqueness case-insensitive without relying on dialect-specific
    COLLATE or citext behaviour.

    ``roles`` is a JSON list of strings (see ``ALL_ROLES``); a user starts as a
    plain customer and gains ``cook`` via the become-a-cook action. Keeping it
    a list is what lets an account be customer, cook, *or both*.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(254), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- profile (editable via PATCH /api/me/profile) ----------------------
    display_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    area: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )  # free-text locality

    roles: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: [ROLE_CUSTOMER]
    )

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    cook_profile: Mapped[CookProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    def has_role(self, role: str) -> bool:
        return role in (self.roles or [])

    @property
    def is_cook(self) -> bool:
        return self.has_role(ROLE_COOK)


class UserSession(Base):
    """One server-side session.

    The primary key is the SHA-256 of the cookie token, never the token
    itself: a database leak must not hand out live sessions.
    """

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    @property
    def active(self) -> bool:
        return self.revoked_at is None and self.expires_at > utcnow()


class CookProfile(Base, TimestampMixin):
    """The cook-side profile created by the become-a-cook action.

    One row per cooking user (``user_id`` is both PK and FK). ``specialties``
    is a JSON list of short free-text tags. ``zone`` is where the kitchen is
    on the service grid - optional, and what places the cook's dishes for the
    public menu's zone/distance filters.
    """

    __tablename__ = "cooks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    headline: Mapped[str] = mapped_column(String(80), nullable=False)
    specialties: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # SET NULL: retiring a zone un-places its cooks instead of deleting them.
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("zones.id", ondelete="SET NULL"), index=True, nullable=True
    )

    user: Mapped[User] = relationship(back_populates="cook_profile")
    # Eager (joined) on purpose: every cook response shows the zone, and a lazy
    # load would be implicit IO under asyncio.
    zone: Mapped[Zone | None] = relationship(lazy="joined")

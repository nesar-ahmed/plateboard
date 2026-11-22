"""ORM models for accounts (with roles + profile) and server-side sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# A real import (not TYPE_CHECKING-only): the CookProfile.zone relationship
# must resolve even when a caller imports these models without app.models.
from app.modules.zones.models import Zone
from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

# The roles a user account may hold. New roles are added here.
ROLE_CUSTOMER = "customer"
ROLE_COOK = "cook"
# Platform operator (back office + admin dashboard). Never granted through the
# API - only by the seed script (or another operator-run script).
ROLE_ADMIN = "admin"
ALL_ROLES = (ROLE_CUSTOMER, ROLE_COOK, ROLE_ADMIN)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An account. ``email`` is stored normalized to lowercase, which is what
    makes uniqueness case-insensitive without relying on dialect-specific
    COLLATE or citext behaviour.

    ``roles`` is a JSON list of strings (see ``ALL_ROLES``); a user starts as a
    plain customer and gains ``cook`` when an admin accepts their cook
    application (``CookProfile.status``) - never on the application itself.
    Keeping it a list is what lets an account be customer, cook, *or both*.
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

    # --- food preferences (GET/PUT /api/me/preferences) ---------------------
    # Allergen tokens from the dishes' fixed Allergen vocabulary, and free-text
    # dietary tags (same normalization as dish tags). The UI offers them as
    # one-tap menu filters; nothing is filtered server-side without asking.
    excluded_allergens: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    dietary_preferences: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    cook_profile: Mapped[CookProfile | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        # cooks has several FKs to users (owner, verifier, reviewer): say which.
        foreign_keys="CookProfile.user_id",
    )

    def has_role(self, role: str) -> bool:
        return role in (self.roles or [])

    @property
    def is_customer(self) -> bool:
        return self.has_role(ROLE_CUSTOMER)

    @property
    def is_cook(self) -> bool:
        return self.has_role(ROLE_COOK)

    @property
    def is_admin(self) -> bool:
        return self.has_role(ROLE_ADMIN)


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


#: Longest IANA timezone name accepted for a kitchen ("America/Argentina/...").
TIMEZONE_MAX_LENGTH = 64
#: Longest explanation an admin may give when rejecting a cook application.
REJECTION_REASON_MAX_LENGTH = 300


class CookApplicationStatus(str, Enum):
    """Where a cook application stands. ``pending`` -> ``accepted`` |
    ``rejected`` (an admin's decision); a rejected applicant may apply again
    (-> ``pending``). Only ``accepted`` kitchens exist for the platform."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


COOK_APPLICATION_STATUS_VALUES: tuple[str, ...] = tuple(
    status.value for status in CookApplicationStatus
)


class CookProfile(Base, TimestampMixin):
    """The cook-side profile - created by the cook *application*.

    One row per applicant/cook (``user_id`` is both PK and FK). ``specialties``
    is a JSON list of short free-text tags. ``zone`` is where the kitchen is
    on the service grid - optional, and what places the cook's dishes for the
    public menu's zone/distance filters.

    The application (``POST /api/cooks``; decided in the back office):

    * ``status`` - ``pending`` until an admin accepts or rejects it. Accepting
      adds the ``cook`` role, so every cook-only endpoint stays closed (403)
      while pending or after a rejection, and only accepted kitchens are
      public. ``submitted_at`` is the latest (re)submission; ``reviewed_at`` /
      ``reviewed_by_id`` (SET NULL) the decision; ``rejection_reason`` is the
      admin's optional explanation, shown to the applicant.

    Trust + availability:

    * ``verified_at`` / ``verified_by_id`` - set by an admin after checking the
      kitchen (``/api/admin/cooks/{id}/verification``); the public badge.
    * ``timezone`` (IANA) + ``opening_hours`` (JSON list of
      ``{"day": 0-6, "opens": "HH:MM", "closes": "HH:MM"|"24:00"}``, Monday =
      0, kitchen-local wall time) + ``orders_paused`` - when the kitchen takes
      orders (``app.modules.cooks.availability``). No hours = no fixed hours:
      orders are taken any time (the cook still accepts each one).
    """

    __tablename__ = "cooks"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{value}'" for value in COOK_APPLICATION_STATUS_VALUES)
            + ")",
            name="status_known",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    headline: Mapped[str] = mapped_column(String(80), nullable=False)
    specialties: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # SET NULL: retiring a zone un-places its cooks instead of deleting them.
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("zones.id", ondelete="SET NULL"), index=True, nullable=True
    )

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    # SET NULL: deleting the admin account keeps the kitchen verified.
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    timezone: Mapped[str] = mapped_column(
        String(TIMEZONE_MAX_LENGTH), nullable=False, default="UTC"
    )
    opening_hours: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    orders_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CookApplicationStatus.PENDING.value,
        server_default=text("'pending'"),
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    # SET NULL: deleting the admin account keeps the decision.
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(REJECTION_REASON_MAX_LENGTH), nullable=True
    )

    @property
    def is_accepted(self) -> bool:
        return self.status == CookApplicationStatus.ACCEPTED.value

    user: Mapped[User] = relationship(
        back_populates="cook_profile", foreign_keys=[user_id]
    )
    # Eager (joined) on purpose: every cook response shows the zone, and a lazy
    # load would be implicit IO under asyncio.
    zone: Mapped[Zone | None] = relationship(lazy="joined")

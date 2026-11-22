"""Schemas for the admin back office (``/api/admin/...`` lists and actions)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from app.modules.auth.models import REJECTION_REASON_MAX_LENGTH, CookApplicationStatus
from app.modules.zones.schemas import ZoneOut
from app.shared.types import UTCDateTime


class AdminUserOut(BaseModel):
    """One account as the back office sees it: identity, roles and activity."""

    id: uuid.UUID
    email: str
    display_name: str | None
    area: str | None
    roles: list[str]
    created_at: UTCDateTime
    last_login_at: UTCDateTime | None = Field(description="latest session start")
    orders_placed: int = Field(description="orders this account placed as a customer")
    orders_received: int = Field(
        description="orders placed with this account as a cook"
    )
    verified_at: UTCDateTime | None = Field(
        description="cooks: when the kitchen was verified (null: not verified / no kitchen)"
    )
    cook_application: CookApplicationStatus | None = Field(
        description="pending | accepted | rejected (null: never applied to cook)"
    )


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class CookVerificationOut(BaseModel):
    """A kitchen's verification after ``POST``/``DELETE
    /api/admin/cooks/{user_id}/verification``."""

    user_id: uuid.UUID
    verified: bool
    verified_at: UTCDateTime | None
    verified_by: uuid.UUID | None = Field(description="the admin who verified it")


# --- cook applications ---------------------------------------------------------------


class CookApplicationOut(BaseModel):
    """One cook application as the back office reviews it: the applicant and
    the kitchen they described."""

    user_id: uuid.UUID
    email: str
    display_name: str | None
    area: str | None
    bio: str | None
    headline: str
    specialties: list[str]
    zone: ZoneOut | None
    status: CookApplicationStatus
    submitted_at: UTCDateTime = Field(description="latest (re)submission")
    reviewed_at: UTCDateTime | None
    reviewed_by: uuid.UUID | None = Field(description="the admin who decided")
    rejection_reason: str | None


class CookApplicationPage(BaseModel):
    items: list[CookApplicationOut]
    total: int
    limit: int
    offset: int


class CookApplicationRejectRequest(BaseModel):
    """Body for rejecting an application. The reason is **required**: the
    applicant is told why, so they know what to change before applying again
    (trimmed; blank is a 422)."""

    reason: str = Field(
        max_length=REJECTION_REASON_MAX_LENGTH,
        description="why the application is rejected - shown to the applicant",
    )

    @field_validator("reason")
    @classmethod
    def _clean_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank - tell the applicant why")
        return stripped

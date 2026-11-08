"""Schemas for the cook profile endpoints."""

from __future__ import annotations

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.zones.models import SLUG_MAX_LENGTH as ZONE_SLUG_MAX_LENGTH
from app.modules.zones.schemas import ZoneOut, normalize_zone_slug
from app.shared.types import UTCDateTime

HEADLINE_MIN_LENGTH = 3
HEADLINE_MAX_LENGTH = 80
SPECIALTY_MAX_LENGTH = 30
SPECIALTY_MAX_COUNT = 10


def validate_tags(tags: list[str]) -> list[str]:
    """Per-tag length/blank checks, then trim + lowercase and reject dupes.

    Raises ValueError so pydantic surfaces it as a 422 field error.
    """
    normalized: dict[str, None] = {}
    for raw in tags:
        tag = raw.strip().lower()
        if not tag:
            raise ValueError("specialty tags must not be blank")
        if len(tag) > SPECIALTY_MAX_LENGTH:
            raise ValueError(
                f"specialty tags are limited to {SPECIALTY_MAX_LENGTH} characters"
            )
        if tag in normalized:
            raise ValueError("specialty tags must be unique (case-insensitive)")
        normalized[tag] = None
    return list(normalized)


def validate_headline(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


def validate_zone_ref(value: str | None) -> str | None:
    """Zone slug from a request body: normalized; blank is an error (send
    ``null``/omit to mean "no zone"). Existence is checked by the service."""
    if value is None:
        return None
    slug = normalize_zone_slug(value)
    if slug is None:
        raise ValueError("must not be blank")
    return slug


class CookCreateRequest(BaseModel):
    """Body for the become-a-cook action."""

    headline: str = Field(
        min_length=HEADLINE_MIN_LENGTH, max_length=HEADLINE_MAX_LENGTH
    )
    specialties: list[str] = Field(default_factory=list, max_length=SPECIALTY_MAX_COUNT)
    zone: str | None = Field(
        default=None,
        max_length=ZONE_SLUG_MAX_LENGTH,
        description="zone slug (GET /api/zones) where the kitchen is",
    )

    @field_validator("headline")
    @classmethod
    def _clean_headline(cls, value: str) -> str:
        return validate_headline(value)  # type: ignore[return-value]

    @field_validator("specialties")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return validate_tags(tags)

    @field_validator("zone")
    @classmethod
    def _clean_zone(cls, value: str | None) -> str | None:
        return validate_zone_ref(value)


class CookPatchRequest(BaseModel):
    """Partial cook-profile edit: at least one field required.

    ``headline``/``specialties``: omitted or null keeps the stored value.
    ``zone``: omitted keeps, a slug moves the kitchen, an explicit ``null``
    clears it (same three states as the profile PATCH).
    """

    headline: str | None = Field(
        default=None, min_length=HEADLINE_MIN_LENGTH, max_length=HEADLINE_MAX_LENGTH
    )
    specialties: list[str] | None = Field(default=None, max_length=SPECIALTY_MAX_COUNT)
    zone: str | None = Field(default=None, max_length=ZONE_SLUG_MAX_LENGTH)

    @field_validator("headline")
    @classmethod
    def _clean_headline(cls, value: str | None) -> str | None:
        return validate_headline(value)

    @field_validator("specialties")
    @classmethod
    def _clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else validate_tags(tags)

    @field_validator("zone")
    @classmethod
    def _clean_zone(cls, value: str | None) -> str | None:
        return validate_zone_ref(value)

    @property
    def zone_sent(self) -> bool:
        """True when the client sent ``zone`` at all (``null`` included)."""
        return "zone" in self.model_fields_set

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if self.headline is None and self.specialties is None and not self.zone_sent:
            raise ValueError(
                "at least one of headline, specialties, zone must be provided"
            )
        return self


class CookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    headline: str
    specialties: list[str]
    zone: ZoneOut | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class CookPublicOut(BaseModel):
    """Public cook-profile card: profile fields merged with the account's
    editable identity fields (display name, bio, free-text area) and the
    kitchen's grid zone."""

    user_id: uuid.UUID
    display_name: str | None
    bio: str | None
    area: str | None
    headline: str
    specialties: list[str]
    zone: ZoneOut | None
    created_at: UTCDateTime


class CookPage(BaseModel):
    """``GET /api/cooks`` envelope (same pagination contract as dishes)."""

    items: list[CookPublicOut]
    total: int
    limit: int
    offset: int

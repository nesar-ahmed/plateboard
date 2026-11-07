"""Schemas for the cook profile endpoints."""

from __future__ import annotations

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class CookCreateRequest(BaseModel):
    """Body for the become-a-cook action."""

    headline: str = Field(
        min_length=HEADLINE_MIN_LENGTH, max_length=HEADLINE_MAX_LENGTH
    )
    specialties: list[str] = Field(default_factory=list, max_length=SPECIALTY_MAX_COUNT)

    @field_validator("headline")
    @classmethod
    def _clean_headline(cls, value: str) -> str:
        return validate_headline(value)  # type: ignore[return-value]

    @field_validator("specialties")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return validate_tags(tags)


class CookPatchRequest(BaseModel):
    """Partial cook-profile edit: at least one field required."""

    headline: str | None = Field(
        default=None, min_length=HEADLINE_MIN_LENGTH, max_length=HEADLINE_MAX_LENGTH
    )
    specialties: list[str] | None = Field(default=None, max_length=SPECIALTY_MAX_COUNT)

    @field_validator("headline")
    @classmethod
    def _clean_headline(cls, value: str | None) -> str | None:
        return validate_headline(value)

    @field_validator("specialties")
    @classmethod
    def _clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else validate_tags(tags)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if self.headline is None and self.specialties is None:
            raise ValueError("at least one of headline, specialties must be provided")
        return self


class CookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    headline: str
    specialties: list[str]
    created_at: UTCDateTime
    updated_at: UTCDateTime

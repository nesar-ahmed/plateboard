"""Schemas for the address book (``/api/me/addresses``).

Validation contract (failures are 422 field errors):

* ``recipient``, ``phone``, ``line1``, ``city`` are required and never blank;
  ``label``, ``line2``, ``postal_code``, ``instructions`` are optional - blank
  means "none".
* ``phone``: digits with the usual separators (``+ ( ) - .`` and spaces),
  at least 6 digits.
* ``zone``: an optional service-grid zone slug (``GET /api/zones``); unknown
  slugs are a 422 ``unknown_zone`` (checked by the service).

PATCH follows the project's three-state rule: omitted keeps the stored value,
a value replaces it, ``null`` clears an optional field.
"""

from __future__ import annotations

import re
import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.addresses.models import (
    CITY_MAX_LENGTH,
    INSTRUCTIONS_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    LINE_MAX_LENGTH,
    PHONE_MAX_LENGTH,
    POSTAL_CODE_MAX_LENGTH,
    RECIPIENT_MAX_LENGTH,
)
from app.modules.zones.models import SLUG_MAX_LENGTH as ZONE_SLUG_MAX_LENGTH
from app.modules.zones.schemas import ZoneOut, normalize_zone_slug
from app.shared.types import UTCDateTime

_PHONE_CHARS = re.compile(r"^[0-9+()\-.\s]+$")
PHONE_MIN_DIGITS = 6

REQUIRED_FIELDS = ("recipient", "phone", "line1", "city")
OPTIONAL_FIELDS = ("label", "line2", "postal_code", "instructions")


def _required(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _phone(value: str) -> str:
    stripped = _required(value)
    if not _PHONE_CHARS.match(stripped):
        raise ValueError("use digits and + ( ) - . or spaces only")
    if sum(ch.isdigit() for ch in stripped) < PHONE_MIN_DIGITS:
        raise ValueError(f"must contain at least {PHONE_MIN_DIGITS} digits")
    return stripped


class AddressCreate(BaseModel):
    """Body for ``POST /api/me/addresses``. The first address of an account
    becomes its default regardless of ``is_default``."""

    label: str | None = Field(default=None, max_length=LABEL_MAX_LENGTH)
    recipient: str = Field(max_length=RECIPIENT_MAX_LENGTH)
    phone: str = Field(max_length=PHONE_MAX_LENGTH)
    line1: str = Field(max_length=LINE_MAX_LENGTH)
    line2: str | None = Field(default=None, max_length=LINE_MAX_LENGTH)
    city: str = Field(max_length=CITY_MAX_LENGTH)
    postal_code: str | None = Field(default=None, max_length=POSTAL_CODE_MAX_LENGTH)
    instructions: str | None = Field(default=None, max_length=INSTRUCTIONS_MAX_LENGTH)
    zone: str | None = Field(default=None, max_length=ZONE_SLUG_MAX_LENGTH)
    is_default: bool = False

    @field_validator("recipient", "line1", "city")
    @classmethod
    def _clean_required(cls, value: str) -> str:
        return _required(value)

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, value: str) -> str:
        return _phone(value)

    @field_validator("label", "line2", "postal_code", "instructions")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        return _optional(value)

    @field_validator("zone")
    @classmethod
    def _clean_zone(cls, value: str | None) -> str | None:
        return normalize_zone_slug(value)


class AddressPatch(BaseModel):
    """Partial edit (at least one field). Required fields cannot be cleared;
    ``is_default: true`` makes this the default (``false`` is refused - pick
    another default instead); ``zone: null`` clears the zone."""

    label: str | None = Field(default=None, max_length=LABEL_MAX_LENGTH)
    recipient: str | None = Field(default=None, max_length=RECIPIENT_MAX_LENGTH)
    phone: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    line1: str | None = Field(default=None, max_length=LINE_MAX_LENGTH)
    line2: str | None = Field(default=None, max_length=LINE_MAX_LENGTH)
    city: str | None = Field(default=None, max_length=CITY_MAX_LENGTH)
    postal_code: str | None = Field(default=None, max_length=POSTAL_CODE_MAX_LENGTH)
    instructions: str | None = Field(default=None, max_length=INSTRUCTIONS_MAX_LENGTH)
    zone: str | None = Field(default=None, max_length=ZONE_SLUG_MAX_LENGTH)
    is_default: bool | None = None

    @field_validator("recipient", "line1", "city")
    @classmethod
    def _clean_required(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("cannot be cleared")
        return _required(value)

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("cannot be cleared")
        return _phone(value)

    @field_validator("label", "line2", "postal_code", "instructions")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        return _optional(value)

    @field_validator("zone")
    @classmethod
    def _clean_zone(cls, value: str | None) -> str | None:
        return normalize_zone_slug(value)

    @field_validator("is_default")
    @classmethod
    def _only_true(cls, value: bool | None) -> bool | None:
        if value is False:
            raise ValueError("choose another default address instead")
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one address field must be provided")
        return self


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str | None
    recipient: str
    phone: str
    line1: str
    line2: str | None
    city: str
    postal_code: str | None
    instructions: str | None
    zone: ZoneOut | None
    is_default: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime


class DeliveryAddressOut(BaseModel):
    """The address as copied into an order at placement (no id: it is a
    snapshot, not a reference)."""

    label: str | None
    recipient: str
    phone: str
    line1: str
    line2: str | None
    city: str
    postal_code: str | None
    instructions: str | None
    zone: ZoneOut | None

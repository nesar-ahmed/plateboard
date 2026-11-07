"""Request/response schemas for the auth feature."""

from __future__ import annotations

import uuid
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.shared.types import UTCDateTime

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128  # cap scrypt input; longer is a DoS vector, not a feature

DISPLAY_NAME_MIN_LENGTH = 1
DISPLAY_NAME_MAX_LENGTH = 60
BIO_MAX_LENGTH = 500
AREA_MAX_LENGTH = 120


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


class LoginRequest(RegisterRequest):
    """Same shape as registration (login credentials are a valid pair too)."""


class ProfilePatchRequest(BaseModel):
    """Partial profile edit: every field optional, at least one required.

    Length limits are the acceptance rule for profile edits; blank-only
    strings are rejected rather than silently stored.
    """

    display_name: str | None = Field(
        default=None,
        min_length=DISPLAY_NAME_MIN_LENGTH,
        max_length=DISPLAY_NAME_MAX_LENGTH,
    )
    bio: str | None = Field(default=None, max_length=BIO_MAX_LENGTH)
    area: str | None = Field(default=None, max_length=AREA_MAX_LENGTH)

    @field_validator("display_name", "bio", "area")
    @classmethod
    def _strip_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if self.display_name is None and self.bio is None and self.area is None:
            raise ValueError("at least one of display_name, bio, area must be provided")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    bio: str | None
    area: str | None
    roles: list[str]
    created_at: UTCDateTime

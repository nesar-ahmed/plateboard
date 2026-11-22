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

from app.modules.dishes.models import ALLERGEN_VALUES, Allergen
from app.modules.dishes.schemas import validate_tag_list
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

    Three states per field, like ``DishPatchRequest``: omitted keeps the
    stored value, a string replaces it, an explicit ``null`` clears it.
    Length limits are the acceptance rule for profile edits; blank-only
    strings are rejected rather than silently stored (send ``null`` to clear).
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
        # model_fields_set (not ``is not None``) so an explicit null - i.e.
        # clearing a field - counts as a real edit.
        if not self.model_fields_set:
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
    updated_at: UTCDateTime  # bumps on profile edits / an accepted cook application


# --- account: food preferences, password, sessions ---------------------------------

DIETARY_PREFERENCE_MAX_LENGTH = 30
DIETARY_PREFERENCE_MAX_COUNT = 10


class PreferencesOut(BaseModel):
    """The account's food profile (``GET/PUT /api/me/preferences``)."""

    excluded_allergens: list[Allergen] = Field(
        description="allergens to keep off the menu, from the fixed Allergen vocabulary"
    )
    dietary_preferences: list[str] = Field(
        description="diets the user follows, e.g. vegan, halal (lowercase tags)"
    )


class PreferencesUpdate(BaseModel):
    """Full replacement (PUT): send both lists; an empty list clears one.

    Allergens must be known (422 otherwise) and are de-duplicated; diets are
    trimmed, lowercased tags - the same rules as dish dietary tags.
    """

    model_config = ConfigDict(use_enum_values=True)

    excluded_allergens: list[Allergen] = Field(
        default_factory=list, max_length=len(ALLERGEN_VALUES)
    )
    dietary_preferences: list[str] = Field(
        default_factory=list, max_length=DIETARY_PREFERENCE_MAX_COUNT
    )

    @field_validator("excluded_allergens")
    @classmethod
    def _dedupe(cls, values: list[Allergen]) -> list[Allergen]:
        return list(dict.fromkeys(values))

    @field_validator("dietary_preferences")
    @classmethod
    def _clean_diets(cls, values: list[str]) -> list[str]:
        return validate_tag_list(
            values,
            label="dietary preferences",
            max_length=DIETARY_PREFERENCE_MAX_LENGTH,
            max_count=DIETARY_PREFERENCE_MAX_COUNT,
        )


class PasswordChangeRequest(BaseModel):
    """``POST /api/me/password``: the current password proves it is you; the
    new one follows the registration rules and must differ from it."""

    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    @model_validator(mode="after")
    def _must_change(self) -> Self:
        if self.current_password == self.new_password:
            raise ValueError("the new password must differ from the current one")
        return self


class PasswordChangedOut(BaseModel):
    signed_out_sessions: int = Field(
        description="other sessions ended by the change (this one stays signed in)"
    )


class SessionOut(BaseModel):
    """One signed-in session of the account. ``id`` is a short fingerprint of
    the stored token hash - enough to tell sessions apart, useless to replay."""

    id: str
    created_at: UTCDateTime
    expires_at: UTCDateTime
    current: bool = Field(description="the session making this request")


class SessionsRevokedOut(BaseModel):
    signed_out_sessions: int

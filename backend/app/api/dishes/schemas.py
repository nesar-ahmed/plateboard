"""Schemas for the dish endpoints.

Validation contract (all failures are 422 with the project error envelope):

* ``name`` - required, 1..120 chars after trimming, never blank.
* ``price`` - integer minor units, **must be positive**.
* ``portions`` - at least 1, at most 999.
* ``allergens`` - each value must be one of the :class:`Allergen` enum
  members; unknown or repeated allergens are rejected.
* ``ingredients`` / ``dietary_tags`` - trimmed lowercase tags, like cook
  specialties: no blanks, no case-insensitive duplicates.
"""

from __future__ import annotations

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.dishes.models import ALLERGEN_VALUES, Allergen
from app.shared.types import UTCDateTime

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 1000
PORTIONS_MAX = 999
INGREDIENT_MAX_LENGTH = 60
INGREDIENT_MAX_COUNT = 25
TAG_MAX_LENGTH = 30
TAG_MAX_COUNT = 10


def validate_tag_list(
    values: list[str], *, label: str, max_length: int, max_count: int
) -> list[str]:
    """Per-item trim + lowercase, reject blank/oversized/duplicate entries.

    Raises ValueError so pydantic surfaces it as a 422 field error - the same
    tag semantics as cook specialties (``app.api.cooks.schemas``).
    """
    normalized: dict[str, None] = {}
    for raw in values:
        item = raw.strip().lower()
        if not item:
            raise ValueError(f"{label} must not be blank")
        if len(item) > max_length:
            raise ValueError(f"{label} are limited to {max_length} characters")
        if item in normalized:
            raise ValueError(f"{label} must be unique (case-insensitive)")
        normalized[item] = None
    if len(normalized) > max_count:
        raise ValueError(f"at most {max_count} {label} are allowed")
    return list(normalized)


def validate_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


def validate_description(value: str | None) -> str | None:
    """Blank or whitespace-only descriptions normalize to NULL (no empty strings)."""
    if value is None:
        return None
    return value.strip() or None


class DishCreateRequest(BaseModel):
    """Body for ``POST /api/me/dishes``. New dishes start active."""

    # Stored payload holds plain allergen token strings, never enum objects.
    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    price: int = Field(gt=0, description="integer amount in minor currency units")
    portions: int = Field(ge=1, le=PORTIONS_MAX)
    ingredients: list[str] = Field(default_factory=list, max_length=INGREDIENT_MAX_COUNT)
    allergens: list[Allergen] = Field(
        default_factory=list, max_length=len(ALLERGEN_VALUES)
    )
    dietary_tags: list[str] = Field(default_factory=list, max_length=TAG_MAX_COUNT)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return validate_name(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        return validate_description(value)

    @field_validator("ingredients")
    @classmethod
    def _clean_ingredients(cls, values: list[str]) -> list[str]:
        return validate_tag_list(
            values, label="ingredients", max_length=INGREDIENT_MAX_LENGTH,
            max_count=INGREDIENT_MAX_COUNT,
        )

    @field_validator("allergens")
    @classmethod
    def _unique_allergens(cls, values: list[Allergen]) -> list[Allergen]:
        # Membership is already guaranteed by the enum; only dupes are left.
        if len(set(values)) != len(values):
            raise ValueError("allergens must be unique")
        return values

    @field_validator("dietary_tags")
    @classmethod
    def _clean_tags(cls, values: list[str]) -> list[str]:
        return validate_tag_list(
            values, label="dietary tags", max_length=TAG_MAX_LENGTH,
            max_count=TAG_MAX_COUNT,
        )


class DishPatchRequest(BaseModel):
    """Partial dish edit: at least one field required (``active: false`` is
    the deactivation; an explicit ``description: null`` clears it)."""

    model_config = ConfigDict(use_enum_values=True)

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    price: int | None = Field(default=None, gt=0)
    portions: int | None = Field(default=None, ge=1, le=PORTIONS_MAX)
    ingredients: list[str] | None = Field(default=None, max_length=INGREDIENT_MAX_COUNT)
    allergens: list[Allergen] | None = Field(default=None, max_length=len(ALLERGEN_VALUES))
    dietary_tags: list[str] | None = Field(default=None, max_length=TAG_MAX_COUNT)
    active: bool | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        return None if value is None else validate_name(value)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        return validate_description(value)

    @field_validator("ingredients")
    @classmethod
    def _clean_ingredients(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else validate_tag_list(
            values, label="ingredients", max_length=INGREDIENT_MAX_LENGTH,
            max_count=INGREDIENT_MAX_COUNT,
        )

    @field_validator("allergens")
    @classmethod
    def _unique_allergens(cls, values: list[Allergen] | None) -> list[Allergen] | None:
        if values is None:
            return None
        if len(set(values)) != len(values):
            raise ValueError("allergens must be unique")
        return values

    @field_validator("dietary_tags")
    @classmethod
    def _clean_tags(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else validate_tag_list(
            values, label="dietary tags", max_length=TAG_MAX_LENGTH,
            max_count=TAG_MAX_COUNT,
        )

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        # model_fields_set (not ``is not None``) so an explicit null - e.g.
        # clearing the description - counts as a real edit.
        if not self.model_fields_set:
            raise ValueError("at least one dish field must be provided")
        return self


class DishOut(BaseModel):
    """Cook dashboard representation of a dish (``/api/me/dishes``)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cook_id: uuid.UUID
    name: str
    description: str | None
    price: int
    portions: int
    ingredients: list[str]
    allergens: list[Allergen]
    dietary_tags: list[str]
    active: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime


class PublicDishOut(DishOut):
    """Public menu representation: the cook's display name rides along so
    listing pages can link to the cook without fetching each profile."""

    cook_name: str | None = None


class DishPage(BaseModel):
    """``GET /api/dishes`` envelope: page plus the count of all matches,
    which is all the UI needs for prev/next pagination."""

    items: list[PublicDishOut]
    total: int
    limit: int
    offset: int

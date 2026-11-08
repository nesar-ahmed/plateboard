"""Schemas for the dish endpoints.

Validation contract (all failures are 422 with the project error envelope):

* ``name`` - required, 1..120 chars after trimming, never blank.
* ``price`` - integer minor units, **must be positive**.
* ``portions`` - at least 1, at most 999.
* ``allergens`` - each value must be one of the :class:`Allergen` enum
  members; unknown or repeated allergens are rejected.
* ``ingredients`` / ``dietary_tags`` - trimmed lowercase tags, like cook
  specialties: no blanks, no case-insensitive duplicates.

The public menu's query string is a schema too (:class:`PublicDishQuery`), so
filter mistakes - unknown allergen, ``min_price > max_price``, a distance
without a zone - are the same 422 field errors as body validation.
"""

from __future__ import annotations

import uuid
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.modules.dishes.models import ALLERGEN_VALUES, Allergen
from app.modules.zones.grid import MAX_GRID_DISTANCE
from app.modules.zones.models import SLUG_MAX_LENGTH as ZONE_SLUG_MAX_LENGTH
from app.modules.zones.schemas import ZoneOut, normalize_zone_slug
from app.shared.text import search_terms
from app.shared.types import UTCDateTime

NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 1000
PORTIONS_MAX = 999
INGREDIENT_MAX_LENGTH = 60
INGREDIENT_MAX_COUNT = 25
TAG_MAX_LENGTH = 30
TAG_MAX_COUNT = 10
SEARCH_MAX_LENGTH = 120
SEARCH_MAX_TERMS = 8  # every word is one more AND-ed LIKE group


def validate_tag_list(
    values: list[str], *, label: str, max_length: int, max_count: int
) -> list[str]:
    """Per-item trim + lowercase, reject blank/oversized/duplicate entries.

    Raises ValueError so pydantic surfaces it as a 422 field error - the same
    tag semantics as cook specialties (``app.modules.cooks.schemas``).
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
    """Public menu representation: the cook's display name and kitchen zone
    ride along so listing pages can link/place the cook without fetching each
    profile. ``distance`` (grid steps from the requested ``zone``) is only set
    when the menu was queried with ``?zone=``."""

    cook_name: str | None = None
    zone: ZoneOut | None = None
    distance: int | None = None


class PublicDishQuery(BaseModel):
    """Query-string filters for ``GET /api/dishes``. All optional, all ANDed.

    * ``q`` - text search: every word must appear (as a substring, accent-
      and case-insensitive) in the name, description or an ingredient
      (blank = no filter)
    * ``cook_id`` - one cook's dishes
    * ``zone`` - origin zone slug. Alone: dishes from cooks *in* that zone;
      with ``max_distance``: cooks within that many grid steps (Manhattan).
      Dishes of cooks without a zone never match a zone filter.
    * ``min_price`` / ``max_price`` - inclusive bounds in minor units
    * ``dietary_tag`` - repeatable; the dish must carry *every* tag given
    * ``exclude_allergen`` - repeatable; dishes declaring *any* are dropped
    """

    model_config = ConfigDict(use_enum_values=True)

    q: str | None = Field(
        default=None,
        max_length=SEARCH_MAX_LENGTH,
        description=(
            "text search: every word must appear in the name, description or "
            f"an ingredient (accent/case-insensitive, max {SEARCH_MAX_TERMS} words)"
        ),
    )
    cook_id: uuid.UUID | None = Field(default=None, description="restrict to one cook")
    zone: str | None = Field(
        default=None,
        max_length=ZONE_SLUG_MAX_LENGTH,
        description="origin zone slug (GET /api/zones); alone = same zone only",
    )
    max_distance: int | None = Field(
        default=None,
        ge=0,
        le=MAX_GRID_DISTANCE,
        description="with zone: max grid distance (Manhattan steps) to the cook",
    )
    min_price: int | None = Field(
        default=None, ge=0, description="inclusive, minor units"
    )
    max_price: int | None = Field(
        default=None, ge=0, description="inclusive, minor units"
    )
    dietary_tag: list[str] = Field(
        default_factory=list,
        max_length=TAG_MAX_COUNT,
        description="repeatable; dish must have all of them",
    )
    exclude_allergen: list[Allergen] = Field(
        default_factory=list,
        max_length=len(ALLERGEN_VALUES),
        description="repeatable; hide dishes declaring any of them",
    )

    @field_validator("q")
    @classmethod
    def _clean_query(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None  # blank search = no search
        if len(search_terms(value)) > SEARCH_MAX_TERMS:
            raise ValueError(f"search is limited to {SEARCH_MAX_TERMS} words")
        return value.strip()

    @property
    def terms(self) -> list[str]:
        """The folded search words (see ``app.shared.text.search_terms``)."""
        return search_terms(self.q)

    @field_validator("zone")
    @classmethod
    def _clean_zone(cls, value: str | None) -> str | None:
        return normalize_zone_slug(value)

    # Field order matters below: ``info.data`` only holds fields declared
    # (and successfully validated) *before* the one being validated.

    @field_validator("max_distance")
    @classmethod
    def _distance_needs_zone(
        cls, value: int | None, info: ValidationInfo
    ) -> int | None:
        if value is not None and info.data.get("zone") is None:
            raise ValueError("max_distance requires zone (the origin to measure from)")
        return value

    @field_validator("max_price")
    @classmethod
    def _price_range_ordered(
        cls, value: int | None, info: ValidationInfo
    ) -> int | None:
        low = info.data.get("min_price")
        if value is not None and low is not None and value < low:
            raise ValueError("max_price must be greater than or equal to min_price")
        return value

    @field_validator("dietary_tag")
    @classmethod
    def _clean_tags(cls, values: list[str]) -> list[str]:
        # Same normalization as stored tags (trim + lowercase); blanks are
        # ignored like a blank ``q``, duplicates collapse.
        tags: dict[str, None] = {}
        for raw in values:
            tag = raw.strip().lower()
            if len(tag) > TAG_MAX_LENGTH:
                raise ValueError(f"dietary tags are limited to {TAG_MAX_LENGTH} characters")
            if tag:
                tags[tag] = None
        return list(tags)

    @field_validator("exclude_allergen")
    @classmethod
    def _dedupe_allergens(cls, values: list[Allergen]) -> list[Allergen]:
        return list(dict.fromkeys(values))


class DishPage(BaseModel):
    """``GET /api/dishes`` envelope: page plus the count of all matches,
    which is all the UI needs for prev/next pagination."""

    items: list[PublicDishOut]
    total: int
    limit: int
    offset: int

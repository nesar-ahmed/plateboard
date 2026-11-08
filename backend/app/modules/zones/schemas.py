"""Schemas for zones (public read model + the create payload used by seeds)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.zones.grid import GRID_MAX
from app.modules.zones.models import NAME_MAX_LENGTH, SLUG_MAX_LENGTH

#: Lowercase words joined by single hyphens: ``old-town``, ``market-square``.
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def normalize_zone_slug(value: str | None) -> str | None:
    """Trim + lowercase a zone reference from a client; blank means "none".

    Shared by every schema that accepts a zone slug, so ``?zone=Old-Town``
    and ``{"zone": " old-town "}`` both mean ``old-town``.
    """
    if value is None:
        return None
    return value.strip().lower() or None


class ZoneOut(BaseModel):
    """A zone as clients see it (the UUID stays internal; ``slug`` is the id)."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    x: int
    y: int


class ZoneCreate(BaseModel):
    """Validated zone definition (seed script / tests - no public write API)."""

    slug: str = Field(max_length=SLUG_MAX_LENGTH, pattern=SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    x: int = Field(ge=0, le=GRID_MAX)
    y: int = Field(ge=0, le=GRID_MAX)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

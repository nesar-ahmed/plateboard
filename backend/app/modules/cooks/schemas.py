"""Schemas for the cook profile endpoints (profile, availability, public page)."""

from __future__ import annotations

import itertools
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.auth.models import TIMEZONE_MAX_LENGTH, CookApplicationStatus
from app.modules.cooks.availability import Availability, is_valid_timezone
from app.modules.reviews.schemas import RatingOut
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
    """Body for the cook application (``POST /api/cooks``) - the kitchen an
    admin will accept or reject."""

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
    verified_at: UTCDateTime | None = Field(
        description="when Plateboard verified the kitchen (null: not verified)"
    )
    status: CookApplicationStatus = Field(
        description="the application: pending | accepted | rejected - only an "
        "accepted kitchen can cook on the platform"
    )
    submitted_at: UTCDateTime = Field(description="latest (re)submission")
    reviewed_at: UTCDateTime | None = Field(description="when an admin decided")
    rejection_reason: str | None = Field(
        description="the admin's explanation of a rejection (may be null)"
    )
    created_at: UTCDateTime
    updated_at: UTCDateTime


# --- availability ---------------------------------------------------------------------

#: "09:30"; closing times may also be "24:00" (midnight at the end of the day).
_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
_HHMM_OR_MIDNIGHT = r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$"
WINDOWS_PER_DAY_MAX = 3


class OpeningWindow(BaseModel):
    """One weekly window in the kitchen's own time zone."""

    day: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    opens: str = Field(pattern=_HHMM, description="HH:MM, kitchen time")
    closes: str = Field(pattern=_HHMM_OR_MIDNIGHT, description="HH:MM or 24:00")

    @model_validator(mode="after")
    def _opens_before_closes(self) -> Self:
        if self.closes != "24:00" and self.closes <= self.opens:
            raise ValueError(
                "closes must be after opens (use 24:00 for midnight; split late nights "
                "across two days)"
            )
        return self


class AvailabilityUpdate(BaseModel):
    """Body for ``PUT /api/cooks/me/availability`` - replaces all three.

    ``hours`` empty = no fixed hours (orders any time). At most
    :data:`WINDOWS_PER_DAY_MAX` windows per day, not overlapping.
    """

    timezone: str = Field(
        max_length=TIMEZONE_MAX_LENGTH, description="IANA zone, e.g. Europe/London"
    )
    orders_paused: bool = False
    hours: list[OpeningWindow] = Field(
        default_factory=list, max_length=7 * WINDOWS_PER_DAY_MAX
    )

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        value = value.strip()
        if not is_valid_timezone(value):
            raise ValueError("unknown time zone (use an IANA name such as Europe/London)")
        return value

    @field_validator("hours")
    @classmethod
    def _sane_week(cls, windows: list[OpeningWindow]) -> list[OpeningWindow]:
        ordered = sorted(windows, key=lambda w: (w.day, w.opens))
        for day in range(7):
            todays = [w for w in ordered if w.day == day]
            if len(todays) > WINDOWS_PER_DAY_MAX:
                raise ValueError(f"at most {WINDOWS_PER_DAY_MAX} windows per day")
            for earlier, later in itertools.pairwise(todays):
                if later.opens < earlier.closes:
                    raise ValueError("windows on the same day must not overlap")
        return ordered


class AvailabilityWindowOut(BaseModel):
    starts_at: UTCDateTime
    ends_at: UTCDateTime


class AvailabilityOut(BaseModel):
    """Whether the kitchen takes orders now, and when over the next 24 hours.

    ``status``: ``open`` / ``closed`` (weekly hours), ``paused`` (switched off
    by the cook) or ``anytime`` (no fixed hours). Times are UTC instants;
    clients show them in the viewer's time.
    """

    status: Literal["open", "closed", "paused", "anytime"]
    accepting_orders: bool = Field(description="an order placed now is taken")
    opens_at: UTCDateTime | None = Field(
        description="closed: the next opening (within a week)"
    )
    closes_at: UTCDateTime | None = Field(description="open: when this window ends")
    next_24h: list[AvailabilityWindowOut] = Field(
        description="taking-orders windows from now to now + 24 h, clipped"
    )
    timezone: str = Field(description="the kitchen's IANA time zone")
    as_of: UTCDateTime = Field(
        description="the instant this was computed for - the start of the 24 h view"
    )

    @classmethod
    def of(cls, availability: Availability) -> AvailabilityOut:
        return cls(
            status=availability.status,
            accepting_orders=availability.accepting_orders,
            opens_at=availability.opens_at,
            closes_at=availability.closes_at,
            next_24h=[
                AvailabilityWindowOut(starts_at=w.starts_at, ends_at=w.ends_at)
                for w in availability.next_24h
            ],
            timezone=availability.timezone,
            as_of=availability.as_of,
        )


class AvailabilitySettingsOut(BaseModel):
    """``GET/PUT /api/cooks/me/availability``: the settings + what they mean now."""

    timezone: str
    orders_paused: bool
    hours: list[OpeningWindow]
    availability: AvailabilityOut


# --- public cook pages ----------------------------------------------------------------


class CookPublicOut(BaseModel):
    """Public cook-profile card: profile fields merged with the account's
    editable identity fields (display name, bio, free-text area), the
    kitchen's grid zone, its verification and whether it takes orders now."""

    user_id: uuid.UUID
    display_name: str | None
    bio: str | None
    area: str | None
    headline: str
    specialties: list[str]
    zone: ZoneOut | None
    verified: bool = Field(description="checked by the Plateboard team")
    verified_at: UTCDateTime | None
    availability: AvailabilityOut
    created_at: UTCDateTime = Field(description="when the kitchen opened on Plateboard")
    rating: RatingOut = Field(default_factory=RatingOut)


class CookPublicStats(BaseModel):
    """The public profile's stats strip - counts, never money.

    Rates and times are null until the kitchen has handled
    ``PUBLIC_STATS_MIN_ORDERS`` orders, so one early rejection can't define a
    new cook; ``new_kitchen`` says so.
    """

    orders_completed: int = Field(description="orders handed over")
    customers: int = Field(description="people who ordered (not cancelled)")
    returning_customers: int = Field(description="...of whom ordered more than once")
    acceptance_rate: float | None = Field(
        description="requests accepted, 0..1 (null below the threshold)"
    )
    average_ready_minutes: float | None = Field(
        description="placed -> ready on average (null below the threshold)"
    )
    new_kitchen: bool = Field(description="too few orders for rates and times yet")


class CookProfilePageOut(CookPublicOut):
    """``GET /api/cooks/{user_id}`` - the card plus the stats strip."""

    stats: CookPublicStats


class CookPage(BaseModel):
    """``GET /api/cooks`` envelope (same pagination contract as dishes)."""

    items: list[CookPublicOut]
    total: int
    limit: int
    offset: int

"""HTTP routes for the cook feature.

``POST /api/cooks`` is the *cook application*: any logged-in user may apply
(201, ``status: pending``); every admin is notified and one of them accepts
or rejects it in the back office. ``GET /api/cooks/me/application`` shows the
caller where their application stands (any state; login only). The
``/api/cooks/me`` profile routes sit behind ``require_cook`` - a role only an
accepted application grants - so applicants and customers see a clean 403.

``GET|PUT /api/cooks/me/availability`` holds when the kitchen takes orders
(time zone, weekly hours, pause switch) and answers what that means right
now and over the next 24 hours.

The trailing ``GET`` routes are public (no auth): a paginated directory of
accepted kitchens (each card with its verification and availability) and one
kitchen's profile page data (plus the stats strip). They must stay *after* ``/me`` in this
module so ``/api/cooks/me`` keeps matching the private route.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.modules.auth.dependencies import CookRequired, LoginRequired
from app.modules.auth.models import CookProfile, User
from app.modules.cooks import service
from app.modules.cooks.schemas import (
    AvailabilityOut,
    AvailabilitySettingsOut,
    AvailabilityUpdate,
    CookCreateRequest,
    CookOut,
    CookPage,
    CookPatchRequest,
    CookProfilePageOut,
    CookPublicOut,
    OpeningWindow,
)
from app.modules.reviews import service as review_service
from app.modules.reviews.schemas import rating_out
from app.modules.zones.schemas import ZoneOut

cook_router = APIRouter(prefix="/api/cooks", tags=["cooks"])

DEFAULT_PAGE_SIZE = 20


def _public_out(
    profile: CookProfile, user: User, rating: review_service.Rating | None = None
) -> CookPublicOut:
    """Merge the cook row with the account's public identity fields, its
    verification and whether it takes orders right now."""
    return CookPublicOut(
        user_id=profile.user_id,
        display_name=user.display_name,
        bio=user.bio,
        area=user.area,
        headline=profile.headline,
        specialties=list(profile.specialties),
        zone=ZoneOut.model_validate(profile.zone) if profile.zone else None,
        verified=profile.verified_at is not None,
        verified_at=profile.verified_at,
        availability=AvailabilityOut.of(service.availability_of(profile)),
        created_at=profile.created_at,
        rating=rating_out(rating),
    )


def _settings_out(profile: CookProfile) -> AvailabilitySettingsOut:
    return AvailabilitySettingsOut(
        timezone=profile.timezone,
        orders_paused=profile.orders_paused,
        hours=[OpeningWindow.model_validate(window) for window in profile.opening_hours],
        availability=AvailabilityOut.of(service.availability_of(profile)),
    )


@cook_router.post("", response_model=CookOut, status_code=201)
async def become_cook(
    payload: CookCreateRequest, user: LoginRequired, db: DbSession
) -> CookOut:
    """Apply to cook (or apply again after a rejection). The kitchen starts
    ``pending`` - cook endpoints stay 403 until an admin accepts it. 409
    ``already_cook`` / ``application_pending``; 422 ``unknown_zone``."""
    profile = await service.become_cook(db, user, payload)
    return CookOut.model_validate(profile)


@cook_router.get("/me/application", response_model=CookOut)
async def my_application(user: LoginRequired, db: DbSession) -> CookOut:
    """My cook application in any state - ``pending``, ``accepted`` or
    ``rejected`` (with the admin's ``rejection_reason``). 404
    ``no_application`` if I never applied."""
    return CookOut.model_validate(await service.get_application(db, user.id))


@cook_router.get("/me", response_model=CookOut)
async def my_cook_profile(user: CookRequired, db: DbSession) -> CookOut:
    profile = await service.get_cook(db, user.id)
    return CookOut.model_validate(profile)


@cook_router.patch("/me", response_model=CookOut)
async def patch_my_cook_profile(
    payload: CookPatchRequest, user: CookRequired, db: DbSession
) -> CookOut:
    profile = await service.get_cook(db, user.id)
    updated = await service.update_cook(db, profile, payload)
    return CookOut.model_validate(updated)


@cook_router.get("/me/availability", response_model=AvailabilitySettingsOut)
async def my_availability(user: CookRequired, db: DbSession) -> AvailabilitySettingsOut:
    return _settings_out(await service.get_cook(db, user.id))


@cook_router.put("/me/availability", response_model=AvailabilitySettingsOut)
async def put_my_availability(
    payload: AvailabilityUpdate, user: CookRequired, db: DbSession
) -> AvailabilitySettingsOut:
    """Replace time zone, weekly hours and pause switch. ``hours: []`` = no
    fixed hours (orders any time); ``orders_paused: true`` stops new orders
    until switched back. Orders are only placed while the kitchen takes them
    (409 ``kitchen_closed`` otherwise)."""
    profile = await service.get_cook(db, user.id)
    return _settings_out(await service.update_availability(db, profile, payload))


# --- public directory (no auth) - keep these AFTER /me so "/api/cooks/me" ---
# --- keeps matching the private route above ----------------------------------


@cook_router.get("", response_model=CookPage)
async def list_cooks(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CookPage:
    total, pairs = await service.page_cooks(db, limit=limit, offset=offset)
    ratings = await review_service.cook_ratings(db, (p.user_id for p, _u in pairs))
    return CookPage(
        items=[
            _public_out(profile, user, ratings.get(profile.user_id))
            for profile, user in pairs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@cook_router.get("/{user_id}", response_model=CookProfilePageOut)
async def get_cook_profile(user_id: uuid.UUID, db: DbSession) -> CookProfilePageOut:
    """The public profile page: the card plus the stats strip (counts, never
    money; rates and times only once the kitchen has answered enough orders)."""
    profile, user = await service.get_public_cook(db, user_id)
    ratings = await review_service.cook_ratings(db, [user_id])
    return CookProfilePageOut(
        **_public_out(profile, user, ratings.get(user_id)).model_dump(),
        stats=await service.public_stats(db, user_id),
    )

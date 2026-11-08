"""HTTP routes for the cook feature.

``POST /api/cooks`` is the *become-a-cook* action: any logged-in user may
create their cook profile. The two ``/me`` variants sit behind
``require_cook``, so non-cooks see a clean 403.

The trailing ``GET`` routes are public (no auth): a paginated cook directory
and one cook's profile page data. They must stay *after* ``/me`` in this
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
    CookCreateRequest,
    CookOut,
    CookPage,
    CookPatchRequest,
    CookPublicOut,
)
from app.modules.zones.schemas import ZoneOut

cook_router = APIRouter(prefix="/api/cooks", tags=["cooks"])

DEFAULT_PAGE_SIZE = 20


def _public_out(profile: CookProfile, user: User) -> CookPublicOut:
    """Merge the cook row with the account's public identity fields."""
    return CookPublicOut(
        user_id=profile.user_id,
        display_name=user.display_name,
        bio=user.bio,
        area=user.area,
        headline=profile.headline,
        specialties=list(profile.specialties),
        zone=ZoneOut.model_validate(profile.zone) if profile.zone else None,
        created_at=profile.created_at,
    )


@cook_router.post("", response_model=CookOut, status_code=201)
async def become_cook(
    payload: CookCreateRequest, user: LoginRequired, db: DbSession
) -> CookOut:
    profile = await service.become_cook(db, user, payload)
    return CookOut.model_validate(profile)


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


# --- public directory (no auth) - keep these AFTER /me so "/api/cooks/me" ---
# --- keeps matching the private route above ----------------------------------


@cook_router.get("", response_model=CookPage)
async def list_cooks(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CookPage:
    total, pairs = await service.page_cooks(db, limit=limit, offset=offset)
    return CookPage(
        items=[_public_out(profile, user) for profile, user in pairs],
        total=total,
        limit=limit,
        offset=offset,
    )


@cook_router.get("/{user_id}", response_model=CookPublicOut)
async def get_cook_profile(user_id: uuid.UUID, db: DbSession) -> CookPublicOut:
    profile, user = await service.get_public_cook(db, user_id)
    return _public_out(profile, user)

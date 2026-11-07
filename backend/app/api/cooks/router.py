"""HTTP routes for the cook feature.

``POST /api/cooks`` is the *become-a-cook* action: any logged-in user may
create their cook profile. The two ``/me`` variants sit behind
``require_cook``, so non-cooks see a clean 403.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.auth.dependencies import CookRequired, LoginRequired
from app.api.cooks import service
from app.api.cooks.schemas import CookCreateRequest, CookOut, CookPatchRequest
from app.api.deps import DbSession

cook_router = APIRouter(prefix="/api/cooks", tags=["cooks"])


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

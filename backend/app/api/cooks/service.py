"""Cook-profile business logic."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.models import ROLE_COOK, CookProfile, User
from app.api.cooks.schemas import CookCreateRequest, CookPatchRequest
from app.core.exceptions import AppError


class AlreadyCookError(AppError):
    status_code = 409
    code = "already_cook"
    default_message = "This account is already a cook"


class CookRequiredError(AppError):
    """Role says cook but the profile row is gone - treat as not-a-cook."""

    status_code = 403
    code = "forbidden"
    default_message = "This action requires a cook profile"


async def become_cook(
    session: AsyncSession, user: User, payload: CookCreateRequest
) -> CookProfile:
    """Create the cook profile and add the cook role - both in one commit.

    Existing customers keep being customers: roles grow, never replace.
    The profile is fetched with an explicit ``get`` - touching the lazy
    ``user.cook_profile`` relationship would trigger IO outside await.
    """
    existing = await session.get(CookProfile, user.id)
    if user.is_cook or existing is not None:
        raise AlreadyCookError
    profile = CookProfile(
        user_id=user.id,
        headline=payload.headline,
        specialties=list(payload.specialties),
    )
    user.roles = [*(user.roles or []), ROLE_COOK]
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError:  # concurrent become-cook for the same account
        await session.rollback()
        raise AlreadyCookError from None
    await session.refresh(profile)
    return profile


async def get_cook(session: AsyncSession, user_id: uuid.UUID) -> CookProfile:
    profile = await session.get(CookProfile, user_id)
    if profile is None:
        raise CookRequiredError
    return profile


async def update_cook(
    session: AsyncSession, profile: CookProfile, payload: CookPatchRequest
) -> CookProfile:
    if payload.headline is not None:
        profile.headline = payload.headline
    if payload.specialties is not None:
        profile.specialties = list(payload.specialties)
    await session.commit()
    await session.refresh(profile)
    return profile

"""Cook-profile business logic."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.modules.auth.models import ROLE_COOK, CookProfile, User
from app.modules.cooks.schemas import CookCreateRequest, CookPatchRequest
from app.modules.zones.service import resolve_zone


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
    zone = await resolve_zone(session, payload.zone) if payload.zone else None
    profile = CookProfile(
        user_id=user.id,
        headline=payload.headline,
        specialties=list(payload.specialties),
        zone=zone,
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
    if payload.zone_sent:
        # Assign the relationship (not just zone_id) so the response carries
        # the new zone without another round trip; null clears it.
        profile.zone = (
            await resolve_zone(session, payload.zone) if payload.zone else None
        )
    await session.commit()
    await session.refresh(profile)
    return profile


class CookProfileNotFoundError(NotFoundError):
    default_message = "Cook profile not found"


async def page_cooks(
    session: AsyncSession, *, limit: int = 20, offset: int = 0
) -> tuple[int, list[tuple[CookProfile, User]]]:
    """Public directory: every cook profile with its account, newest first.

    ``total`` covers all profiles so the UI can paginate; rows carry the
    ``User`` so the router can render display_name/bio/area without extra
    queries. Only accounts that completed the become-a-cook action appear -
    the role list alone is not enough to have a public page.
    """
    total = (
        await session.scalar(select(func.count()).select_from(CookProfile))
    ) or 0
    stmt = (
        select(CookProfile, User)
        .join(User, User.id == CookProfile.user_id)
        .order_by(
            CookProfile.created_at.desc(),
            # tie-breaker so paging within the same second is deterministic
            CookProfile.user_id,
        )
        .limit(limit)
        .offset(offset)
    )
    return total, [(profile, user) for profile, user in (await session.execute(stmt)).all()]


async def get_public_cook(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[CookProfile, User]:
    stmt = (
        select(CookProfile, User)
        .join(User, User.id == CookProfile.user_id)
        .where(CookProfile.user_id == user_id)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise CookProfileNotFoundError
    return row[0], row[1]

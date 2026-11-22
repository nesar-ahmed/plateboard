"""Cook-profile business logic: the application, profiles, availability,
public stats.

Becoming a cook is an *application*: ``POST /api/cooks`` creates the kitchen
profile as ``pending`` and tells every admin; an admin accepts it (which adds
the ``cook`` role) or rejects it (``app.modules.admin.service``). Until then
every cook-only endpoint answers 403 and the kitchen is invisible to the
public; after a rejection the applicant may apply again. Only ``accepted``
kitchens are listed in the directory or have a public page.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.modules.auth.models import CookApplicationStatus, CookProfile, User
from app.modules.cooks.availability import Availability, compute_availability
from app.modules.cooks.schemas import (
    AvailabilityUpdate,
    CookCreateRequest,
    CookPatchRequest,
    CookPublicStats,
)
from app.modules.dashboards import service as dashboards
from app.modules.notifications import service as notifications
from app.modules.notifications.catalog import CookApplicationPayload, NotificationType
from app.modules.orders.models import Order, OrderStatus
from app.modules.zones.service import resolve_zone
from app.shared.base import utcnow
from app.shared.sql import minutes_between

#: Orders a kitchen must have answered (accepted or rejected) before its
#: public rates and times show - one early rejection must not define it.
PUBLIC_STATS_MIN_ORDERS = 5


class AlreadyCookError(AppError):
    status_code = 409
    code = "already_cook"
    default_message = "This account is already a cook"


class ApplicationPendingError(AppError):
    status_code = 409
    code = "application_pending"
    default_message = "Your cook application is waiting for review"


class NoApplicationError(AppError):
    status_code = 404
    code = "no_application"
    default_message = "You have not applied to cook yet"


class CookRequiredError(AppError):
    """Role says cook but the profile row is gone - treat as not-a-cook."""

    status_code = 403
    code = "forbidden"
    default_message = "This action requires a cook profile"


async def become_cook(
    session: AsyncSession, user: User, payload: CookCreateRequest
) -> CookProfile:
    """Submit the cook application - or resubmit it after a rejection.

    The kitchen profile is created (or updated) as ``pending`` and every
    admin is notified; the account gains the ``cook`` role only when an admin
    accepts it. An accepted kitchen is 409 ``already_cook``, an open
    application 409 ``application_pending``. The profile is fetched with an
    explicit ``get`` - touching the lazy ``user.cook_profile`` relationship
    would trigger IO outside await.
    """
    existing = await session.get(CookProfile, user.id)
    if user.is_cook or (existing is not None and existing.is_accepted):
        raise AlreadyCookError
    if existing is not None and existing.status == CookApplicationStatus.PENDING.value:
        raise ApplicationPendingError
    zone = await resolve_zone(session, payload.zone) if payload.zone else None
    if existing is None:
        profile = CookProfile(user_id=user.id)
        session.add(profile)
    else:  # rejected before: a fresh submission replaces the old one
        profile = existing
        profile.reviewed_at = None
        profile.reviewed_by_id = None
        profile.rejection_reason = None
    profile.headline = payload.headline
    profile.specialties = list(payload.specialties)
    profile.zone = zone
    profile.status = CookApplicationStatus.PENDING.value
    profile.submitted_at = utcnow()
    try:
        await notifications.notify_admins(
            session,
            kind=NotificationType.COOK_APPLICATION_SUBMITTED,
            payload=CookApplicationPayload(
                applicant_name=user.display_name, headline=payload.headline
            ),
            subject_id=user.id,
            actor_id=user.id,
        )
        await session.commit()
    except IntegrityError:  # concurrent application for the same account
        await session.rollback()
        raise ApplicationPendingError from None
    await session.refresh(profile)
    return profile


async def get_application(session: AsyncSession, user_id: uuid.UUID) -> CookProfile:
    """The caller's cook application in any state (404 ``no_application``)."""
    profile = await session.get(CookProfile, user_id)
    if profile is None:
        raise NoApplicationError
    return profile


async def get_cook(session: AsyncSession, user_id: uuid.UUID) -> CookProfile:
    """The caller's *accepted* kitchen - the cook role alone is not enough."""
    profile = await session.get(CookProfile, user_id)
    if profile is None or not profile.is_accepted:
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


#: Public reads only ever see kitchens an admin accepted.
_ACCEPTED = CookProfile.status == CookApplicationStatus.ACCEPTED.value


async def page_cooks(
    session: AsyncSession, *, limit: int = 20, offset: int = 0
) -> tuple[int, list[tuple[CookProfile, User]]]:
    """Public directory: every *accepted* kitchen with its account, newest
    first.

    ``total`` covers all of them so the UI can paginate; rows carry the
    ``User`` so the router can render display_name/bio/area without extra
    queries. Pending and rejected applications never appear - the role list
    alone is not enough to have a public page either.
    """
    total = (
        await session.scalar(
            select(func.count()).select_from(CookProfile).where(_ACCEPTED)
        )
    ) or 0
    stmt = (
        select(CookProfile, User)
        .join(User, User.id == CookProfile.user_id)
        .where(_ACCEPTED)
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
        .where(CookProfile.user_id == user_id, _ACCEPTED)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise CookProfileNotFoundError
    return row[0], row[1]


# --- availability ---------------------------------------------------------------------


def availability_of(profile: CookProfile, now: datetime | None = None) -> Availability:
    """Whether the kitchen takes orders at ``now`` (default: this instant)."""
    return compute_availability(
        hours=profile.opening_hours or [],
        timezone=profile.timezone,
        paused=profile.orders_paused,
        now=now or utcnow(),
    )


async def update_availability(
    session: AsyncSession, profile: CookProfile, payload: AvailabilityUpdate
) -> CookProfile:
    """Replace the time zone, the weekly hours and the pause switch (PUT)."""
    profile.timezone = payload.timezone
    profile.orders_paused = payload.orders_paused
    profile.opening_hours = [window.model_dump() for window in payload.hours]
    await session.commit()
    await session.refresh(profile)
    return profile


# --- public stats ---------------------------------------------------------------------


async def public_stats(session: AsyncSession, cook_id: uuid.UUID) -> CookPublicStats:
    """The public profile's stats strip. Counts only - never money - and the
    same definitions as the cook's own dashboard (acceptance rate, customers)."""
    completed = (
        await session.scalar(
            select(func.count()).where(
                Order.cook_id == cook_id, Order.status == OrderStatus.COMPLETED.value
            )
        )
    ) or 0
    customers = await dashboards.customer_stats(session, cook_id)
    performance = await dashboards.kitchen_performance(session, cook_id)
    new_kitchen = performance.accepted + performance.rejected < PUBLIC_STATS_MIN_ORDERS
    ready = await session.scalar(
        select(func.avg(minutes_between(Order.created_at, Order.ready_at))).where(
            Order.cook_id == cook_id, Order.ready_at.is_not(None)
        )
    )
    return CookPublicStats(
        orders_completed=completed,
        customers=customers.unique,
        returning_customers=customers.repeat,
        acceptance_rate=None if new_kitchen else performance.acceptance_rate,
        average_ready_minutes=None
        if new_kitchen or ready is None
        else round(float(ready), 1),
        new_kitchen=new_kitchen,
    )

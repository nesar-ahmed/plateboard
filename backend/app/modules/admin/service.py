"""Back office: every account (with activity, filterable), cook
applications and cook verification.

The admin role observes the platform (lists + the admin dashboard) and
changes two things about kitchens:

* the **cook application** - ``accept_application`` (adds the ``cook`` role:
  the kitchen opens) or ``reject_application`` (always with a reason),
  each only while the application is ``pending`` (compare-and-set: when two
  admins decide at once, the second gets 409 ``application_not_pending``);
* the **verification** of an accepted kitchen - the public "verified" badge
  (``verify_cook`` / ``revoke_cook``, idempotent).

Each decision notifies the cook in the same transaction (only on a real
change), and an application's "new cook application" notifications are
marked read for every admin once it is decided. Orders and menus stay with
their cooks and customers. Orders for admins reuse
``orders.service.page_orders`` unscoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.auth.models import (
    ROLE_COOK,
    CookApplicationStatus,
    CookProfile,
    User,
    UserSession,
)
from app.modules.notifications import service as notifications
from app.modules.notifications.catalog import (
    CookApplicationPayload,
    NoPayload,
    NotificationType,
)
from app.modules.notifications.models import Audience
from app.modules.orders.models import Order
from app.shared.base import utcnow
from app.shared.sql import folded_contains, json_array_contains
from app.shared.text import search_terms


def _user_filters(role: str | None, query: str | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if role is not None:
        conditions.append(json_array_contains(User.roles, role))
    for term in search_terms(query):  # every word in the email or the name
        conditions.append(
            or_(
                folded_contains(User.email, term),
                folded_contains(User.display_name, term),
            )
        )
    return conditions


def _with_activity(stmt: Select[Any]) -> Select[Any]:
    """Add last login, order counts and the cook verification as correlated
    scalar subqueries."""
    last_login = (
        select(func.max(UserSession.created_at))
        .where(UserSession.user_id == User.id)
        .scalar_subquery()
    )
    placed = select(func.count()).where(Order.customer_id == User.id).scalar_subquery()
    received = select(func.count()).where(Order.cook_id == User.id).scalar_subquery()
    verified = (
        select(CookProfile.verified_at)
        .where(CookProfile.user_id == User.id)
        .scalar_subquery()
    )
    application = (
        select(CookProfile.status)
        .where(CookProfile.user_id == User.id)
        .scalar_subquery()
    )
    return stmt.add_columns(last_login, placed, received, verified, application)


type UserRow = tuple[User, datetime | None, int, int, datetime | None, str | None]


async def page_users(
    session: AsyncSession,
    *,
    role: str | None = None,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[UserRow]]:
    """Newest accounts first: ``(total, [(user, last_login, placed, received,
    cook_verified_at, cook_application_status)])``."""
    conditions = _user_filters(role, query)
    total = await session.scalar(
        select(func.count()).select_from(User).where(*conditions)
    )
    stmt = (
        _with_activity(select(User))
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return total or 0, [
        (row[0], row[1], row[2] or 0, row[3] or 0, row[4], row[5]) for row in rows
    ]


# --- cook applications ---------------------------------------------------------------


class ApplicationNotFoundError(NotFoundError):
    default_message = "Cook application not found"


class ApplicationNotPendingError(ConflictError):
    """Already decided (possibly by another admin a moment ago)."""

    code = "application_not_pending"
    default_message = "This application has already been decided"

    def __init__(self, status: str) -> None:
        super().__init__(
            f"This application is already {status}", details={"status": status}
        )


async def page_applications(
    session: AsyncSession,
    *,
    status: CookApplicationStatus | None = CookApplicationStatus.PENDING,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[tuple[CookProfile, User]]]:
    """Applications with their applicants. Pending ones come oldest first -
    the review queue, first come first served; any other selection newest
    first. ``status=None`` lists every application."""
    conditions = [] if status is None else [CookProfile.status == status.value]
    total = await session.scalar(
        select(func.count()).select_from(CookProfile).where(*conditions)
    )
    oldest_first = status is CookApplicationStatus.PENDING
    stmt = (
        select(CookProfile, User)
        .join(User, User.id == CookProfile.user_id)
        .where(*conditions)
        .order_by(
            CookProfile.submitted_at.asc()
            if oldest_first
            else CookProfile.submitted_at.desc(),
            CookProfile.user_id,
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    return total or 0, [(profile, user) for profile, user in rows]


async def get_application(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[CookProfile, User]:
    row = (
        await session.execute(
            select(CookProfile, User)
            .join(User, User.id == CookProfile.user_id)
            .where(CookProfile.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise ApplicationNotFoundError
    return row[0], row[1]


async def _decide(
    session: AsyncSession,
    user_id: uuid.UUID,
    admin_id: uuid.UUID | None,
    decision: CookApplicationStatus,
    reason: str | None,
) -> tuple[CookProfile, User]:
    """Compare-and-set pending -> ``decision``, grant the role on acceptance,
    notify the applicant, resolve the admins' notifications - one commit."""
    profile, user = await get_application(session, user_id)
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(CookProfile)
            .where(
                CookProfile.user_id == user_id,
                CookProfile.status == CookApplicationStatus.PENDING.value,
            )
            .values(
                status=decision.value,
                reviewed_at=utcnow(),
                reviewed_by_id=admin_id,
                rejection_reason=reason,
            )
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount != 1:
        await session.rollback()
        profile, _user = await get_application(session, user_id)
        raise ApplicationNotPendingError(profile.status)

    accepted = decision is CookApplicationStatus.ACCEPTED
    if accepted:
        # Roles grow, never replace: the applicant stays a customer too.
        user.roles = list(dict.fromkeys([*(user.roles or []), ROLE_COOK]))
    await notifications.notify(
        session,
        recipient_id=user_id,
        audience=Audience.ACCOUNT,
        kind=NotificationType.COOK_APPLICATION_ACCEPTED
        if accepted
        else NotificationType.COOK_APPLICATION_REJECTED,
        payload=CookApplicationPayload(
            applicant_name=user.display_name, headline=profile.headline, reason=reason
        ),
        subject_id=user_id,
        actor_id=admin_id,
    )
    await notifications.resolve(
        session, kind=NotificationType.COOK_APPLICATION_SUBMITTED, subject_id=user_id
    )
    await session.commit()
    return await get_application(session, user_id)


async def accept_application(
    session: AsyncSession, user_id: uuid.UUID, admin_id: uuid.UUID | None
) -> tuple[CookProfile, User]:
    """Open the kitchen: status ``accepted`` and the ``cook`` role.
    ``admin_id`` is the deciding admin (``None``: an operator script)."""
    return await _decide(
        session, user_id, admin_id, CookApplicationStatus.ACCEPTED, reason=None
    )


async def reject_application(
    session: AsyncSession,
    user_id: uuid.UUID,
    admin_id: uuid.UUID | None,
    reason: str,
) -> tuple[CookProfile, User]:
    """Turn the application down; ``reason`` (required - the API refuses a
    blank one) is shown to the applicant, who may apply again."""
    return await _decide(
        session, user_id, admin_id, CookApplicationStatus.REJECTED, reason=reason
    )


# --- cook verification -------------------------------------------------------------


class KitchenNotFoundError(NotFoundError):
    """No accepted kitchen behind this id (not a cook, an application still
    pending or rejected, or no such account)."""

    default_message = "Kitchen not found"


async def _kitchen(session: AsyncSession, cook_id: uuid.UUID) -> CookProfile:
    profile = await session.get(CookProfile, cook_id)
    if profile is None or not profile.is_accepted:
        raise KitchenNotFoundError
    return profile


async def _tell_kitchen(
    session: AsyncSession,
    cook_id: uuid.UUID,
    admin_id: uuid.UUID,
    kind: NotificationType,
) -> None:
    await notifications.notify(
        session,
        recipient_id=cook_id,
        audience=Audience.COOK,
        kind=kind,
        payload=NoPayload(),
        subject_id=cook_id,
        actor_id=admin_id,
    )


async def verify_cook(
    session: AsyncSession, cook_id: uuid.UUID, admin_id: uuid.UUID
) -> CookProfile:
    """Mark the kitchen verified and tell the cook. Idempotent: verifying
    again keeps the original date and verifier (the badge means "checked
    since") and notifies nobody."""
    profile = await _kitchen(session, cook_id)
    if profile.verified_at is None:
        profile.verified_at = utcnow()
        profile.verified_by_id = admin_id
        await _tell_kitchen(
            session, cook_id, admin_id, NotificationType.KITCHEN_VERIFIED
        )
        await session.commit()
        await session.refresh(profile)
    return profile


async def revoke_cook(
    session: AsyncSession, cook_id: uuid.UUID, admin_id: uuid.UUID
) -> CookProfile:
    """Take the badge away and tell the cook (idempotent, like verifying)."""
    profile = await _kitchen(session, cook_id)
    if profile.verified_at is not None:
        profile.verified_at = None
        profile.verified_by_id = None
        await _tell_kitchen(
            session, cook_id, admin_id, NotificationType.KITCHEN_VERIFICATION_REVOKED
        )
        await session.commit()
        await session.refresh(profile)
    return profile

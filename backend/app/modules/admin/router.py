"""HTTP routes for the admin back office (role: admin; 401 before 403).

* GET /api/admin/users   - every account with roles and activity
  (``?role=customer|cook|admin``, ``?q=`` over email + display name)
* GET /api/admin/orders  - every order (``?status=`` repeatable, ``?cook_id=``,
  ``?customer_id=``)

Both paginate with ``limit``/``offset``, newest first. The admin dashboard is
``GET /api/admin/dashboard`` (``app.modules.dashboards``).

* GET  /api/admin/cook-applications       - the review queue (``?status=``,
  default ``pending``, oldest first; ``all`` = every application)
* POST /api/admin/cook-applications/{user_id}/accept - open the kitchen: the
  applicant gains the ``cook`` role
* POST /api/admin/cook-applications/{user_id}/reject - with the required
  ``reason`` shown to the applicant (who may apply again)

Deciding is only possible while the application is ``pending`` (409
``application_not_pending`` - e.g. another admin was faster); the applicant
is notified either way.

* POST   /api/admin/cooks/{user_id}/verification - verify the kitchen (the
  public "verified" badge); idempotent
* DELETE /api/admin/cooks/{user_id}/verification - revoke it; idempotent

Both answer the kitchen's verification (the cook is notified when it
changes); an id without an accepted kitchen is 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminUserOut,
    AdminUserPage,
    CookApplicationOut,
    CookApplicationPage,
    CookApplicationRejectRequest,
    CookVerificationOut,
)
from app.modules.auth.dependencies import AdminRequired
from app.modules.auth.models import CookApplicationStatus, CookProfile, User
from app.modules.dishes.schemas import SEARCH_MAX_LENGTH
from app.modules.orders import service as order_service
from app.modules.orders.models import OrderStatus
from app.modules.orders.schemas import OrderPage, order_out
from app.modules.zones.schemas import ZoneOut

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100, description="page size")]
PageOffset = Annotated[int, Query(ge=0, description="rows to skip")]


@admin_router.get("/users", response_model=AdminUserPage)
async def list_users(
    _admin: AdminRequired,
    db: DbSession,
    role: Annotated[
        Literal["customer", "cook", "admin"] | None,
        Query(description="holding this role"),
    ] = None,
    q: Annotated[
        str | None,
        Query(max_length=SEARCH_MAX_LENGTH, description="words in the email or name"),
    ] = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> AdminUserPage:
    total, rows = await service.page_users(
        db, role=role, query=q, limit=limit, offset=offset
    )
    return AdminUserPage(
        items=[
            AdminUserOut(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                area=user.area,
                roles=list(user.roles),
                created_at=user.created_at,
                last_login_at=last_login,
                orders_placed=placed,
                orders_received=received,
                verified_at=verified_at,
                cook_application=CookApplicationStatus(application)
                if application
                else None,
            )
            for user, last_login, placed, received, verified_at, application in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.get("/orders", response_model=OrderPage)
async def list_orders(
    _admin: AdminRequired,
    db: DbSession,
    status: Annotated[
        list[OrderStatus] | None, Query(description="repeatable: any of these statuses")
    ] = None,
    cook_id: Annotated[
        uuid.UUID | None, Query(description="placed with this cook")
    ] = None,
    customer_id: Annotated[
        uuid.UUID | None, Query(description="placed by this customer")
    ] = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> OrderPage:
    total, views = await order_service.page_orders(
        db,
        customer_id=customer_id,
        cook_id=cook_id,
        status=status or [],
        limit=limit,
        offset=offset,
    )
    return OrderPage(
        items=[order_out(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
    )


def _application_out(profile: CookProfile, user: User) -> CookApplicationOut:
    return CookApplicationOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        area=user.area,
        bio=user.bio,
        headline=profile.headline,
        specialties=list(profile.specialties),
        zone=ZoneOut.model_validate(profile.zone) if profile.zone else None,
        status=CookApplicationStatus(profile.status),
        submitted_at=profile.submitted_at,
        reviewed_at=profile.reviewed_at,
        reviewed_by=profile.reviewed_by_id,
        rejection_reason=profile.rejection_reason,
    )


@admin_router.get("/cook-applications", response_model=CookApplicationPage)
async def list_cook_applications(
    _admin: AdminRequired,
    db: DbSession,
    status: Annotated[
        Literal["pending", "accepted", "rejected", "all"],
        Query(description="pending (default, oldest first) | accepted | rejected | all"),
    ] = "pending",
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> CookApplicationPage:
    total, rows = await service.page_applications(
        db,
        status=None if status == "all" else CookApplicationStatus(status),
        limit=limit,
        offset=offset,
    )
    return CookApplicationPage(
        items=[_application_out(profile, user) for profile, user in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "/cook-applications/{user_id}/accept", response_model=CookApplicationOut
)
async def accept_cook_application(
    user_id: uuid.UUID, admin: AdminRequired, db: DbSession
) -> CookApplicationOut:
    """Accept a pending application: the kitchen opens (``cook`` role) and the
    applicant is notified. 404 unknown; 409 ``application_not_pending``."""
    return _application_out(*await service.accept_application(db, user_id, admin.id))


@admin_router.post(
    "/cook-applications/{user_id}/reject", response_model=CookApplicationOut
)
async def reject_cook_application(
    user_id: uuid.UUID,
    admin: AdminRequired,
    db: DbSession,
    payload: CookApplicationRejectRequest,
) -> CookApplicationOut:
    """Reject a pending application with a ``reason`` (required, <= 300
    chars) the applicant sees; they may apply again. 422 without a reason;
    404 unknown; 409 ``application_not_pending``."""
    return _application_out(
        *await service.reject_application(db, user_id, admin.id, payload.reason)
    )


def _verification_out(profile: CookProfile) -> CookVerificationOut:
    return CookVerificationOut(
        user_id=profile.user_id,
        verified=profile.verified_at is not None,
        verified_at=profile.verified_at,
        verified_by=profile.verified_by_id,
    )


@admin_router.post("/cooks/{user_id}/verification", response_model=CookVerificationOut)
async def verify_cook(
    user_id: uuid.UUID, admin: AdminRequired, db: DbSession
) -> CookVerificationOut:
    """Verify a kitchen after checking it - its public page and card show the
    badge. Verifying again changes nothing (the first date stays)."""
    return _verification_out(await service.verify_cook(db, user_id, admin.id))


@admin_router.delete("/cooks/{user_id}/verification", response_model=CookVerificationOut)
async def revoke_cook_verification(
    user_id: uuid.UUID, admin: AdminRequired, db: DbSession
) -> CookVerificationOut:
    """Take the badge away (idempotent)."""
    return _verification_out(await service.revoke_cook(db, user_id, admin.id))

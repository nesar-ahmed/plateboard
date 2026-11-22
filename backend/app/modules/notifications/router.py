"""HTTP routes for the signed-in user's notification inbox (login required).

* GET    /api/me/notifications               - newest first (``?audience=``,
                                               ``?unread=true``, paging) +
                                               the inbox's unread count
* GET    /api/me/notifications/unread-count  - unread per panel (badges)
* POST   /api/me/notifications/read-all      - mark all read (optionally one
                                               panel, and only up to ``before``)
* PATCH  /api/me/notifications/{id}          - ``{"read": true|false}``
* DELETE /api/me/notifications/{id}          - dismiss

``audience`` is the panel: ``account`` (everyone), ``cook`` and ``admin``
(role required - 403 otherwise; 401 still wins for anonymous callers).
Without it, every inbox the caller can see is included. Someone else's
notification id is a 404. Notifications are *written* by the feature
services (``service.notify``), never through this API.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession
from app.modules.auth.dependencies import LoginRequired
from app.modules.notifications import service
from app.modules.notifications.models import Audience
from app.modules.notifications.schemas import (
    MarkAllReadOut,
    MarkAllReadRequest,
    NotificationOut,
    NotificationPage,
    NotificationPatch,
    UnreadCountOut,
    notification_out,
)

notification_router = APIRouter(prefix="/api/me/notifications", tags=["notifications"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100, description="page size")]
PageOffset = Annotated[int, Query(ge=0, description="rows to skip")]
AudienceFilter = Annotated[
    Audience | None,
    Query(description="one panel's inbox (default: every inbox the caller can see)"),
]


@notification_router.get("", response_model=NotificationPage)
async def list_notifications(
    user: LoginRequired,
    db: DbSession,
    audience: AudienceFilter = None,
    unread: Annotated[bool, Query(description="only unread notifications")] = False,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> NotificationPage:
    """``unread`` in the answer counts the unread notifications of the listed
    inbox(es) whatever the ``unread`` filter - one call draws list + badge."""
    total, unread_count, rows = await service.page_notifications(
        db, user, audience=audience, unread_only=unread, limit=limit, offset=offset
    )
    return NotificationPage(
        items=[notification_out(row) for row in rows],
        total=total,
        unread=unread_count,
        limit=limit,
        offset=offset,
    )


@notification_router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(user: LoginRequired, db: DbSession) -> UnreadCountOut:
    """Cheap enough to poll (a partial index over unread rows)."""
    counts = await service.unread_counts(db, user)
    return UnreadCountOut(
        total=sum(counts.values()),
        account=counts[Audience.ACCOUNT],
        cook=counts[Audience.COOK],
        admin=counts[Audience.ADMIN],
    )


@notification_router.post("/read-all", response_model=MarkAllReadOut)
async def mark_all_read(
    user: LoginRequired, db: DbSession, payload: MarkAllReadRequest | None = None
) -> MarkAllReadOut:
    """No body = every visible inbox, everything so far. Pass ``before`` (the
    newest notification on screen) so one that arrives meanwhile stays unread."""
    payload = payload or MarkAllReadRequest()
    marked = await service.mark_all_read(
        db, user, audience=payload.audience, before=payload.before
    )
    return MarkAllReadOut(marked=marked)


@notification_router.patch("/{notification_id}", response_model=NotificationOut)
async def patch_notification(
    notification_id: uuid.UUID,
    payload: NotificationPatch,
    user: LoginRequired,
    db: DbSession,
) -> NotificationOut:
    row = await service.get_visible(db, notification_id, user)
    return notification_out(await service.set_read(db, row, read=payload.read))


@notification_router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: uuid.UUID, user: LoginRequired, db: DbSession
) -> Response:
    row = await service.get_visible(db, notification_id, user)
    await service.delete_notification(db, row)
    return Response(status_code=204)

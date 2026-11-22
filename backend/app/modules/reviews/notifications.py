from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications import service as notifications
from app.modules.notifications.catalog import NotificationType, ReviewPayload
from app.modules.notifications.models import Audience
from app.modules.reviews.models import Review

COMMENT_EXCERPT_LENGTH = 140


def _excerpt(comment: str | None) -> str | None:
    if comment is None or len(comment) <= COMMENT_EXCERPT_LENGTH:
        return comment
    return comment[: COMMENT_EXCERPT_LENGTH - 1].rstrip() + "…"


async def review_posted(
    session: AsyncSession,
    review: Review,
    *,
    customer_name: str | None,
    at: datetime | None = None,
) -> None:
    await notifications.notify(
        session,
        recipient_id=review.cook_id,
        audience=Audience.COOK,
        kind=NotificationType.REVIEW_POSTED,
        payload=ReviewPayload(
            dish_name=review.dish_name,
            rating=review.rating,
            customer_name=customer_name,
            comment=_excerpt(review.comment),
        ),
        subject_id=review.id,
        actor_id=review.customer_id,
        dedupe_key=f"review:{review.id}:posted",
        created_at=at,
    )


async def review_replied(
    session: AsyncSession,
    review: Review,
    *,
    cook_name: str | None,
    at: datetime | None = None,
) -> None:
    await notifications.notify(
        session,
        recipient_id=review.customer_id,
        audience=Audience.ACCOUNT,
        kind=NotificationType.REVIEW_REPLIED,
        payload=ReviewPayload(
            dish_name=review.dish_name, rating=review.rating, cook_name=cook_name
        ),
        subject_id=review.id,
        actor_id=review.cook_id,
        # Per-review key: a reply removed and written again is not announced twice.
        dedupe_key=f"review:{review.id}:replied",
        created_at=at,
    )
    # The cook's "new review" was a to-do; replying completes it.
    await notifications.resolve(
        session,
        kind=NotificationType.REVIEW_POSTED,
        subject_id=review.id,
        recipient_id=review.cook_id,
    )


async def review_removed(session: AsyncSession, review: Review) -> None:
    await notifications.resolve(
        session,
        kind=NotificationType.REVIEW_POSTED,
        subject_id=review.id,
        recipient_id=review.cook_id,
    )

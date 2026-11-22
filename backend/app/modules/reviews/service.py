from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.auth.models import User
from app.modules.dishes.models import Dish
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.reviews import notifications as review_notifications
from app.modules.reviews.models import RATING_MAX, RATING_MIN, Review
from app.modules.reviews.schemas import ReviewCreate, ReviewPatch
from app.shared.base import utcnow

type AnySelect = Select[*tuple[Any, ...]]


class ReviewNotFoundError(NotFoundError):
    default_message = "Review not found"


class UnknownOrderError(ValidationFailedError):
    default_message = "Unknown order"

    def __init__(self) -> None:
        super().__init__(
            details=[
                {
                    "field": "order_id",
                    "type": "unknown_order",
                    "message": "no such order among your orders",
                }
            ]
        )


class DishNotInOrderError(ValidationFailedError):
    default_message = "This dish is not on that order"

    def __init__(self) -> None:
        super().__init__(
            details=[
                {
                    "field": "dish_id",
                    "type": "not_in_order",
                    "message": "review a dish that was on the order",
                }
            ]
        )


class OrderNotCompletedError(ConflictError):
    code = "order_not_completed"
    default_message = (
        "You can review a dish once you have received it: the cook accepted the "
        "order and made it ready, and you confirmed receiving it"
    )

    def __init__(self, *, status: str, missing: list[str]) -> None:
        super().__init__(details={"status": status, "missing": missing})


class AlreadyReviewedError(ConflictError):
    code = "already_reviewed"
    default_message = "You already reviewed this dish - edit your review instead"

    def __init__(self, review_id: uuid.UUID | None) -> None:
        super().__init__(details={"review_id": str(review_id) if review_id else None})


# A dish is reviewable only once the customer received it. ``completed`` alone
# is not trusted: the order must also carry the cook's accept and ready steps,
# so a status written any other way (a script, a bad migration) never opens
# reviews. Every other status - placed, accepted, ready, cancelled - is refused.
_CYCLE_STAMPS = ("accepted_at", "ready_at", "completed_at")


def full_cycle_steps_missing(order: Order) -> list[str]:
    missing = [] if order.status == OrderStatus.COMPLETED.value else ["status"]
    return missing + [stamp for stamp in _CYCLE_STAMPS if getattr(order, stamp) is None]


def full_cycle_conditions() -> list[ColumnElement[bool]]:
    # SQL twin of full_cycle_steps_missing() == [] - keep the two in step.
    return [
        Order.status == OrderStatus.COMPLETED.value,
        *(getattr(Order, stamp).is_not(None) for stamp in _CYCLE_STAMPS),
    ]


def short_name(display_name: str | None) -> str | None:
    if not display_name or not display_name.strip():
        return None
    parts = display_name.split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."


@dataclasses.dataclass(frozen=True)
class ReviewView:
    review: Review
    customer_name: str | None
    cook_name: str | None

    @property
    def author_name(self) -> str | None:
        return short_name(self.customer_name)


_Customer = aliased(User, name="review_customer")
_Cook = aliased(User, name="review_cook")


def _review_select() -> AnySelect:
    # populate_existing: after an update + commit, return the stored row
    # rather than the identity map's stale copy.
    return (
        select(Review, _Customer.display_name, _Cook.display_name)
        .join(_Customer, _Customer.id == Review.customer_id)
        .join(_Cook, _Cook.id == Review.cook_id)
        .execution_options(populate_existing=True)
    )


def _conditions(
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
    dish_id: uuid.UUID | None = None,
    rating: int | None = None,
    replied: bool | None = None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if customer_id is not None:
        conditions.append(Review.customer_id == customer_id)
    if cook_id is not None:
        conditions.append(Review.cook_id == cook_id)
    if dish_id is not None:
        conditions.append(Review.dish_id == dish_id)
    if rating is not None:
        conditions.append(Review.rating == rating)
    if replied is not None:
        conditions.append(
            Review.replied_at.is_not(None) if replied else Review.replied_at.is_(None)
        )
    return conditions


async def page_reviews(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
    dish_id: uuid.UUID | None = None,
    rating: int | None = None,
    replied: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[ReviewView]]:
    conditions = _conditions(
        customer_id=customer_id,
        cook_id=cook_id,
        dish_id=dish_id,
        rating=rating,
        replied=replied,
    )
    total = await session.scalar(select(func.count()).select_from(Review).where(*conditions))
    rows = (
        await session.execute(
            _review_select()
            .where(*conditions)
            .order_by(Review.created_at.desc(), Review.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return total or 0, [
        ReviewView(review=review, customer_name=customer, cook_name=cook)
        for review, customer, cook in rows
    ]


async def get_review(
    session: AsyncSession,
    review_id: uuid.UUID,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
) -> ReviewView:
    row = (
        await session.execute(
            _review_select().where(
                Review.id == review_id,
                *_conditions(customer_id=customer_id, cook_id=cook_id),
            )
        )
    ).one_or_none()
    if row is None:
        raise ReviewNotFoundError
    return ReviewView(review=row[0], customer_name=row[1], cook_name=row[2])


@dataclasses.dataclass(frozen=True)
class Rating:
    average: float | None = None
    count: int = 0
    distribution: dict[int, int] = dataclasses.field(default_factory=dict)


def _average(value: Any) -> float | None:
    return None if value is None else round(float(value), 2)


async def rating_summary(
    session: AsyncSession,
    *,
    dish_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
) -> Rating:
    counts = {
        rating: count
        for rating, count in (
            await session.execute(
                select(Review.rating, func.count())
                .where(*_conditions(dish_id=dish_id, cook_id=cook_id))
                .group_by(Review.rating)
            )
        ).all()
    }
    total = sum(counts.values())
    average = sum(rating * count for rating, count in counts.items()) / total if total else None
    return Rating(
        average=_average(average),
        count=total,
        distribution={
            stars: counts.get(stars, 0) for stars in range(RATING_MAX, RATING_MIN - 1, -1)
        },
    )


async def _ratings_by(
    session: AsyncSession, column: Any, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Rating]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return {}
    rows = await session.execute(
        select(column, func.avg(Review.rating), func.count())
        .where(column.in_(wanted))
        .group_by(column)
    )
    return {
        key: Rating(average=_average(average), count=count)
        for key, average, count in rows.all()
    }


async def dish_ratings(
    session: AsyncSession, dish_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Rating]:
    return await _ratings_by(session, Review.dish_id, dish_ids)


async def cook_ratings(
    session: AsyncSession, cook_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Rating]:
    return await _ratings_by(session, Review.cook_id, cook_ids)


async def unreplied_count(session: AsyncSession, cook_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Review)
            .where(*_conditions(cook_id=cook_id, replied=False))
        )
    ) or 0


@dataclasses.dataclass(frozen=True)
class PendingReview:
    dish: Dish
    cook_name: str | None
    order_id: uuid.UUID
    completed_at: datetime


async def page_pending(
    session: AsyncSession,
    customer_id: uuid.UUID,
    *,
    dish_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[PendingReview]]:
    unreviewed = ~exists(
        select(Review.id).where(
            Review.customer_id == customer_id, Review.dish_id == OrderItem.dish_id
        )
    )
    # One row per dish: row_number() over each dish's received orders, newest
    # first, so rank 1 is the order to review it from. Lines of deleted dishes
    # (dish_id NULL) cannot be reviewed.
    ranked = (
        select(
            OrderItem.dish_id.label("dish_id"),
            Order.id.label("order_id"),
            Order.completed_at.label("completed_at"),
            func.row_number()
            .over(
                partition_by=OrderItem.dish_id,
                order_by=(Order.completed_at.desc(), Order.id),
            )
            .label("rank"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.customer_id == customer_id,
            *full_cycle_conditions(),
            OrderItem.dish_id.is_not(None) if dish_id is None else OrderItem.dish_id == dish_id,
            unreviewed,
        )
        .subquery()
    )
    latest = ranked.c.rank == 1
    total = await session.scalar(select(func.count()).select_from(ranked).where(latest))
    rows = (
        await session.execute(
            select(Dish, User.display_name, ranked.c.order_id, ranked.c.completed_at)
            .select_from(ranked)
            .join(Dish, Dish.id == ranked.c.dish_id)
            .join(User, User.id == Dish.cook_id)
            .where(latest)
            .order_by(ranked.c.completed_at.desc(), ranked.c.dish_id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return total or 0, [
        PendingReview(dish=dish, cook_name=cook, order_id=order_id, completed_at=done)
        for dish, cook, order_id, done in rows
    ]


async def _existing_review_id(
    session: AsyncSession, customer_id: uuid.UUID, dish_id: uuid.UUID
) -> uuid.UUID | None:
    return await session.scalar(
        select(Review.id).where(Review.customer_id == customer_id, Review.dish_id == dish_id)
    )


async def create_review(
    session: AsyncSession, customer_id: uuid.UUID, payload: ReviewCreate
) -> ReviewView:
    order = await session.scalar(
        select(Order).where(Order.id == payload.order_id, Order.customer_id == customer_id)
    )
    if order is None:
        raise UnknownOrderError
    on_order = await session.scalar(
        select(OrderItem.id)
        .where(OrderItem.order_id == order.id, OrderItem.dish_id == payload.dish_id)
        .limit(1)
    )
    if on_order is None:
        raise DishNotInOrderError
    missing = full_cycle_steps_missing(order)
    if missing:
        raise OrderNotCompletedError(status=order.status, missing=missing)
    existing = await _existing_review_id(session, customer_id, payload.dish_id)
    if existing is not None:
        raise AlreadyReviewedError(existing)

    dish = await session.get(Dish, payload.dish_id)
    assert dish is not None  # the order line still links it
    review = Review(
        customer_id=customer_id,
        cook_id=order.cook_id,
        dish_id=dish.id,
        order_id=order.id,
        dish_name=dish.name,
        rating=payload.rating,
        comment=payload.comment,
    )
    session.add(review)
    try:
        await session.flush()
    except IntegrityError:
        # Two requests for the same dish passed the check above together; the
        # unique (customer, dish) pair lets exactly one in.
        await session.rollback()
        raise AlreadyReviewedError(
            await _existing_review_id(session, customer_id, payload.dish_id)
        ) from None
    review_id = review.id
    await review_notifications.review_posted(
        session,
        review,
        customer_name=await session.scalar(
            select(User.display_name).where(User.id == customer_id)
        ),
    )
    await session.commit()
    return await get_review(session, review_id)


async def update_review(
    session: AsyncSession, view: ReviewView, payload: ReviewPatch
) -> ReviewView:
    review = view.review
    changed = False
    for field, value in payload.model_dump(exclude_unset=True).items():
        if getattr(review, field) != value:
            setattr(review, field, value)
            changed = True
    if changed:
        review.edited_at = utcnow()
        await session.commit()
    return await get_review(session, review.id)


async def delete_review(session: AsyncSession, view: ReviewView) -> None:
    await review_notifications.review_removed(session, view.review)
    await session.delete(view.review)
    await session.commit()


async def set_reply(session: AsyncSession, view: ReviewView, text: str) -> ReviewView:
    review = view.review
    first = review.reply is None
    if review.reply != text:
        review.reply = text
        review.replied_at = utcnow()
        # Rewording a reply is not news to the customer: only the first one notifies.
        if first:
            await review_notifications.review_replied(session, review, cook_name=view.cook_name)
        await session.commit()
    return await get_review(session, review.id)


async def remove_reply(session: AsyncSession, view: ReviewView) -> ReviewView:
    review = view.review
    if review.reply is not None:
        review.reply = None
        review.replied_at = None
        await session.commit()
    return await get_review(session, review.id)

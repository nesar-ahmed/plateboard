from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession
from app.modules.auth.dependencies import CookRequired, CustomerRequired
from app.modules.cooks import service as cook_service
from app.modules.dishes import service as dish_service
from app.modules.reviews import service
from app.modules.reviews.schemas import (
    CookReviewOut,
    CookReviewPage,
    MyReviewOut,
    MyReviewPage,
    PendingReviewOut,
    PendingReviewPage,
    ReplyRequest,
    ReviewCreate,
    ReviewOut,
    ReviewPage,
    ReviewPatch,
    ReviewReplyOut,
    rating_summary_out,
)

my_review_router = APIRouter(prefix="/api/me/reviews", tags=["reviews"])
cook_review_router = APIRouter(prefix="/api/cooks/me/reviews", tags=["reviews"])
public_review_router = APIRouter(prefix="/api", tags=["reviews"])

DEFAULT_PAGE_SIZE = 20

PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]
RatingFilter = Annotated[int | None, Query(ge=1, le=5)]


def _public_fields(view: service.ReviewView) -> dict[str, object]:
    review = view.review
    return {
        "id": review.id,
        "rating": review.rating,
        "comment": review.comment,
        "author_name": view.author_name,
        "dish_id": review.dish_id,
        "dish_name": review.dish_name,
        "cook_id": review.cook_id,
        "created_at": review.created_at,
        "edited_at": review.edited_at,
        "reply": ReviewReplyOut(body=review.reply, replied_at=review.replied_at)
        if review.reply is not None and review.replied_at is not None
        else None,
    }


def _review_out(view: service.ReviewView) -> ReviewOut:
    return ReviewOut.model_validate(_public_fields(view))


def _my_review_out(view: service.ReviewView) -> MyReviewOut:
    return MyReviewOut.model_validate(
        {**_public_fields(view), "order_id": view.review.order_id, "cook_name": view.cook_name}
    )


def _cook_review_out(view: service.ReviewView) -> CookReviewOut:
    return CookReviewOut.model_validate(
        {
            **_public_fields(view),
            "order_id": view.review.order_id,
            "customer_name": view.customer_name,
        }
    )


@my_review_router.get("", response_model=MyReviewPage)
async def list_my_reviews(
    user: CustomerRequired,
    db: DbSession,
    dish_id: uuid.UUID | None = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> MyReviewPage:
    total, views = await service.page_reviews(
        db, customer_id=user.id, dish_id=dish_id, limit=limit, offset=offset
    )
    return MyReviewPage(
        items=[_my_review_out(view) for view in views], total=total, limit=limit, offset=offset
    )


@my_review_router.get("/pending", response_model=PendingReviewPage)
async def list_pending_reviews(
    user: CustomerRequired,
    db: DbSession,
    dish_id: uuid.UUID | None = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> PendingReviewPage:
    total, pending = await service.page_pending(
        db, user.id, dish_id=dish_id, limit=limit, offset=offset
    )
    return PendingReviewPage(
        items=[
            PendingReviewOut(
                dish_id=item.dish.id,
                dish_name=item.dish.name,
                dish_available=item.dish.active,
                cook_id=item.dish.cook_id,
                cook_name=item.cook_name,
                order_id=item.order_id,
                completed_at=item.completed_at,
            )
            for item in pending
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@my_review_router.post("", response_model=MyReviewOut, status_code=201)
async def create_review(
    payload: ReviewCreate, user: CustomerRequired, db: DbSession
) -> MyReviewOut:
    return _my_review_out(await service.create_review(db, user.id, payload))


@my_review_router.get("/{review_id}", response_model=MyReviewOut)
async def get_my_review(
    review_id: uuid.UUID, user: CustomerRequired, db: DbSession
) -> MyReviewOut:
    return _my_review_out(await service.get_review(db, review_id, customer_id=user.id))


@my_review_router.patch("/{review_id}", response_model=MyReviewOut)
async def update_my_review(
    review_id: uuid.UUID, payload: ReviewPatch, user: CustomerRequired, db: DbSession
) -> MyReviewOut:
    view = await service.get_review(db, review_id, customer_id=user.id)
    return _my_review_out(await service.update_review(db, view, payload))


@my_review_router.delete("/{review_id}", status_code=204)
async def delete_my_review(
    review_id: uuid.UUID, user: CustomerRequired, db: DbSession
) -> Response:
    view = await service.get_review(db, review_id, customer_id=user.id)
    await service.delete_review(db, view)
    return Response(status_code=204)


@cook_review_router.get("", response_model=CookReviewPage)
async def list_kitchen_reviews(
    user: CookRequired,
    db: DbSession,
    rating: RatingFilter = None,
    replied: bool | None = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> CookReviewPage:
    total, views = await service.page_reviews(
        db, cook_id=user.id, rating=rating, replied=replied, limit=limit, offset=offset
    )
    return CookReviewPage(
        items=[_cook_review_out(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
        summary=rating_summary_out(await service.rating_summary(db, cook_id=user.id)),
        unreplied=await service.unreplied_count(db, user.id),
    )


@cook_review_router.get("/{review_id}", response_model=CookReviewOut)
async def get_kitchen_review(
    review_id: uuid.UUID, user: CookRequired, db: DbSession
) -> CookReviewOut:
    return _cook_review_out(await service.get_review(db, review_id, cook_id=user.id))


@cook_review_router.put("/{review_id}/reply", response_model=CookReviewOut)
async def reply_to_review(
    review_id: uuid.UUID, payload: ReplyRequest, user: CookRequired, db: DbSession
) -> CookReviewOut:
    view = await service.get_review(db, review_id, cook_id=user.id)
    return _cook_review_out(await service.set_reply(db, view, payload.reply))


@cook_review_router.delete("/{review_id}/reply", response_model=CookReviewOut)
async def remove_review_reply(
    review_id: uuid.UUID, user: CookRequired, db: DbSession
) -> CookReviewOut:
    view = await service.get_review(db, review_id, cook_id=user.id)
    return _cook_review_out(await service.remove_reply(db, view))


@public_review_router.get("/dishes/{dish_id}/reviews", response_model=ReviewPage)
async def list_dish_reviews(
    dish_id: uuid.UUID,
    db: DbSession,
    rating: RatingFilter = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> ReviewPage:
    await dish_service.get_public_dish(db, dish_id)
    total, views = await service.page_reviews(
        db, dish_id=dish_id, rating=rating, limit=limit, offset=offset
    )
    return ReviewPage(
        items=[_review_out(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
        summary=rating_summary_out(await service.rating_summary(db, dish_id=dish_id)),
    )


@public_review_router.get("/cooks/{user_id}/reviews", response_model=ReviewPage)
async def list_kitchen_public_reviews(
    user_id: uuid.UUID,
    db: DbSession,
    rating: RatingFilter = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> ReviewPage:
    await cook_service.get_public_cook(db, user_id)
    total, views = await service.page_reviews(
        db, cook_id=user_id, rating=rating, limit=limit, offset=offset
    )
    return ReviewPage(
        items=[_review_out(view) for view in views],
        total=total,
        limit=limit,
        offset=offset,
        summary=rating_summary_out(await service.rating_summary(db, cook_id=user_id)),
    )

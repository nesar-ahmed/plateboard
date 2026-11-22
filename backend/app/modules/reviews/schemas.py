from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.reviews.models import (
    COMMENT_MAX_LENGTH,
    RATING_MAX,
    RATING_MIN,
    REPLY_MAX_LENGTH,
)
from app.shared.types import UTCDateTime

if TYPE_CHECKING:
    from app.modules.reviews.service import Rating


def _clean_comment(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


class ReviewCreate(BaseModel):
    order_id: uuid.UUID = Field(description="one of my orders that I received")
    dish_id: uuid.UUID = Field(description="a dish on that order")
    rating: int = Field(ge=RATING_MIN, le=RATING_MAX)
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)

    @field_validator("comment")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return _clean_comment(value)


class ReviewPatch(BaseModel):
    rating: int | None = Field(default=None, ge=RATING_MIN, le=RATING_MAX)
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)

    @field_validator("comment")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        return _clean_comment(value)

    @field_validator("rating")
    @classmethod
    def _rating_not_null(cls, value: int | None) -> int | None:
        if value is None:
            raise ValueError("a review always has a rating")
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        # model_fields_set, not "is not None": an explicit null comment is an edit.
        if not self.model_fields_set:
            raise ValueError("send rating and/or comment")
        return self


class ReplyRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=REPLY_MAX_LENGTH)

    @field_validator("reply")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class RatingOut(BaseModel):
    average: float | None = Field(default=None, description="null without reviews")
    count: int = 0


class StarCount(BaseModel):
    rating: int
    count: int


class RatingSummaryOut(RatingOut):
    distribution: list[StarCount] = Field(description="5 stars down to 1")


def rating_out(rating: Rating | None) -> RatingOut:
    return RatingOut() if rating is None else RatingOut(average=rating.average, count=rating.count)


def rating_summary_out(rating: Rating) -> RatingSummaryOut:
    return RatingSummaryOut(
        average=rating.average,
        count=rating.count,
        distribution=[
            StarCount(rating=stars, count=count) for stars, count in rating.distribution.items()
        ],
    )


class ReviewReplyOut(BaseModel):
    body: str
    replied_at: UTCDateTime


class ReviewOut(BaseModel):
    id: uuid.UUID
    rating: int
    comment: str | None
    author_name: str | None = Field(description='"First L."; null without a display name')
    dish_id: uuid.UUID | None = Field(description="null once the cook deleted the dish")
    dish_name: str
    cook_id: uuid.UUID
    created_at: UTCDateTime
    edited_at: UTCDateTime | None
    reply: ReviewReplyOut | None


class MyReviewOut(ReviewOut):
    order_id: uuid.UUID | None
    cook_name: str | None


class CookReviewOut(ReviewOut):
    order_id: uuid.UUID | None
    customer_name: str | None


class ReviewPage(BaseModel):
    items: list[ReviewOut]
    total: int
    limit: int
    offset: int
    summary: RatingSummaryOut = Field(description="over every review, whatever the filter")


class MyReviewPage(BaseModel):
    items: list[MyReviewOut]
    total: int
    limit: int
    offset: int


class CookReviewPage(BaseModel):
    items: list[CookReviewOut]
    total: int
    limit: int
    offset: int
    summary: RatingSummaryOut
    unreplied: int


class PendingReviewOut(BaseModel):
    dish_id: uuid.UUID
    dish_name: str
    dish_available: bool
    cook_id: uuid.UUID
    cook_name: str | None
    order_id: uuid.UUID = Field(description="my latest received order with the dish")
    completed_at: UTCDateTime


class PendingReviewPage(BaseModel):
    items: list[PendingReviewOut]
    total: int
    limit: int
    offset: int

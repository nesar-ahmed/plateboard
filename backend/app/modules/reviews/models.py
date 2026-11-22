from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

RATING_MIN = 1
RATING_MAX = 5
COMMENT_MAX_LENGTH = 1000
REPLY_MAX_LENGTH = 1000
DISH_NAME_MAX_LENGTH = 120


class Review(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            f"rating >= {RATING_MIN} AND rating <= {RATING_MAX}", name="rating_range"
        ),
        CheckConstraint("(reply IS NULL) = (replied_at IS NULL)", name="reply_complete"),
        CheckConstraint("customer_id <> cook_id", name="not_own_dish"),
        # One review per customer per dish. NULL dish ids (deleted dishes) never
        # collide, so old reviews of a deleted dish do not block anything.
        UniqueConstraint("customer_id", "dish_id", name="uq_reviews_customer_dish"),
        Index("ix_reviews_cook_created", "cook_id", "created_at"),
        Index("ix_reviews_dish_created", "dish_id", "created_at"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL + the dish_name copy: deleting a dish keeps its reviews on the
    # kitchen's record instead of erasing the kitchen's rating history.
    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dishes.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )
    dish_name: Mapped[str] = mapped_column(String(DISH_NAME_MAX_LENGTH), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(COMMENT_MAX_LENGTH), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    reply: Mapped[str | None] = mapped_column(String(REPLY_MAX_LENGTH), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

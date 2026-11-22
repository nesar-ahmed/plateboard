"""reviews

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("cook_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("dish_name", sa.String(length=120), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.Column("edited_at", sa.DateTime(), nullable=True),
        sa.Column("reply", sa.String(length=1000), nullable=True),
        sa.Column("replied_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(reply IS NULL) = (replied_at IS NULL)",
            name=op.f("ck_reviews_reply_complete"),
        ),
        sa.CheckConstraint("customer_id <> cook_id", name=op.f("ck_reviews_not_own_dish")),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5", name=op.f("ck_reviews_rating_range")
        ),
        sa.ForeignKeyConstraint(
            ["cook_id"],
            ["users.id"],
            name=op.f("fk_reviews_cook_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name=op.f("fk_reviews_customer_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_reviews_dish_id_dishes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_reviews_order_id_orders"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint("customer_id", "dish_id", name="uq_reviews_customer_dish"),
    )
    op.create_index(
        "ix_reviews_cook_created", "reviews", ["cook_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_reviews_dish_created", "reviews", ["dish_id", "created_at"], unique=False
    )
    op.create_index(op.f("ix_reviews_order_id"), "reviews", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reviews_order_id"), table_name="reviews")
    op.drop_index("ix_reviews_dish_created", table_name="reviews")
    op.drop_index("ix_reviews_cook_created", table_name="reviews")
    op.drop_table("reviews")

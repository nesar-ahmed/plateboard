"""carts for guests and users

Adds ``carts`` - owned by exactly one of an account (``user_id``, unique: one
cart per account) or a guest (``token_hash``, unique: the SHA-256 of the
random token in the HTTP-only cart cookie) - and ``cart_items``, one row per
(cart, dish) with a quantity of 1..100 (CHECK). Deleting an account, a cart
or a dish cascades to the lines; ``dish_id`` gets its own index for that.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (token_hash IS NULL)",
            name=op.f("ck_carts_exactly_one_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_carts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carts")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_carts_token_hash")),
        sa.UniqueConstraint("user_id", name=op.f("uq_carts_user_id")),
    )
    op.create_table(
        "cart_items",
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "quantity >= 1 AND quantity <= 100",
            name=op.f("ck_cart_items_quantity_range"),
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["carts.id"],
            name=op.f("fk_cart_items_cart_id_carts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_cart_items_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cart_id", "dish_id", name=op.f("pk_cart_items")),
    )
    op.create_index(
        op.f("ix_cart_items_dish_id"), "cart_items", ["dish_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cart_items_dish_id"), table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_table("carts")

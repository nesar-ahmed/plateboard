"""orders and order lines

Adds ``orders`` - one customer buying from one cook (both FK ``users``,
CASCADE; CHECK they differ), a ``status`` out of placed / accepted / ready /
completed / cancelled (CHECK), the ``total`` and ``item_count`` frozen at
placement (CHECK positive), an optional note, one timestamp per status step
and who cancelled - and ``order_items``, the snapshot lines: dish name and
unit price copied at placement, quantity 1..100 (CHECK), ``position`` for the
cart's order, and ``dish_id`` (FK ``dishes``, SET NULL) so deleting a dish
keeps the order history intact.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
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
        "orders",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("cook_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.String(length=20), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN ('customer', 'cook')",
            name=op.f("ck_orders_cancelled_by_known"),
        ),
        sa.CheckConstraint(
            "status IN ('placed', 'accepted', 'ready', 'completed', 'cancelled')",
            name=op.f("ck_orders_status_known"),
        ),
        sa.CheckConstraint(
            "customer_id <> cook_id", name=op.f("ck_orders_not_own_order")
        ),
        sa.CheckConstraint(
            "item_count > 0", name=op.f("ck_orders_item_count_positive")
        ),
        sa.CheckConstraint("total > 0", name=op.f("ck_orders_total_positive")),
        sa.ForeignKeyConstraint(
            ["cook_id"],
            ["users.id"],
            name=op.f("fk_orders_cook_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name=op.f("fk_orders_customer_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
    )
    op.create_index(op.f("ix_orders_cook_id"), "orders", ["cook_id"], unique=False)
    op.create_index(
        op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False
    )
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "quantity >= 1 AND quantity <= 100",
            name=op.f("ck_order_items_quantity_range"),
        ),
        sa.CheckConstraint(
            "unit_price > 0", name=op.f("ck_order_items_unit_price_positive")
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_order_items_dish_id_dishes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
    )
    op.create_index(
        op.f("ix_order_items_dish_id"), "order_items", ["dish_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_dish_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_cook_id"), table_name="orders")
    op.drop_table("orders")

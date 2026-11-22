"""address book and the order's delivery address

Adds ``addresses`` - an account's delivery addresses (FK ``users``, CASCADE):
recipient, phone, two address lines, city, postal code, instructions, an
optional service-grid zone (FK ``zones``, SET NULL) and ``is_default``, with a
partial unique index so an account has at most one default - and the
nullable ``orders.delivery_address`` JSON column holding the copy of the
address an order was placed to (NULL for orders placed before this).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "addresses",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=True),
        sa.Column("recipient", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("line1", sa.String(length=120), nullable=False),
        sa.Column("line2", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("instructions", sa.String(length=200), nullable=True),
        sa.Column("zone_id", sa.Uuid(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_addresses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["zones.id"],
            name=op.f("fk_addresses_zone_id_zones"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(
        op.f("ix_addresses_user_id"), "addresses", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_addresses_zone_id"), "addresses", ["zone_id"], unique=False
    )
    # Partial unique index: at most one default address per account.
    op.create_index(
        "uq_addresses_one_default_per_user",
        "addresses",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
        postgresql_where=sa.text("is_default"),
    )
    # A nullable column: SQLite adds it in place, no table rebuild needed.
    op.add_column("orders", sa.Column("delivery_address", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Native ALTER TABLE ... DROP COLUMN (SQLite >= 3.35), NOT batch mode: a
    # batch "recreate" drops and rebuilds the table, and with foreign keys ON
    # dropping a parent table fires ON DELETE CASCADE on every child row.
    # (orders is the parent of order_items)
    op.drop_column("orders", "delivery_address")
    op.drop_index("uq_addresses_one_default_per_user", table_name="addresses")
    op.drop_index(op.f("ix_addresses_zone_id"), table_name="addresses")
    op.drop_index(op.f("ix_addresses_user_id"), table_name="addresses")
    op.drop_table("addresses")

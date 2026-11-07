"""dishes table

Adds the cook-owned ``dishes`` menu table: name/description, integer
minor-unit price (CHECK positive), portions (CHECK positive), JSON list
columns for ingredients/allergens/dietary tags, and the ``active`` flag that
keeps deactivated dishes out of the public menu.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dishes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cook_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("portions", sa.Integer(), nullable=False),
        sa.Column(
            "ingredients", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "allergens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "dietary_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("(true)")
        ),
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
        sa.CheckConstraint("price > 0", name=op.f("ck_dishes_price_positive")),
        sa.CheckConstraint("portions > 0", name=op.f("ck_dishes_portions_positive")),
        sa.ForeignKeyConstraint(
            ["cook_id"],
            ["users.id"],
            name=op.f("fk_dishes_cook_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dishes")),
    )
    # index=True on the model columns -> plain (non-unique) indexes.
    op.create_index(op.f("ix_dishes_cook_id"), "dishes", ["cook_id"], unique=False)
    op.create_index(op.f("ix_dishes_active"), "dishes", ["active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dishes_active"), table_name="dishes")
    op.drop_index(op.f("ix_dishes_cook_id"), table_name="dishes")
    op.drop_table("dishes")

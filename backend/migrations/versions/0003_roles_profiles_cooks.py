"""roles + user profile fields + cooks table

Adds the customer/cook role list (default customer) and the editable profile
columns to ``users``, plus the 1:1 ``cooks`` cook-profile table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("display_name", sa.String(length=60), nullable=True)
    )
    op.add_column("users", sa.Column("bio", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("area", sa.String(length=120), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "roles",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[\"customer\"]'"),
        ),
    )
    op.create_table(
        "cooks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("headline", sa.String(length=80), nullable=False),
        sa.Column(
            "specialties", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_cooks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_cooks")),
    )


def downgrade() -> None:
    op.drop_table("cooks")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("roles")
        batch_op.drop_column("area")
        batch_op.drop_column("bio")
        batch_op.drop_column("display_name")

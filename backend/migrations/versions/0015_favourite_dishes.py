"""favourite dishes

Adds ``favourite_dishes`` - a customer's saved dishes: one row per (user,
dish), the pair being the primary key (a dish is saved at most once), both
FKs CASCADE (deleting the account or the dish removes the row) and
``created_at`` (when it was saved - the list is newest first). ``dish_id``
gets its own index for the dish-delete cascade (the PK leads with
``user_id``). The 50-per-account limit is enforced by the service.

A brand-new table nothing references: the downgrade simply drops it.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favourite_dishes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_favourite_dishes_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_favourite_dishes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "dish_id", name=op.f("pk_favourite_dishes")),
    )
    op.create_index(
        op.f("ix_favourite_dishes_dish_id"),
        "favourite_dishes",
        ["dish_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_favourite_dishes_dish_id"), table_name="favourite_dishes")
    op.drop_table("favourite_dishes")

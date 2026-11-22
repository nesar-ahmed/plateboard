"""user food preferences

Adds two JSON list columns to ``users`` - ``excluded_allergens`` (tokens
from the dishes' Allergen vocabulary) and ``dietary_preferences`` (lowercase
diet tags) - backing ``GET/PUT /api/me/preferences``. Both default to an
empty list, so existing accounts start with no preferences.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL columns on an existing table need a server default for the
    # rows already there; SQLite adds them in place.
    op.add_column(
        "users",
        sa.Column(
            "excluded_allergens",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "dietary_preferences",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    # Native ALTER TABLE ... DROP COLUMN (SQLite >= 3.35), NOT batch mode: a
    # batch "recreate" drops and rebuilds the table, and with foreign keys ON
    # dropping a parent table fires ON DELETE CASCADE on every child row.
    # (users is the parent of sessions, cooks, dishes, carts, orders, ...)
    op.drop_column("users", "dietary_preferences")
    op.drop_column("users", "excluded_allergens")

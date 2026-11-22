"""order cancel reason

Adds the nullable ``orders.cancel_reason`` column (max 200 chars): the cook's
optional explanation when they reject a placed order or cancel an accepted
one (``PATCH /api/cooks/me/orders/{id}`` with ``{"status": "cancelled",
"reason": ...}``). Existing orders have none (NULL).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("cancel_reason", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    # Native ALTER TABLE ... DROP COLUMN (SQLite >= 3.35), NOT batch mode:
    # ``orders`` is the parent of ``order_items`` (ON DELETE CASCADE), and a
    # batch "recreate" would drop the table and with it every order line.
    op.drop_column("orders", "cancel_reason")

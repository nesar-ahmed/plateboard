"""cook verification and availability

Adds to ``cooks``:

* ``verified_at`` + ``verified_by_id`` (FK ``users``, SET NULL) - the admin's
  verification behind the public "verified" badge;
* ``timezone`` (IANA, default ``UTC``), ``opening_hours`` (JSON list of weekly
  windows, default ``[]`` = no fixed hours) and ``orders_paused`` (default
  false) - when the kitchen takes orders.

Existing cooks start unverified, with no fixed hours, not paused - exactly
how they behaved before (orders any time).

Batch mode is safe here: ``cooks`` is a *child* table (nothing references
it), so the SQLite "recreate" cannot cascade-delete other rows - and it is
required, because SQLite cannot natively drop a column that carries a
foreign key (``verified_by_id``).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cooks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("verified_by_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "timezone",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'UTC'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "opening_hours",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "orders_paused",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_cooks_verified_by_id_users"),
            "users",
            ["verified_by_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("cooks", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_cooks_verified_by_id_users"), type_="foreignkey"
        )
        batch_op.drop_column("orders_paused")
        batch_op.drop_column("opening_hours")
        batch_op.drop_column("timezone")
        batch_op.drop_column("verified_by_id")
        batch_op.drop_column("verified_at")

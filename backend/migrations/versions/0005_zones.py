"""zones on a grid, cooks placed in zones

Adds the ``zones`` reference table - a slug, a display name and integer grid
coordinates (``x``/``y``, CHECK >= 0, one zone per cell) - and the optional
``cooks.zone_id`` (FK, ON DELETE SET NULL) that places a cook's kitchen, and
therefore their dishes, on the grid. Existing cooks start without a zone.

SQLite cannot add a foreign key to an existing table, so the ``cooks`` change
runs as a batch operation (copy into a new table, swap); rows are preserved.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zones",
        sa.Column("slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("x >= 0", name=op.f("ck_zones_x_non_negative")),
        sa.CheckConstraint("y >= 0", name=op.f("ck_zones_y_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zones")),
        sa.UniqueConstraint("x", "y", name="uq_zones_x_y"),
    )
    # unique=True + index=True on the model column -> one UNIQUE index.
    op.create_index(op.f("ix_zones_slug"), "zones", ["slug"], unique=True)

    with op.batch_alter_table("cooks") as batch_op:
        batch_op.add_column(sa.Column("zone_id", sa.Uuid(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_cooks_zone_id"), ["zone_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_cooks_zone_id_zones"),
            "zones",
            ["zone_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("cooks") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_cooks_zone_id_zones"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_cooks_zone_id"))
        batch_op.drop_column("zone_id")

    op.drop_index(op.f("ix_zones_slug"), table_name="zones")
    op.drop_table("zones")

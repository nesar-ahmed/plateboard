"""cook applications

Becoming a cook is now an *application* an admin accepts or rejects. Adds to
``cooks``:

* ``status`` (``pending`` / ``accepted`` / ``rejected``, CHECK-constrained,
  indexed for the back-office queue; new rows default to ``pending``);
* ``submitted_at`` (the latest submission), ``reviewed_at`` +
  ``reviewed_by_id`` (FK ``users``, SET NULL - the deciding admin) and
  ``rejection_reason``.

Every existing kitchen is grandfathered in: it becomes ``accepted``,
submitted and reviewed when it was created (its cook already holds the
``cook`` role, which accepting an application grants from now on).

Batch mode is safe here: ``cooks`` is a *child* table (nothing references
it), so the SQLite "recreate" cannot cascade-delete other rows - and it is
needed to add the CHECK constraint and to drop the FK column on downgrade.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cooks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'pending'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "submitted_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
            )
        )
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("rejection_reason", sa.String(length=300), nullable=True)
        )
        batch_op.create_check_constraint(
            "status_known", "status IN ('pending', 'accepted', 'rejected')"
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_cooks_reviewed_by_id_users"),
            "users",
            ["reviewed_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_cooks_status"), ["status"], unique=False)

    # Grandfather every existing kitchen: accepted when it was created.
    op.execute(
        "UPDATE cooks SET status = 'accepted', submitted_at = created_at, "
        "reviewed_at = created_at"
    )


def downgrade() -> None:
    # Pending / rejected applicants never held the cook role, and before this
    # revision a cooks row *is* a kitchen: remove theirs so no account gains
    # a kitchen it was never given.
    op.execute("DELETE FROM cooks WHERE status <> 'accepted'")
    with op.batch_alter_table("cooks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cooks_status"))
        batch_op.drop_constraint(
            batch_op.f("fk_cooks_reviewed_by_id_users"), type_="foreignkey"
        )
        batch_op.drop_constraint(batch_op.f("ck_cooks_status_known"), type_="check")
        batch_op.drop_column("rejection_reason")
        batch_op.drop_column("reviewed_by_id")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("status")

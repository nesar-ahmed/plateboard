"""notifications

Adds ``notifications`` - the in-app inboxes: one row per recipient and event
(FK ``users``, CASCADE), the panel it belongs to (``audience``: account /
cook / admin, CHECK-constrained), the event ``type``, an optional subject
(``subject_kind`` + ``subject_id``, both or neither - no FK, the notification
outlives its order/kitchen), the acting account (FK ``users``, SET NULL), the
JSON ``data`` snapshot, an optional ``dedupe_key`` (unique per recipient) and
``read_at``.

Indexes: ``ix_notifications_inbox`` (recipient, audience, created_at) for the
newest-first list - it also covers the recipient FK - and the partial
``ix_notifications_unread`` over unread rows only, for the badges.

A brand-new table nothing references: the downgrade simply drops it.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("audience", sa.String(length=20), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("subject_kind", sa.String(length=20), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "audience IN ('account', 'cook', 'admin')",
            name=op.f("ck_notifications_audience_known"),
        ),
        sa.CheckConstraint(
            "(subject_kind IS NULL) = (subject_id IS NULL)",
            name=op.f("ck_notifications_subject_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_notifications_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        # One row per (recipient, event key); NULL keys never collide.
        sa.UniqueConstraint(
            "recipient_id", "dedupe_key", name="uq_notifications_recipient_dedupe_key"
        ),
    )
    op.create_index(
        op.f("ix_notifications_actor_id"), "notifications", ["actor_id"], unique=False
    )
    op.create_index(
        "ix_notifications_inbox",
        "notifications",
        ["recipient_id", "audience", "created_at"],
        unique=False,
    )
    # Partial index: only unread rows, so the badge count stays cheap.
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["recipient_id", "audience"],
        unique=False,
        sqlite_where=sa.text("read_at IS NULL"),
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_unread", table_name="notifications")
    op.drop_index("ix_notifications_inbox", table_name="notifications")
    op.drop_index(op.f("ix_notifications_actor_id"), table_name="notifications")
    op.drop_table("notifications")

"""order fulfilment

Adds ``orders.fulfilment`` - how an order reaches the customer: ``pickup``
(the default - every existing order was a pickup) or ``delivery`` (modelled,
not offered yet), with a CHECK constraint on the column.

``orders`` is a *parent* table (``order_items`` cascades from it), so this
revision never uses batch mode: the column and its CHECK are added in place
with a native ``ALTER TABLE ... ADD COLUMN`` (allowed in SQLite: NOT NULL with
a constant default, and a column-level CHECK), and the downgrade is a native
``DROP COLUMN`` (SQLite >= 3.35; a column's own CHECK does not block it). A
batch "recreate" would drop the table, and with foreign keys ON that deletes
every order line (``tests/test_migrations.py`` guards it).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Spelled out: op.add_column cannot attach a CHECK to the new column, and
    # adding one afterwards would need the forbidden table rebuild.
    op.execute(
        "ALTER TABLE orders ADD COLUMN fulfilment VARCHAR(20) DEFAULT 'pickup' "
        "NOT NULL CONSTRAINT ck_orders_fulfilment_known "
        "CHECK (fulfilment IN ('pickup', 'delivery'))"
    )


def downgrade() -> None:
    op.drop_column("orders", "fulfilment")

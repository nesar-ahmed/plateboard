"""baseline: empty schema starting point for API v1

The previous modular schema (users/boards/cards) was removed together with
``app/modules``. This revision is the clean slate v1 builds on: it stamps
``alembic_version`` so future ``alembic revision --autogenerate`` diffs start
from here.

Revision ID: 0001
Create Date: 2026-11-07
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No tables yet - models arrive with the v1 features."""


def downgrade() -> None:
    """Nothing to drop."""

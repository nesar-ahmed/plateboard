"""Migrations: Alembic is the schema authority and tests prove it runs clean.

``environment`` already applied ``upgrade head`` to the temp database, so these
tests only verify the outcome and the re-run (idempotency) behaviour.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command

from tests.conftest import make_alembic_config

EXPECTED_HEAD = "0001"


def test_upgrade_head_stamps_the_baseline_version(environment, tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == EXPECTED_HEAD


def test_upgrade_head_is_idempotent(environment) -> None:
    """Second run must be a silent no-op - startup scripts rely on that."""
    command.upgrade(make_alembic_config(), "head")
    command.upgrade(make_alembic_config(), "head")

"""Migrations: Alembic is the schema authority and tests prove it runs clean.

``environment`` already applied ``upgrade head`` to the temp database, so these
tests only verify the outcome and the re-run (idempotency) behaviour.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import Script

from app.core.config import BACKEND_ROOT
from tests.conftest import make_alembic_config

EXPECTED_HEAD = "0016"


def rev_after_head(steps: int = 1) -> str:
    """Revision id ``steps`` after EXPECTED_HEAD ("0006", "0007", ...)."""
    return f"{int(EXPECTED_HEAD) + steps:04d}"


NEXT_REVISION = rev_after_head()


def test_upgrade_head_stamps_the_current_head(environment, tmp_path: Path) -> None:
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


# --- new revisions follow the NNNN_<slug>.py convention ---------------------------


def scratch_alembic_config(tmp_path: Path) -> AlembicConfig:
    """The real alembic.ini + env.py over a *copy* of ``migrations/``, so the
    revisions these tests generate never land in the repository."""
    scratch = tmp_path / "scratch-migrations"
    shutil.copytree(
        BACKEND_ROOT / "migrations",
        scratch,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    config = make_alembic_config()
    config.set_main_option("script_location", str(scratch))
    return config


def generate(config: AlembicConfig, message: str, **kwargs: object) -> Script:
    script = command.revision(config, message=message, **kwargs)  # type: ignore[arg-type]
    assert isinstance(script, Script)
    return script


def test_autogenerate_continues_the_numbered_chain(environment, tmp_path: Path) -> None:
    """Autogenerate on the migrated temp DB: sequential id + slug file name,
    and an empty diff - the ORM models and the migrations agree."""
    script = generate(
        scratch_alembic_config(tmp_path), "Add widgets & more!", autogenerate=True
    )
    assert script.revision == NEXT_REVISION
    assert script.down_revision == EXPECTED_HEAD
    assert Path(script.path).name == f"{NEXT_REVISION}_add_widgets_more.py"

    source = Path(script.path).read_text()
    assert f"revision: str = '{NEXT_REVISION}'" in source
    upgrade_body = source.split("def upgrade()")[1].split("def downgrade()")[0]
    assert "op." not in upgrade_body, "schema drift between models and migrations"


def test_plain_revisions_keep_counting(environment, tmp_path: Path) -> None:
    """``alembic revision -m`` (no autogenerate) is numbered too - that is
    what ``revision_environment = true`` in alembic.ini is for."""
    config = scratch_alembic_config(tmp_path)
    first = generate(config, "add widgets")
    second = generate(config, "add gadgets")
    assert (first.revision, second.revision) == (rev_after_head(1), rev_after_head(2))
    assert second.down_revision == first.revision
    assert Path(second.path).name == f"{rev_after_head(2)}_add_gadgets.py"


def test_explicit_rev_id_wins_and_numbering_resumes_after_it(
    environment, tmp_path: Path
) -> None:
    config = scratch_alembic_config(tmp_path)
    explicit = generate(config, "hand picked", rev_id="0042")
    assert Path(explicit.path).name == "0042_hand_picked.py"
    assert generate(config, "after it").revision == "0043"


# --- 0005: the cooks table rebuild keeps data ---------------------------------------


def test_zones_migration_keeps_existing_cooks(environment, tmp_path: Path) -> None:
    """0005 recreates ``cooks`` (SQLite batch mode) to add the zone FK: rows,
    the users FK (CASCADE) and the new zones FK (SET NULL) must all survive,
    and the downgrade must give the table back."""
    config = make_alembic_config()
    command.downgrade(config, "0004")
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("a" * 32, "pre-zones@example.com", "x"),
        )
        conn.execute(
            "INSERT INTO cooks (user_id, headline, specialties) VALUES (?, ?, ?)",
            ("a" * 32, "Cooking since 0004", '["soup"]'),
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(config, "head")
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT headline, specialties, zone_id FROM cooks"
        ).fetchall()
        fks = {
            (row[2], row[3]): row[6]  # (table, from) -> on_delete
            for row in conn.execute("PRAGMA foreign_key_list(cooks)")
        }
    finally:
        conn.close()
    assert rows == [("Cooking since 0004", '["soup"]', None)]
    # (at head; 0011 adds the verifying admin, 0013 the reviewing one - and
    # their own rebuilds keep the rest)
    assert fks == {
        ("users", "user_id"): "CASCADE",
        ("zones", "zone_id"): "SET NULL",
        ("users", "verified_by_id"): "SET NULL",
        ("users", "reviewed_by_id"): "SET NULL",
    }

    command.downgrade(config, "0004")
    conn = sqlite3.connect(db)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(cooks)")]
        count = conn.execute("SELECT count(*) FROM cooks").fetchone()[0]
    finally:
        conn.close()
    assert "zone_id" not in columns
    assert count == 1


# --- 0008-0014 downgrades never cascade-delete child rows ---------------------------


def test_downgrades_keep_parent_and_child_rows(environment, tmp_path: Path) -> None:
    """0009 drops columns from ``users``, 0010 and 0008 from ``orders`` - both
    are parents of ON DELETE CASCADE children. A batch-mode "recreate" would drop
    and rebuild those tables, and with foreign keys ON that deletes every
    child row; the downgrades must use native DROP COLUMN instead."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for uid, email in (
            ("c" * 32, "cook@example.com"),
            ("d" * 32, "buyer@example.com"),
        ):
            conn.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                (uid, email, "x"),
            )
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            ("e" * 64, "d" * 32, "2999-01-01 00:00:00"),
        )
        conn.execute(
            "INSERT INTO cooks (user_id, headline, specialties, verified_at, verified_by_id,"
            " opening_hours, status) VALUES (?, 'Soups', '[]', '2026-01-01 00:00:00', ?, ?,"
            " 'accepted')",
            ("c" * 32, "d" * 32, '[{"day": 0, "opens": "09:00", "closes": "17:00"}]'),
        )
        conn.execute(
            "INSERT INTO orders (id, customer_id, cook_id, status, total, item_count)"
            " VALUES (?, ?, ?, 'placed', 500, 1)",
            ("f" * 32, "d" * 32, "c" * 32),
        )
        conn.execute(
            "INSERT INTO order_items (id, order_id, position, name, unit_price, quantity)"
            " VALUES (?, ?, 0, 'Soup', 500, 1)",
            ("a" * 32, "f" * 32),
        )
        conn.commit()
    finally:
        conn.close()

    config = make_alembic_config()
    command.downgrade(config, "0013")  # 0014: native DROP COLUMN on orders (a parent)
    conn = sqlite3.connect(db)
    try:
        lines = conn.execute("SELECT count(*) FROM order_items").fetchone()[0]
        order_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
    finally:
        conn.close()
    assert lines == 1
    assert "fulfilment" not in order_columns

    command.downgrade(config, "0010")  # 0013 + 0011: batch-rebuild cooks (a child)
    conn = sqlite3.connect(db)
    try:
        cooks = conn.execute("SELECT user_id, headline FROM cooks").fetchall()
        cook_columns = [row[1] for row in conn.execute("PRAGMA table_info(cooks)")]
    finally:
        conn.close()
    assert cooks == [("c" * 32, "Soups")]
    assert "opening_hours" not in cook_columns and "verified_at" not in cook_columns

    command.downgrade(config, "0009")
    conn = sqlite3.connect(db)
    try:
        lines = conn.execute("SELECT count(*) FROM order_items").fetchone()[0]
        order_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
    finally:
        conn.close()
    assert lines == 1  # 0010's downgrade kept the order line
    assert "cancel_reason" not in order_columns

    command.downgrade(config, "0007")
    conn = sqlite3.connect(db)
    try:
        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("users", "sessions", "orders", "order_items")
        }
        user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        order_columns = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
    finally:
        conn.close()
    assert counts == {"users": 2, "sessions": 1, "orders": 1, "order_items": 1}
    # ...and back up: existing kitchens get the defaults (no fixed hours).
    assert "excluded_allergens" not in user_columns
    assert "delivery_address" not in order_columns

    command.upgrade(config, "head")  # and back up again cleanly
    conn = sqlite3.connect(db)
    try:
        kitchen = conn.execute(
            "SELECT timezone, opening_hours, orders_paused, verified_at FROM cooks"
        ).fetchone()
    finally:
        conn.close()
    assert kitchen == ("UTC", "[]", 0, None)


# --- 0013: cook applications grandfather existing kitchens ---------------------------


def test_cook_applications_migration(environment, tmp_path: Path) -> None:
    """Upgrading makes every existing kitchen ``accepted`` (reviewed when it
    was created); downgrading drops the applications that were never
    accepted - before 0013 a cooks row *is* a kitchen."""
    config = make_alembic_config()
    command.downgrade(config, "0012")
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    try:
        for uid, email in (
            ("a" * 32, "old@example.com"),
            ("b" * 32, "new@example.com"),
        ):
            conn.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, 'x')",
                (uid, email),
            )
        conn.execute(
            "INSERT INTO cooks (user_id, headline, specialties, created_at)"
            " VALUES (?, 'Old kitchen', '[]', '2026-01-02 03:04:05')",
            ("a" * 32,),
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(config, "head")
    conn = sqlite3.connect(db)
    try:
        kitchen = conn.execute(
            "SELECT status, submitted_at, reviewed_at, reviewed_by_id FROM cooks"
        ).fetchone()
        conn.execute(
            "INSERT INTO cooks (user_id, headline, specialties) VALUES (?, 'New', '[]')",
            ("b" * 32,),
        )
        conn.commit()
        fresh = conn.execute(
            "SELECT status FROM cooks WHERE user_id = ?", ("b" * 32,)
        ).fetchone()
    finally:
        conn.close()
    assert kitchen == ("accepted", "2026-01-02 03:04:05", "2026-01-02 03:04:05", None)
    assert fresh == ("pending",)

    command.downgrade(config, "0012")
    conn = sqlite3.connect(db)
    try:
        kept = conn.execute("SELECT headline FROM cooks").fetchall()
    finally:
        conn.close()
    assert kept == [("Old kitchen",)]

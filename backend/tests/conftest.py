"""Pytest configuration: every test gets its own temporary SQLite database.

Isolation by construction:

* ``DATABASE_URL`` points at a fresh file under ``tmp_path`` (a real file DB,
  so WAL mode and the SQLite pragmas are genuinely exercised),
* Alembic migrations are applied to that file before the app is created -
  tests run the exact same schema path as production.

Nothing here touches ``backend/plateboard.db``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient

from app.core.config import BACKEND_ROOT, Settings, reload_settings
from app.core.db import build_engine, dispose_engine, get_sessionmaker, set_engine
from app.main import create_app
from app.modules.zones import service as zone_service
from app.modules.zones.models import Zone
from app.modules.zones.schemas import ZoneCreate


def make_alembic_config() -> AlembicConfig:
    """Alembic config with absolute paths, usable from any working directory."""
    config = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
    return config


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Temp file database (migrated to head), settings pointed at it.

    Sync on purpose: ``migrations/env.py`` drives its own event loop, which
    must not collide with pytest-asyncio's.
    """
    database_file = tmp_path / "test.db"

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_file}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://testserver")
    settings = reload_settings()

    # Apply the real migrations to the temp database.
    command.upgrade(make_alembic_config(), "head")
    return settings


@pytest.fixture
async def client(environment: Settings) -> AsyncIterator[AsyncClient]:
    """Async HTTP client driving the real ASGI app against the temp database."""
    engine = build_engine(environment.DATABASE_URL)
    set_engine(engine)
    try:
        app = create_app(environment)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as instance:
            yield instance
    finally:
        await dispose_engine()


def pytest_configure(config: pytest.Config) -> None:
    """Custom markers used by the suite."""
    config.addinivalue_line("markers", "integration: touches the real ASGI app")


@pytest.fixture(scope="session", autouse=True)
def _settings_cache() -> Iterator[None]:
    """Guarantee the settings cache starts and ends the run in a clean state."""
    reload_settings()
    yield
    reload_settings()


# --- reusable auth plumbing for feature tests -------------------------------

DEFAULT_PASSWORD = "super-secret-passphrase"
COOK_BODY = {"headline": "Home chef of the decade", "specialties": ["biryani", "korma"]}


@pytest.fixture
def accounts(client):
    """Convenience calls built on the shared ``client`` (cookie jar included).

    After ``login()`` the jar holds the session, so later requests are
    authenticated without touching cookies manually.
    """

    async def register(
        email: str = "user@example.com", password: str = DEFAULT_PASSWORD
    ):
        return await client.post(
            "/api/auth/register", json={"email": email, "password": password}
        )

    async def login(email: str = "user@example.com", password: str = DEFAULT_PASSWORD):
        return await client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )

    async def become_cook(body: dict | None = None):
        return await client.post("/api/cooks", json=body or COOK_BODY)

    async def customer(email: str = "user@example.com"):
        """Register + login in one step; returns the login response."""
        await register(email)
        return await login(email)

    async def cook(email: str = "chef@example.com"):
        """Register + login + become-cook; returns the become response."""
        await customer(email)
        return await become_cook()

    return SimpleNamespace(
        client=client,
        register=register,
        login=login,
        become_cook=become_cook,
        customer=customer,
        cook=cook,
    )


# --- zones: a small test-owned grid (independent of the seed data) ----------------

#: 3 x 3 service grid, ``(slug, name, x, y)``; x = column, y = row.
#:
#:      x=0          x=1            x=2
#: y=0  north-gate   old-town       hillside
#: y=1  riverside    market-square  university
#: y=2  harbour      station        garden-district
ZONE_GRID: tuple[tuple[str, str, int, int], ...] = (
    ("north-gate", "North Gate", 0, 0),
    ("old-town", "Old Town", 1, 0),
    ("hillside", "Hillside", 2, 0),
    ("riverside", "Riverside", 0, 1),
    ("market-square", "Market Square", 1, 1),
    ("university", "University", 2, 1),
    ("harbour", "Harbour", 0, 2),
    ("station", "Station", 1, 2),
    ("garden-district", "Garden District", 2, 2),
)


@pytest.fixture
async def zones(client) -> dict[str, Zone]:
    """The ``ZONE_GRID`` created through the real service, keyed by slug."""
    created: dict[str, Zone] = {}
    async with get_sessionmaker()() as session:
        for slug, name, x, y in ZONE_GRID:
            created[slug] = await zone_service.create_zone(
                session, ZoneCreate(slug=slug, name=name, x=x, y=y)
            )
    return created

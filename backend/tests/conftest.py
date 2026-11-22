"""Pytest configuration: every test gets its own temporary SQLite database.

Isolation by construction:

* ``DATABASE_URL`` points at a fresh file under ``tmp_path`` (a real file DB,
  so WAL mode and the SQLite pragmas are genuinely exercised),
* Alembic migrations are applied to that file before the app is created -
  tests run the exact same schema path as production.

Nothing here touches ``backend/plateboard.db``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import BACKEND_ROOT, Settings, reload_settings
from app.core.db import build_engine, dispose_engine, get_sessionmaker, set_engine
from app.main import create_app
from app.modules.admin import service as admin_service
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.orders.models import Order
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
async def asgi_transport(environment: Settings) -> AsyncIterator[ASGITransport]:
    """The real ASGI app against the temp database, as an httpx transport."""
    engine = build_engine(environment.DATABASE_URL)
    set_engine(engine)
    try:
        yield ASGITransport(app=create_app(environment))
    finally:
        await dispose_engine()


@pytest.fixture
async def client(asgi_transport: ASGITransport) -> AsyncIterator[AsyncClient]:
    """Async HTTP client (one browser, one cookie jar) driving the app."""
    async with AsyncClient(
        transport=asgi_transport, base_url="http://testserver"
    ) as instance:
        yield instance


@pytest.fixture
async def make_client(
    asgi_transport: ASGITransport,
) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Factory for *more* browsers on the same app (own cookie jars), e.g. a
    second device of the same account. Closed automatically."""
    made: list[AsyncClient] = []

    def factory() -> AsyncClient:
        made.append(AsyncClient(transport=asgi_transport, base_url="http://testserver"))
        return made[-1]

    try:
        yield factory
    finally:
        for instance in made:
            await instance.aclose()


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
        """Apply to cook (the application starts ``pending``)."""
        return await client.post("/api/cooks", json=body or COOK_BODY)

    async def _user_id(email: str) -> uuid.UUID:
        async with get_sessionmaker()() as session:
            user_id = await session.scalar(select(User.id).where(User.email == email))
        assert user_id is not None, email
        return user_id

    async def approve(email: str = "user@example.com") -> None:
        """Accept the account's pending cook application the way the back
        office does (``admin.service``), as an operator (no admin account -
        so admin counts and inboxes stay untouched)."""
        async with get_sessionmaker()() as session:
            await admin_service.accept_application(session, await _user_id(email), None)

    async def reject(
        email: str = "user@example.com", reason: str = "Not quite ready yet"
    ) -> None:
        async with get_sessionmaker()() as session:
            await admin_service.reject_application(
                session, await _user_id(email), None, reason
            )

    async def customer(email: str = "user@example.com"):
        """Register + login in one step; returns the login response."""
        await register(email)
        return await login(email)

    async def cook(email: str = "chef@example.com"):
        """Register + login + apply + get accepted: a working kitchen. Returns
        the application response (201)."""
        await customer(email)
        applied = await become_cook()
        assert applied.status_code == 201, applied.text
        await approve(email)
        return applied

    async def grant_role(email: str, role: str) -> None:
        """Add a role straight in the database - the only way the admin role
        is ever granted (the API cannot; see scripts/seed.py)."""
        async with get_sessionmaker()() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None, email
            user.roles = [*user.roles, role]
            await session.commit()

    async def admin(email: str = "admin@example.com"):
        """Register + grant admin + login; returns the login response."""
        await register(email)
        await grant_role(email, ROLE_ADMIN)
        return await login(email)

    return SimpleNamespace(
        client=client,
        register=register,
        login=login,
        become_cook=become_cook,
        approve=approve,
        reject=reject,
        customer=customer,
        cook=cook,
        grant_role=grant_role,
        admin=admin,
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


# --- orders: two cooks, two customers, a small menu -----------------------------------

ORDERS = "/api/me/orders"
COOK_ORDERS = "/api/cooks/me/orders"
ADDRESSES = "/api/me/addresses"
HOME = {
    "label": "Home",
    "recipient": "Bea Buyer",
    "phone": "+1 555 0100",
    "line1": "12 Lantern Lane",
    "city": "Springfield",
}
CHEF_A, CHEF_B = "chef-a@example.com", "chef-b@example.com"
BUYER, OTHER_BUYER = "buyer@example.com", "other@example.com"

DISHES = {
    # key: (cook, name, price)
    "curry": (CHEF_A, "Veg curry", 800),
    "tart": (CHEF_A, "Custard tart", 500),
    "pizza": (CHEF_B, "Pizza margherita", 900),
}
NAMES = {
    CHEF_A: "Chef Ana",
    CHEF_B: "Chef Bruno",
    BUYER: "Bea Buyer",
    OTHER_BUYER: "Otto Other",
}


@pytest.fixture
async def market(accounts) -> SimpleNamespace:
    """Two cooks with DISHES and two registered customers; nobody signed in."""
    client = accounts.client
    ids: dict[str, str] = {}
    for cook in (CHEF_A, CHEF_B):
        await accounts.cook(cook)
        await client.patch("/api/me/profile", json={"display_name": NAMES[cook]})
        for key, (owner, name, price) in DISHES.items():
            if owner == cook:
                created = await client.post(
                    "/api/me/dishes", json={"name": name, "price": price, "portions": 5}
                )
                assert created.status_code == 201, created.text
                ids[key] = created.json()["id"]
        await client.post("/api/auth/logout")
    for buyer in (BUYER, OTHER_BUYER):
        await accounts.customer(buyer)
        await client.patch("/api/me/profile", json={"display_name": NAMES[buyer]})
        await client.post("/api/auth/logout")
    client.cookies.clear()

    async def login(email: str) -> None:
        client.cookies.clear()
        response = await accounts.login(email)
        assert response.status_code == 200, response.text

    async def add(key: str, quantity: int = 1) -> None:
        response = await client.post(
            "/api/cart/items", json={"dish_id": ids[key], "quantity": quantity}
        )
        assert response.status_code == 200, response.text

    addresses: dict[str, str] = {}

    async def address() -> str:
        """The signed-in user's address id (created on first use)."""
        me = (await client.get("/api/me")).json()["email"]
        if me not in addresses:
            created = await client.post(ADDRESSES, json=HOME)
            assert created.status_code == 201, created.text
            addresses[me] = created.json()["id"]
        return addresses[me]

    async def place(**body):
        """POST /api/me/orders to the signed-in user's address."""
        return await client.post(ORDERS, json={"address_id": await address(), **body})

    by_name = {name: email for email, name in NAMES.items()}

    async def complete(order: dict) -> dict:
        """The whole happy path of a ``placed`` order: its cook accepts it and
        marks it ready, then its customer confirms receipt (which is what
        completes it). Leaves the customer signed in; returns the order."""
        await login(by_name[order["cook"]["name"]])
        for status in ("accepted", "ready"):
            moved = await client.patch(
                f"{COOK_ORDERS}/{order['id']}", json={"status": status}
            )
            assert moved.status_code == 200, moved.text
        await login(by_name[order["customer"]["name"]])
        received = await receive(client, order["id"])
        assert received.status_code == 200, received.text
        return received.json()

    async def order(
        *lines: tuple[str, int], buyer: str = BUYER, note: str | None = None
    ) -> dict:
        """Sign in as ``buyer``, fill the cart, place it; returns the order."""
        await login(buyer)
        for key, quantity in lines:
            await add(key, quantity)
        response = await place(**({"note": note} if note else {}))
        assert response.status_code == 201, response.text
        return response.json()

    return SimpleNamespace(
        client=client,
        ids=ids,
        login=login,
        add=add,
        address=address,
        place=place,
        order=order,
        complete=complete,
    )


async def receive(client, order_id: str):
    """The signed-in *customer* confirms they received a ready order - the
    only way an order is completed."""
    return await client.post(f"{ORDERS}/{order_id}/receive")


async def set_order_times(order_id: str, **columns) -> None:
    """Backdate / stamp an order straight in the database (``created_at``,
    ``accepted_at``, ``completed_at``, ...) - time-based dashboards need it."""
    async with get_sessionmaker()() as session:
        await session.execute(
            update(Order).where(Order.id == uuid.UUID(order_id)).values(**columns)
        )
        await session.commit()

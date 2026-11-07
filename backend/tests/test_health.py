"""``GET /api/health`` - the probe the frontend renders.

These are the cheapest tests in the suite and they catch the most annoying
deployment bug: an app that imports but never answers.
"""

from __future__ import annotations

import pytest

from app.api import health as health_module
from app.core.config import Settings
from app.main import create_app


async def test_health_reports_ok(client) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"


async def test_health_confirms_sqlite_wal_and_foreign_keys(client) -> None:
    """The pragmas this project depends on must be visible through the probe.

    The temp database is a real file, so ``journal_mode`` is genuinely ``wal``
    and ``foreign_keys`` is genuinely ON - exactly what production gets.
    """
    body = (await client.get("/api/health")).json()
    info = body["database_info"]
    assert info["engine"] == "sqlite"
    assert info["journal_mode"] == "wal"
    assert info["foreign_keys"] is True


async def test_health_is_503_when_the_database_is_unreachable(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom() -> dict[str, str]:
        msg = "simulated database outage"
        raise RuntimeError(msg)

    monkeypatch.setattr(health_module, "_inspect_database", _boom)
    response = await client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "error"


async def test_process_time_header_is_set(client) -> None:
    response = await client.get("/api/health")
    assert float(response.headers["x-process-time"]) >= 0


async def test_v1_route_table_starts_empty(client) -> None:
    """The version marker is currently the only v1 route; feature routers bolt on."""
    response = await client.get("/api/v1")
    assert response.status_code == 200
    assert response.json()["version"] == "v1"


def test_docs_are_hidden_in_production(environment: Settings) -> None:
    """OpenAPI in a production namespace is a free map of the attack surface."""
    production = Settings(ENVIRONMENT="production", DEBUG=False)
    app = create_app(production)
    assert app.docs_url is None
    assert app.openapi_url is None

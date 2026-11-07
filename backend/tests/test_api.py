"""API surface: the backend is an API-only service (the frontend is its own app).

Covers the root metadata route, the project-wide JSON error contract, and the
OpenAPI document that describes the v1 surface.
"""

from __future__ import annotations


async def test_root_reports_service_metadata(client) -> None:
    """ "/`` self-describes the API so a bare backend port is never a mystery."""
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Plateboard API"
    assert body["environment"] == "test"
    assert body["health"] == "/api/health"
    assert body["v1"] == "/api/v1"


async def test_unknown_path_returns_the_json_error_envelope(client) -> None:
    """Every non-2xx, including the plain 404, uses the project error shape."""
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"


async def test_openapi_documents_the_api_surface(client) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/health" in paths
    assert "/api/v1" in paths
    assert {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/me",
        "/api/me/profile",
        "/api/cooks",
        "/api/cooks/me",
        "/api/cooks/{user_id}",
        "/api/me/dishes",
        "/api/me/dishes/{dish_id}",
        "/api/dishes",
        "/api/dishes/{dish_id}",
    } <= set(paths)
    assert "/api/v1/dishes" not in paths  # public menu moved to /api/dishes

"""API docs pages: CDN by default, self-hosted assets with ``DOCS_ASSETS_DIR``.

Every test passes ``DOCS_ASSETS_DIR`` explicitly, so the outcome never
depends on a developer's ``backend/.env``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.docs import REQUIRED_DOCS_ASSETS, DocsAssetsError
from app.main import create_app

CDN = "cdn.jsdelivr.net"
OPENAPI = "/api/v1/openapi.json"


@asynccontextmanager
async def docs_client(
    settings: Settings, *, root_path: str = ""
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(settings), root_path=root_path)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def assets_dir(tmp_path: Path) -> Path:
    """Stand-ins for the swagger-ui-dist / redoc files (content is irrelevant)."""
    directory = tmp_path / "docs-assets"
    directory.mkdir()
    for name in REQUIRED_DOCS_ASSETS:
        (directory / name).write_text(f"/* {name} */")
    return directory


# --- default: FastAPI's CDN pages, unchanged -------------------------------------


async def test_docs_use_the_cdn_by_default(environment) -> None:
    async with docs_client(Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=None)) as client:
        swagger = await client.get("/docs")
        redoc = await client.get("/redoc")
        assets = await client.get("/docs/assets/swagger-ui-bundle.js")
    assert swagger.status_code == 200
    assert f"https://{CDN}/npm/swagger-ui-dist@5/swagger-ui-bundle.js" in swagger.text
    assert f"https://{CDN}/npm/redoc@2/bundles/redoc.standalone.js" in redoc.text
    assert assets.status_code == 404  # nothing mounted


async def test_blank_setting_means_cdn(environment) -> None:
    """``DOCS_ASSETS_DIR=`` in a .env file is "unset", not the current dir."""
    settings = Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR="  ")  # type: ignore[arg-type]
    assert settings.docs_assets_path is None


# --- DOCS_ASSETS_DIR: everything from the API itself ---------------------------------


async def test_self_hosted_swagger_ui(environment, assets_dir: Path) -> None:
    settings = Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=assets_dir)
    async with docs_client(settings) as client:
        page = await client.get("/docs")
        bundle = await client.get("/docs/assets/swagger-ui-bundle.js")
        css = await client.get("/docs/assets/swagger-ui.css")
        oauth2 = await client.get("/docs/oauth2-redirect")
        spec = await client.get(OPENAPI)

    assert page.status_code == 200
    assert CDN not in page.text and "fastapi.tiangolo.com" not in page.text
    assert 'src="/docs/assets/swagger-ui-bundle.js"' in page.text
    assert 'href="/docs/assets/swagger-ui.css"' in page.text
    assert f"url: '{OPENAPI}'" in page.text
    assert "Plateboard API - Swagger UI" in page.text

    assert bundle.status_code == 200
    assert bundle.text == "/* swagger-ui-bundle.js */"
    assert css.status_code == 200
    assert oauth2.status_code == 200
    assert spec.status_code == 200
    # The assets route is plumbing, not API surface.
    assert not any(path.startswith("/docs") for path in spec.json()["paths"])


async def test_self_hosted_redoc_needs_no_cdn_or_google_fonts(
    environment, assets_dir: Path
) -> None:
    settings = Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=assets_dir)
    async with docs_client(settings) as client:
        page = await client.get("/redoc")
    assert page.status_code == 200
    assert 'src="/docs/assets/redoc.standalone.js"' in page.text
    assert CDN not in page.text
    assert "fonts.googleapis.com" not in page.text


async def test_self_hosted_docs_respect_root_path(environment, assets_dir: Path) -> None:
    """Behind a path-prefixing proxy every URL must carry the prefix - same as
    FastAPI's own docs pages."""
    settings = Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=assets_dir)
    async with docs_client(settings, root_path="/backend") as client:
        page = await client.get("/docs")
    assert 'src="/backend/docs/assets/swagger-ui-bundle.js"' in page.text
    assert "url: '/backend/api/v1/openapi.json'" in page.text


def test_relative_dir_resolves_against_backend_root(environment) -> None:
    from app.core.config import BACKEND_ROOT

    settings = Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=Path("docs-assets"))
    assert settings.docs_assets_path == BACKEND_ROOT / "docs-assets"


# --- misconfiguration fails at startup, production stays closed -----------------------


def test_missing_assets_fail_fast(environment, assets_dir: Path) -> None:
    (assets_dir / "redoc.standalone.js").unlink()
    with pytest.raises(DocsAssetsError, match="redoc.standalone.js"):
        create_app(Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=assets_dir))


def test_missing_directory_fails_fast(environment, tmp_path: Path) -> None:
    with pytest.raises(DocsAssetsError, match="not a directory"):
        create_app(Settings(ENVIRONMENT="test", DOCS_ASSETS_DIR=tmp_path / "nope"))


async def test_production_still_hides_docs(environment, assets_dir: Path) -> None:
    settings = Settings(ENVIRONMENT="production", DEBUG=False, DOCS_ASSETS_DIR=assets_dir)
    async with docs_client(settings) as client:
        for path in ("/docs", "/redoc", "/docs/assets/swagger-ui-bundle.js", OPENAPI):
            assert (await client.get(path)).status_code == 404, path

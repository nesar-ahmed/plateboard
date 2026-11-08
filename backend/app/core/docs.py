"""Self-hosted Swagger UI / ReDoc for hosts whose browsers cannot reach a CDN.

FastAPI's built-in ``/docs`` and ``/redoc`` pages are tiny HTML shells that
pull their JavaScript/CSS from ``cdn.jsdelivr.net``. Without access to that
CDN the page stays blank (``SwaggerUIBundle is not defined``) even though the
API and ``openapi.json`` are fine.

With ``DOCS_ASSETS_DIR`` set, :func:`register_self_hosted_docs` replaces those
two pages with identical ones whose assets come from the API itself, mounted
at ``/docs/assets`` - FastAPI's documented "self-hosting JavaScript and CSS for
docs" recipe. Without it nothing changes: FastAPI serves its CDN-based pages.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

__all__ = [
    "DOCS_ASSETS_MOUNT",
    "REQUIRED_DOCS_ASSETS",
    "DocsAssetsError",
    "register_self_hosted_docs",
]

DOCS_URL = "/docs"
REDOC_URL = "/redoc"
DOCS_ASSETS_MOUNT = "/docs/assets"

SWAGGER_JS = "swagger-ui-bundle.js"  # swagger-ui-dist@5
SWAGGER_CSS = "swagger-ui.css"  # swagger-ui-dist@5
REDOC_JS = "redoc.standalone.js"  # redoc@2 (bundles/)
FAVICON = "favicon-32x32.png"  # ships with swagger-ui-dist; optional

REQUIRED_DOCS_ASSETS: tuple[str, ...] = (SWAGGER_JS, SWAGGER_CSS, REDOC_JS)


class DocsAssetsError(RuntimeError):
    """``DOCS_ASSETS_DIR`` is set but unusable - fail at startup, not in the browser."""


def _check_assets(directory: Path) -> None:
    if not directory.is_dir():
        msg = f"DOCS_ASSETS_DIR={directory} is not a directory"
        raise DocsAssetsError(msg)
    missing = [name for name in REQUIRED_DOCS_ASSETS if not (directory / name).is_file()]
    if missing:
        msg = f"DOCS_ASSETS_DIR={directory} is missing {', '.join(missing)}"
        raise DocsAssetsError(msg)


def register_self_hosted_docs(app: FastAPI, directory: Path) -> None:
    """Serve ``/docs`` and ``/redoc`` with assets from ``directory``.

    The app must be created with ``docs_url=None`` / ``redoc_url=None`` (so
    FastAPI does not add its CDN pages) and with an ``openapi_url``. The
    handlers mirror ``FastAPI.setup()``: same titles, OAuth2 redirect, Swagger
    parameters and ``root_path`` handling - only the asset URLs differ.
    """
    _check_assets(directory)
    openapi_url = app.openapi_url
    if openapi_url is None:
        msg = "self-hosted docs need an openapi_url"
        raise DocsAssetsError(msg)

    app.mount(DOCS_ASSETS_MOUNT, StaticFiles(directory=directory), name="docs-assets")

    def asset(request: Request, name: str) -> str:
        root_path = request.scope.get("root_path", "").rstrip("/")
        return f"{root_path}{DOCS_ASSETS_MOUNT}/{name}"

    async def swagger_ui_html(request: Request) -> HTMLResponse:
        root_path = request.scope.get("root_path", "").rstrip("/")
        oauth2_redirect_url = app.swagger_ui_oauth2_redirect_url
        return get_swagger_ui_html(
            openapi_url=root_path + openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_js_url=asset(request, SWAGGER_JS),
            swagger_css_url=asset(request, SWAGGER_CSS),
            swagger_favicon_url=asset(request, FAVICON),
            oauth2_redirect_url=(
                root_path + oauth2_redirect_url if oauth2_redirect_url else None
            ),
            init_oauth=app.swagger_ui_init_oauth,
            swagger_ui_parameters=app.swagger_ui_parameters,
        )

    async def swagger_ui_redirect(_request: Request) -> HTMLResponse:
        return get_swagger_ui_oauth2_redirect_html()

    async def redoc_html(request: Request) -> HTMLResponse:
        root_path = request.scope.get("root_path", "").rstrip("/")
        return get_redoc_html(
            openapi_url=root_path + openapi_url,
            title=f"{app.title} - ReDoc",
            redoc_js_url=asset(request, REDOC_JS),
            redoc_favicon_url=asset(request, FAVICON),
            with_google_fonts=False,  # another CDN; ReDoc falls back to system fonts
        )

    app.add_route(DOCS_URL, swagger_ui_html, include_in_schema=False)
    if app.swagger_ui_oauth2_redirect_url:
        app.add_route(
            app.swagger_ui_oauth2_redirect_url,
            swagger_ui_redirect,
            include_in_schema=False,
        )
    app.add_route(REDOC_URL, redoc_html, include_in_schema=False)

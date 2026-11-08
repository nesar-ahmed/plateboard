"""Application factory and ASGI entry point.

This process serves the **API only** - the frontend runs as its own Next.js
standalone server (see the README's hosting section). Start the backend::

    uv run python -m app.main      # from backend/

The module-level ``app`` keeps the classic entry point working too::

    uv run uvicorn app.main:app
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.core.db import dispose_engine, get_engine
from app.core.docs import register_self_hosted_docs
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {"name": "system", "description": "Health probes and service metadata."},
    {"name": "auth", "description": "Accounts, roles and server-side sessions."},
    {"name": "cooks", "description": "Cook profiles (role: cook)."},
    {
        "name": "dishes",
        "description": "Menu dishes: cook-only management (/api/me/dishes) "
        "and the public active-dish menu (/api/dishes).",
    },
    {
        "name": "zones",
        "description": "Service-grid zones (slug + x/y); distances are grid steps.",
    },
    {
        "name": "cart",
        "description": "The signed-in user's cart: dishes and quantities (/api/me/cart).",
    },
    {"name": "v1", "description": "API version 1 - under development."},
]


def run_migrations() -> None:
    """Bring the database to head with the Alembic migrations in ``migrations/``.

    ``alembic.ini`` leaves the URL empty on purpose; ``migrations/env.py`` reads
    it from :func:`app.core.config.get_settings`, so migrations and the app can
    never point at different databases.
    """
    config = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    # Absolute paths: alembic otherwise resolves these against the *cwd*.
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown work that needs the running event loop."""
    settings: Settings = app.state.settings
    configure_logging(settings)

    # Touching the engine here creates the SQLite file/directory and fails fast
    # on a bad DATABASE_URL instead of on the first request.
    #
    # Schema migrations deliberately do NOT run here: Alembic's env.py drives
    # its own event loop, which cannot start inside the live server loop. The
    # `python -m app.main` entry point migrates before uvicorn boots; otherwise
    # run `uv run alembic upgrade head` (see README).
    get_engine()
    logger.info(
        "%s v%s starting (env=%s, db=%s)",
        settings.APP_NAME,
        __version__,
        settings.ENVIRONMENT,
        settings.DATABASE_URL,
    )
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("%s stopped", settings.APP_NAME)


def register_service_root(app: FastAPI, settings: Settings) -> None:
    """Small metadata route at ``/`` so the bare API server is self-describing.

    The frontend is a separate Next.js standalone process; this backend hosts
    only the ``/api`` surface. Behind nginx, ``/`` goes to the frontend and
    this route is reached via the API origin directly.
    """

    @app.get("/", tags=["system"], summary="Service metadata")
    async def service_info() -> dict[str, Any]:
        return {
            "name": settings.APP_NAME,
            "version": __version__,
            "environment": settings.ENVIRONMENT,
            "health": "/api/health",
            "v1": settings.API_V1_PREFIX,
            "docs": "/docs" if settings.docs_enabled else None,
        }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests call this with their own ``Settings``."""
    settings = settings or get_settings()
    # Self-hosted docs assets (DOCS_ASSETS_DIR) replace FastAPI's CDN-based
    # /docs + /redoc pages; without the setting FastAPI's defaults are used.
    docs_assets = settings.docs_assets_path if settings.docs_enabled else None
    cdn_docs = settings.docs_enabled and docs_assets is None

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        debug=settings.DEBUG,
        root_path=settings.ROOT_PATH,
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
        # Interactive docs are handy in development, an attack surface in production.
        docs_url="/docs" if cdn_docs else None,
        redoc_url="/redoc" if cdn_docs else None,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json"
        if settings.docs_enabled
        else None,
    )
    app.state.settings = settings

    register_exception_handlers(app)

    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            # Wildcard origins and cookies cannot be combined safely.
            allow_credentials="*" not in settings.CORS_ORIGINS,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    app.middleware("http")(add_process_time_header)

    app.include_router(api_router)
    if docs_assets is not None:
        register_self_hosted_docs(app, docs_assets)
    register_service_root(app, settings)
    return app


async def add_process_time_header(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Small observability hook: proxies can log per-request latency."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    if response.status_code >= 500:
        logger.error(
            "%s %s -> %d in %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
    return response


def cli(argv: list[str] | None = None) -> None:
    """Start the API server::

        uv run python -m app.main

    Migrates the database, then serves the API on one host/port. The frontend
    runs as its own Next.js standalone process (see the README)."""
    parser = argparse.ArgumentParser(
        prog="plateboard", description="Serve the Plateboard API."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Reload on backend source changes (development).",
    )
    args = parser.parse_args(argv)

    # Migrations up front: fail loudly here, not inside the server loop.
    run_migrations()

    import uvicorn

    if args.reload:
        # The reloader spawns a fresh process, so it needs the import string.
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)


app = create_app()

if __name__ == "__main__":
    cli()

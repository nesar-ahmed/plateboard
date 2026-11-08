"""Application settings.

Everything configurable is declared here and read from the environment (or a
local ``.env`` file). Modules should depend on :func:`get_settings` instead of
reading ``os.environ`` themselves, so configuration stays typed, validated and
documented in a single place.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]

#: Filesystem root of the backend package (the directory containing ``app/``).
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration.

    Values are loaded with the following precedence (highest wins):

    1. keyword arguments passed to ``Settings(...)`` (used by tests)
    2. real environment variables
    3. the ``backend/.env`` file
    4. the defaults declared below
    """

    model_config = SettingsConfigDict(
        # A single source of truth for local config: backend/.env (copy it from
        # backend/.env.example). Anchored to BACKEND_ROOT so it loads no matter
        # which directory the process starts in. Real environment variables
        # (tests, pm2, Docker) still take precedence over the file.
        env_file=(BACKEND_ROOT / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -----------------------------------------------------
    APP_NAME: str = "Plateboard API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = "local"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    ROOT_PATH: str = ""

    # --- database --------------------------------------------------------
    # SQLite is the default; swap in any SQLAlchemy URL (postgres+asyncpg, ...)
    # without touching application code. Relative SQLite paths resolve against
    # the backend root, so the file always lands in backend/plateboard.db.
    DATABASE_URL: str = "sqlite+aiosqlite:///./plateboard.db"
    DATABASE_ECHO: bool = False
    SQL_ECHO: bool = False

    # --- http ------------------------------------------------------------
    # Accepts either a JSON array ('["http://a", "http://b"]') or a plain
    # comma separated list ("http://a,http://b") in the environment.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    TRUST_X_FORWARDED_HOST: bool = False

    # --- API docs ---------------------------------------------------------
    # /docs (Swagger UI) and /redoc load their JS/CSS from the jsDelivr CDN by
    # default, so the *browser* needs internet access. Point this at a local
    # directory holding those files to serve them from the API itself instead
    # (air-gapped hosts, locked-down networks). Relative paths resolve against
    # the backend root. Expected files: swagger-ui-bundle.js, swagger-ui.css
    # (swagger-ui-dist@5) and redoc.standalone.js (redoc@2); see README.
    DOCS_ASSETS_DIR: Path | None = None

    # --- sessions ---------------------------------------------------------
    # Server-side sessions (table `sessions`) carried in an HTTP-only cookie.
    SESSION_COOKIE_NAME: str = "plateboard_session"
    SESSION_TTL_DAYS: int = 7

    # --- carts -----------------------------------------------------------
    # Guests get a cart too, identified by a random token in this HTTP-only
    # cookie (only its SHA-256 is stored). Logging in moves the guest cart to
    # the account and clears the cookie.
    CART_COOKIE_NAME: str = "plateboard_cart"
    CART_TTL_DAYS: int = 30

    # --- observability ---------------------------------------------------
    LOG_LEVEL: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    LOG_JSON: bool = False

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Allow ``CORS_ORIGINS=http://a,http://b`` in addition to JSON."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return stripped  # let pydantic decode the JSON array
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("DOCS_ASSETS_DIR", mode="before")
    @classmethod
    def _blank_dir_is_unset(cls, value: object) -> object:
        """``DOCS_ASSETS_DIR=`` (empty, as in .env templates) means "use the CDN"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def docs_assets_path(self) -> Path | None:
        """Absolute self-hosted docs-assets directory, or ``None`` for the CDN."""
        if self.DOCS_ASSETS_DIR is None:
            return None
        path = self.DOCS_ASSETS_DIR.expanduser()
        return path if path.is_absolute() else BACKEND_ROOT / path

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == "test"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def docs_enabled(self) -> bool:
        """Interactive docs are served everywhere except production."""
        return not self.is_production

    @property
    def sqlite_file(self) -> Path | None:
        """Filesystem path of the SQLite database, if this is a file URL.

        Relative paths resolve against :data:`BACKEND_ROOT` - not the process
        working directory - so ``./plateboard.db`` always means
        ``backend/plateboard.db``.
        """
        prefix = "sqlite+aiosqlite:///"
        if not self.DATABASE_URL.startswith(prefix):
            return None
        raw = self.DATABASE_URL.removeprefix(prefix)
        if not raw or raw == ":memory:" or "mode=memory" in raw:
            return None
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = BACKEND_ROOT / candidate
        return candidate

    @property
    def resolved_database_url(self) -> str:
        """``DATABASE_URL`` with relative SQLite paths made absolute.

        Engines and Alembic must build from this so the file location is the
        same no matter which directory the process was started in.
        """
        target = self.sqlite_file
        if target is None:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///{target}"

    def ensure_sqlite_dir(self) -> None:
        """Create the parent directory for file-based SQLite databases."""
        target = self.sqlite_file
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance.

    Tests that need different configuration should build their own
    ``Settings(...)`` object rather than mutating this one, or call
    :func:`cache_clear` first.
    """
    return Settings()


def reload_settings() -> Settings:
    """Drop the cache and re-read the environment (used by tooling/tests)."""
    get_settings.cache_clear()
    return get_settings()

# Plateboard backend

FastAPI + SQLAlchemy 2 (async) on **SQLite (WAL mode, foreign keys ON)**,
schema versioned with **Alembic**.

The backend is an **API-only** service. The frontend runs as its own Next.js
standalone server (see [`../frontend/README.md`](../frontend/README.md)); on a
VPS, nginx sits in front of both.

## Run

From this directory:

```bash
uv sync --all-groups
uv run python -m app.main        # migrates, then serves the API on :8000
```

- API metadata: <http://127.0.0.1:8000/>
- Health probe: <http://127.0.0.1:8000/api/health>
- Docs: <http://127.0.0.1:8000/docs>

Flags: `--host`, `--port`, `--reload`. Alternate entry point:
`uv run uvicorn app.main:app` (run `uv run alembic upgrade head` yourself, since
this path does not migrate).

## Configuration

All settings load from environment variables, `backend/.env`, then code
defaults (in that precedence order). Copy the committed template to start:

```bash
cp .env.example .env          # local defaults work as-is
```

`.env` is git-ignored (never pushed to GitHub); `.env.example` documents every
variable. See `app/core/config.py` for the typed definitions.

## Database

The development database is a single file at the backend root:
`backend/plateboard.db` (git-ignored, plus its `-wal`/`-shm` sidecars). Set via
`DATABASE_URL`; relative SQLite paths always resolve to this directory.

## Migrations (Alembic)

```bash
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "add widgets"   # after defining a model
uv run alembic downgrade -1
```

Migrations live in `migrations/versions/`; `0001_baseline.py` is the clean v1
starting point. `migrations/env.py` reads the DSN from settings (never from
`alembic.ini`), and `uv run python -m app.main` runs `upgrade head` on boot.

## Tests

```bash
uv run pytest                       # 11 tests
uv run pytest --cov=app             # with coverage
uv run ruff check app tests migrations
uv run mypy app
```

Each test gets its own **temporary SQLite file** under `tmp_path`, migrated by
Alembic, so the suite never touches `plateboard.db` yet still exercises WAL and
foreign-key pragmas for real.

## Layout

```text
app/
  api/
    health.py     # GET /api/health (NOT versioned - stable probe URL)
    router.py     # mounts /api (health + v1)
    deps.py       # shared DB-session dependency
    v1/           # API version 1, under development
  core/           # settings, engine (WAL/FK pragmas), logging, error envelope
  shared/         # declarative Base + mixins, schema helpers
  main.py         # create_app(), service-root route, API entry point
migrations/       # Alembic env.py + versions/
tests/            # isolated temp-DB fixtures + health/migrations/API-surface tests
```

## API surface

| Method | Path          | Description                                   |
| ------ | ------------- | --------------------------------------------- |
| GET    | `/api/health` | API + database status and SQLite pragmas      |
| GET    | `/api/v1`     | v1 marker; feature routers get mounted here   |
| GET    | `/`           | Backend service metadata (JSON)               |

Config table and full VPS hosting (pm2 + nginx) are in the
[repo root README](../README.md).

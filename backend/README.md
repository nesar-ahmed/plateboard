# Plateboard backend

FastAPI + SQLAlchemy 2 (async) on **SQLite (WAL mode, foreign keys ON)**,
schema versioned with **Alembic**.

The backend is an **API-only** service with cookie-based auth, additive
**customer/cook roles**, editable profiles and cook-only endpoints guarded by
the `require_login`/`require_cook` dependencies. The frontend runs as its own
Next.js standalone server (see [`../frontend/README.md`](../frontend/README.md));
on a VPS, nginx sits in front of both.

## Run

From this directory:

```bash
uv sync --all-groups
uv run python -m app.main        # migrates, then serves the API on :8000
```

- API metadata: <http://127.0.0.1:8000/>
- Health probe: <http://127.0.0.1:8000/api/health>
- Auth: `POST /api/auth/register`, `POST /api/auth/login`,
  `POST /api/auth/logout`, `GET /api/me` (HTTP-only session cookie)
- Profiles & cooks: `PATCH /api/me/profile`, `POST /api/cooks` (become a
  cook), `GET|PATCH /api/cooks/me` (cook role required)
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

Migrations live in `migrations/versions/` (`0001_baseline.py` starts the v1
slate, `0002` adds auth, `0003` adds roles/profile fields + the cooks table).
`migrations/env.py` reads the DSN from settings (never from `alembic.ini`), and
`uv run python -m app.main` runs `upgrade head` on boot.

## Tests

```bash
uv run pytest                       # 50 tests
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
    auth/         # accounts + roles + profiles: router, service, models, scrypt
    cooks/        # become-a-cook + cook-only endpoints (require_cook -> 403)
    router.py     # mounts /api (health + auth + cooks + v1)
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
| POST   | `/api/auth/register` | Create account (409 on taken email, 422 short password); role defaults to `customer` |
| POST   | `/api/auth/login`    | Generic 401 on any bad credentials; sets HTTP-only session cookie |
| POST   | `/api/auth/logout`   | Revokes the session server-side (401 without one) |
| GET    | `/api/me`     | Current user: profile fields + roles          |
| PATCH  | `/api/me/profile` | Edit display_name/bio/area (length-validated) |
| POST   | `/api/cooks`  | Become a cook: headline + specialty tags (409 if already) |
| GET    | `/api/cooks/me` | My cook profile - 403 without the cook role |
| PATCH  | `/api/cooks/me` | Update cook profile - 403 without the cook role |
| GET    | `/api/v1`     | v1 marker; feature routers get mounted here   |
| GET    | `/`           | Backend service metadata (JSON)               |

Config table and full VPS hosting (pm2 + nginx) are in the
[repo root README](../README.md).

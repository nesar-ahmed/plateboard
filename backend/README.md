# Plateboard backend

FastAPI + SQLAlchemy 2 (async) on **SQLite (WAL mode, foreign keys ON)**,
schema versioned with **Alembic**.

The backend is an **API-only** service with cookie-based auth, additive
**customer/cook roles**, editable profiles, cook-only endpoints and
cook-owned **dishes** (fixed allergen enum, minor-unit prices, public menu of
active dishes) guarded by the `require_login`/`require_cook` dependencies. The
frontend runs as its own Next.js standalone server (see
[`../frontend/README.md`](../frontend/README.md)); on a VPS, nginx sits in
front of both.

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
  cook), `GET|PATCH /api/cooks/me` (cook role required); public cook pages:
  `GET /api/cooks` (directory), `GET /api/cooks/{user_id}` (profile)
- Dishes: `POST|GET /api/me/dishes`, `GET|PATCH|DELETE /api/me/dishes/{id}`
  (cook only, own dishes only); public menu: `GET /api/dishes` (active only,
  `?q=` name search + `limit`/`offset`), `GET /api/dishes/{id}`
- Seeding demo data: `uv run python scripts/seed.py` (safe to re-run; prints
  fresh login credentials)
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
slate, `0002` adds auth, `0003` adds roles/profile fields + the cooks table,
`0004` adds the dishes table). `migrations/env.py` reads the DSN from settings
(never from `alembic.ini`), and `uv run python -m app.main` runs
`upgrade head` on boot.

## Seeding demo data

```bash
uv run python scripts/seed.py     # 10 cooks (40 dishes) + 5 customers
```

All accounts are invented and use `@example.com` emails. Passwords are
generated fresh at run time and printed - re-running reuses the existing
accounts but resets their passwords to what is printed, so **the printed
credentials always work**. Dishes are keyed on (cook, name): existing dishes
are left untouched, so dashboard edits and deactivations survive a re-run.
The script runs migrations first, so it works against a brand-new database.

## Tests

```bash
uv run pytest                       # 85 tests
uv run pytest --cov=app             # with coverage
uv run ruff check app tests migrations scripts
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
    cooks/        # become-a-cook, cook-only endpoints, public cook pages
    dishes/       # cook-owned menu CRUD + public active-dish menu
    router.py     # mounts /api (health + auth + cooks + dishes + v1)
    deps.py       # shared DB-session dependency
    v1/           # API version 1, under development
  core/           # settings, engine (WAL/FK pragmas), logging, error envelope
  shared/         # declarative Base + mixins, schema helpers
  main.py         # create_app(), service-root route, API entry point
migrations/       # Alembic env.py + versions/
scripts/seed.py   # idempotent demo data (cooks/dishes/customers + credentials)
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
| GET    | `/api/cooks`  | Public cook directory (paginated), no auth |
| GET    | `/api/cooks/{user_id}` | Public cook profile page (404 without one) |
| POST   | `/api/me/dishes` | Add a dish (cook only; 422 unless price > 0 and allergens are known) |
| GET    | `/api/me/dishes` | My dashboard list - deactivated dishes included, newest first |
| GET    | `/api/me/dishes/{id}` | One of my dishes (another cook's id -> 404) |
| PATCH  | `/api/me/dishes/{id}` | Edit / deactivate (`{"active": false}`) / reactivate own dish |
| DELETE | `/api/me/dishes/{id}` | Remove own dish for good |
| GET    | `/api/dishes` | Public menu - active dishes only; `?q=` name LIKE search, `cook_id`, `limit`/`offset` paging |
| GET    | `/api/dishes/{id}` | One active dish (+ its cook's name); deactivated -> 404 |
| GET    | `/api/v1`     | v1 marker; feature routers get mounted here   |
| GET    | `/`           | Backend service metadata (JSON)               |

Config table and full VPS hosting (pm2 + nginx) are in the
[repo root README](../README.md).

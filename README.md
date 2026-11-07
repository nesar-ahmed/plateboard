# Plateboard

Two independent apps that each run as their own process:

- **Backend** — FastAPI + SQLAlchemy 2 (async) on **SQLite with WAL mode and
  foreign keys enabled**, schema managed by **Alembic**. Includes cookie-based
  auth (register/login/logout/me). API v1 lives in `backend/app/api/v1/` and is
  a work in progress. See `backend/README.md`.
- **Frontend** — React (Next.js 16), built in **`standalone` mode**: a
  self-contained Node server (`frontend/.next/standalone/`) you run directly,
  under **pm2**, or behind an **nginx** reverse proxy on a VPS. It shows the
  health of `GET /api/health`. See `frontend/README.md`.

## Prerequisites

| Tool | Why                                      |
| ---- | ---------------------------------------- |
| [uv](https://docs.astral.sh/uv/) | Python deps, lockfile, virtualenv |
| Node.js 20+ / npm             | frontend dev + standalone build  |

## Configure (once)

Every environment variable is loaded from `.env` files - one per app, both
git-ignored so they never reach GitHub. The committed `.env.example` files
document the full variable set; copy and adjust:

```bash
cp backend/.env.example backend/.env         # local defaults work out of the box
cp frontend/.env.example frontend/.env       # API_ORIGIN for the /api proxy
```

Real environment variables (tests, pm2, Docker) always override `.env`.

## Development (two terminals)

```bash
# terminal 1 - API on http://127.0.0.1:8000 (migrates on start)
cd backend
uv sync --all-groups
uv run python -m app.main

# terminal 2 - UI on http://localhost:3000, /api/* proxied to the backend
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000/> — the status pill should read **ok**. The dev
server rewrites `/api/:path*` to `API_ORIGIN` (from `frontend/.env`, default
`http://127.0.0.1:8000`), so the UI fetches relative URLs and the code is
identical in production.

## Tests / quality (backend)

```bash
cd backend
uv run pytest            # 30 tests: health, auth, SQLite pragmas, migrations, API surface
uv run ruff check app tests migrations
uv run mypy app
```

Every test runs against its **own temporary SQLite database** (a real file
under `pytest`'s `tmp_path`, created fresh and migrated with Alembic before the
app starts), so the suite never touches `backend/plateboard.db` and still
exercises the production schema and WAL/foreign-key pragmas end to end.

## Database & migrations

The development database is a single file at the **backend root**:
`backend/plateboard.db` (git-ignored, along with its `-wal`/`-shm` sidecars).
Relative `sqlite` URLs always resolve against the backend directory, so the
file lands there no matter where you start the process from.

Schema changes are managed with **Alembic** (installed, so no raw-SQL runner is
needed); migrations live in `backend/migrations/versions/`
(`0001_baseline.py` starts the v1 slate, `0002_auth_users_sessions.py` adds the
`users` + `sessions` tables).

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "add widgets"   # after defining a model
uv run alembic downgrade -1
```

The DSN always comes from `DATABASE_URL` in settings (`migrations/env.py`),
never from `alembic.ini`. `uv run python -m app.main` migrates on startup; with
any other way of booting (plain `uvicorn app.main:app`), run
`alembic upgrade head` yourself.

## Hosting on a VPS

Build the frontend as a standalone server, then run the two processes side by
side and put nginx in front:

```bash
# 1. Frontend: self-contained Node server in .next/standalone/
cd frontend
cp .env.example .env        # set API_ORIGIN to the backend's real URL first
npm ci
npm run build               # build + postbuild asset copy

# 2. Backend: API only (migrates on start)
cd ../backend
cp .env.example .env        # adjust DATABASE_URL / ENVIRONMENT for the VPS
uv sync
```

**Run the two processes** (both bind to `127.0.0.1`; nginx is the public face):

```bash
HOSTNAME=127.0.0.1 PORT=3000 node frontend/.next/standalone/server.js
cd backend && uv run python -m app.main --host 127.0.0.1 --port 8000
```

**Keep them alive with pm2** - register each as a process and restart on boot:

```bash
pm2 start "node .next/standalone/server.js" --name plateboard-web --cwd frontend \
  --update-env -e HOSTNAME=127.0.0.1 -e PORT=3000
pm2 start "uv run python -m app.main --host 127.0.0.1 --port 8000" \
  --name plateboard-api --cwd backend -i 1
pm2 save && pm2 startup            # respawn on reboot
```

**Put nginx in front** - route by path so the browser stays on one origin:

- `location /api/` -> `proxy_pass http://127.0.0.1:8000;` (the backend)
- `location /_next/static/` -> serve `frontend/.next/static/` from disk (immutable)
- `location /` -> `proxy_pass http://127.0.0.1:3000;` (the frontend)

Add TLS with certbot (`sudo certbot --nginx -d yourdomain`).

## Configuration

All environment variables load from `.env` files (`backend/.env`,
`frontend/.env`), which are **git-ignored**; the committed `.env.example`
files list every variable. Precedence: explicit `Settings(...)` kwargs (tests)
> real env vars > `.env` > code defaults. Backend settings are declared and
validated in `backend/app/core/config.py`:

| Variable             | Default                                 | Notes                               |
| -------------------- | --------------------------------------- | ----------------------------------- |
| `DATABASE_URL`       | `sqlite+aiosqlite:///./plateboard.db`   | relative paths anchor to `backend/` |
| `ENVIRONMENT`        | `local`                                 | `production` hides `/docs` + openapi |
| `CORS_ORIGINS`       | `http://localhost:3000,...`             | only needed if a browser hits the API cross-origin |
| `LOG_LEVEL`          | `INFO`                                  |                                     |
| `SESSION_COOKIE_NAME`| `plateboard_session`                    | HTTP-only session cookie name       |
| `SESSION_TTL_DAYS`   | `7`                                     | server-side session lifetime        |

Frontend-side variables (Next.js):

| Variable          | Default                  | When it matters                          |
| ----------------- | ------------------------ | ---------------------------------------- |
| `API_ORIGIN`      | `http://127.0.0.1:8000`  | dev proxy + standalone rewrite fallback (read at build/dev start) |
| `HOSTNAME`/`PORT` | `0.0.0.0`/`3000`         | runtime env of the standalone `server.js` (not read from `.env`) |

## API surface

| Method | Path               | Description                                              |
| ------ | ------------------ | -------------------------------------------------------- |
| GET    | `/api/health`      | Health probe: API + database status, SQLite pragmas      |
| POST   | `/api/auth/register` | Create account (email lowercased, salted scrypt hash)  |
| POST   | `/api/auth/login`  | Sets HTTP-only `plateboard_session` cookie (server-side session) |
| POST   | `/api/auth/logout` | Revokes the session server-side, clears the cookie       |
| GET    | `/api/me`          | Current user (401 without an active session)             |
| GET    | `/api/v1`          | v1 marker (`{"version": "v1", ...}`)                     |
| GET    | `/`                | Backend service metadata (JSON) - the UI is served by the frontend process |
| GET    | `/docs`            | OpenAPI playground (disabled when `ENVIRONMENT=production`) |

Auth rules: passwords >= 8 chars hashed with stdlib `hashlib.scrypt` +
per-user random salt; emails unique/checked case-insensitively; failed logins
always return the same generic 401 (no account-existence leak); sessions are
stored as SHA-256 token hashes in the `sessions` table, so a DB leak cannot
replay logins.

## Layout

```text
.gitignore                    # root: Python, Node, SQLite artifacts
README.md
backend/
  .env                        # local config (git-ignored, never pushed)
  .env.example                # documented template - committed
  pyproject.toml              # deps, dev group, pytest config
  uv.lock                     # locked dependency versions (uv)
  alembic.ini                 # Alembic paths (DSN deliberately lives in settings)
  plateboard.db               # SQLite dev database (created at startup, ignored)
  app/
    api/
      health.py               # GET /api/health (intentionally NOT versioned)
      auth/                   # register/login/logout/me + scrypt hashing + sessions
      router.py               # mounts everything under /api
      deps.py                 # shared FastAPI dependencies (DB session)
      v1/                     # API version 1 - under development
    core/                     # settings, engine (WAL + FK pragmas), logging, errors
    shared/                   # declarative Base, mixins, schema helpers
    main.py                   # app factory + single-process API entry point
  migrations/                 # Alembic (env.py reads DATABASE_URL from settings)
  tests/                      # per-test temp SQLite DB migrated by Alembic
  README.md
frontend/
  .env                        # local config (git-ignored, never pushed)
  .env.example                # documented template - committed
  src/app/                    # Next.js App Router (health dashboard page)
  next.config.ts              # output: "standalone" + /api rewrite
  .next/standalone/           # `npm run build` self-host server (git-ignored)
  README.md
```

## Notes

- **SQLite pragmas**: WAL journaling, `busy_timeout=5000` and `foreign_keys=ON`
  are set on every connection (`app/core/db.py`). SQLite ignores foreign-key
  constraints unless the pragma is on - turning it off silently is the classic
  SQLite data-integrity bug.
- **Why standalone?** `output: "standalone"` trims the build to just the files
  and node modules the server needs; `node .next/standalone/server.js` runs
  anywhere with no `npm install`, which is exactly what pm2 or a Docker image
  wants.
- API v1 starts from an intentionally empty slate: the previous `app/modules`
  domain (users/boards/cards) and its schema were removed; rebuild them as
  routers/models under `app/api/v1/`.

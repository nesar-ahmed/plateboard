# Plateboard

Two independent apps that each run as their own process:

- **Backend** — FastAPI + SQLAlchemy 2 (async) on **SQLite with WAL mode and
  foreign keys enabled**, schema managed by **Alembic**. Cookie auth with
  **roles (customer/cook)**, editable profiles, cook endpoints, and cook-owned
  dishes (fixed allergen enum, minor-unit prices, public active-dish menu).
  API v1 lives in `backend/app/api/v1/` and is a work in progress. See
  `backend/README.md`.
- **Frontend** — React (Next.js 16), built in **`standalone` mode**: a
  self-contained Node server (`frontend/.next/standalone/`) you run directly,
  under **pm2**, or behind an **nginx** reverse proxy on a VPS. Public dish
  list with search, dish and cook pages, login/register, and a cook dashboard
  for profile + dish management; the old status probe lives on at `/health`.
  See `frontend/README.md`.

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

## Development (two terminals + a seed run)

```bash
# terminal 1 - API on http://127.0.0.1:8000 (migrates on start)
cd backend
uv sync --all-groups
uv run python -m app.main

# terminal 2 - UI on http://localhost:3000, /api/* proxied to the backend
cd frontend
npm install
npm run dev

# once - demo data (9 zones / 10 cooks / 40 dishes / 5 customers, prints credentials)
cd backend
uv run python scripts/seed.py
```

Open <http://localhost:3000/> — the public dish list, served live from the
backend. The seed output lists `@example.com` logins; use one to reach the
dashboard (`/dashboard`) and, as a cook, add a dish and see it in the public
menu. The dev server rewrites `/api/:path*` to `API_ORIGIN` (from
`frontend/.env`, default `http://127.0.0.1:8000`), so the UI fetches relative
URLs and the code is identical in production. Health probe: `/health`.

## Tests / quality (backend)

```bash
cd backend
uv run pytest            # 224 tests: health, auth, roles/cooks, profiles, dishes, public menu + search + filters, zones, cart, seed, pragmas, migrations, API surface, docs
uv run ruff check app tests migrations scripts
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
(`0001_baseline.py` starts the v1 slate, `0002` adds auth, `0003` adds roles,
profile fields and the cooks table, `0004` adds the dishes table, `0005` adds
zones and places cooks in them, `0006` adds carts (guest or account) and
cart items).

Revisions are numbered sequentially and named `NNNN_<slug>.py`: a new
`alembic revision` (with or without `--autogenerate`) automatically gets the
next id after the highest existing one - `0007_add_widgets.py` with
`revision = "0007"` - via `process_revision_directives` in
`migrations/env.py` and `file_template` in `alembic.ini`. Pass `--rev-id` to
pick an id yourself. Autogenerate needs the database at head first.

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "add widgets"   # -> 0007_add_widgets.py
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
| `CART_COOKIE_NAME`   | `plateboard_cart`                       | HTTP-only guest-cart cookie name    |
| `CART_TTL_DAYS`      | `30`                                    | guest-cart cookie lifetime          |
| `DOCS_ASSETS_DIR`    | unset (CDN)                             | self-host `/docs` + `/redoc` JS/CSS when browsers cannot reach jsDelivr ([backend README](backend/README.md#api-docs-without-a-cdn)) |

Frontend-side variables (Next.js):

| Variable          | Default                  | When it matters                          |
| ----------------- | ------------------------ | ---------------------------------------- |
| `API_ORIGIN`      | `http://127.0.0.1:8000`  | dev proxy + standalone rewrite fallback (read at build/dev start) |
| `HOSTNAME`/`PORT` | `0.0.0.0`/`3000`         | runtime env of the standalone `server.js` (not read from `.env`) |

## API surface

| Method | Path               | Description                                              |
| ------ | ------------------ | -------------------------------------------------------- |
| GET    | `/api/health`      | Health probe: API + database status, SQLite pragmas      |
| POST   | `/api/auth/register` | Create account (email lowercased, salted scrypt hash); default role: customer |
| POST   | `/api/auth/login`  | Sets HTTP-only `plateboard_session` cookie (server-side session); moves a guest cart to the account |
| POST   | `/api/auth/logout` | Revokes the session server-side, clears the cookie       |
| GET    | `/api/me`          | Current user incl. profile fields, roles, `created_at`/`updated_at` (401 without an active session) |
| PATCH  | `/api/me/profile`  | Edit `display_name` (≤60), `bio` (≤500), `area` (≤120); omitted = keep, `null` = clear, blank = 422 |
| POST   | `/api/cooks`       | Become a cook: creates cook profile (headline ≤80, specialty tags, optional `zone` slug), adds `cook` role |
| GET    | `/api/cooks/me`    | My cook profile - **403 for non-cooks**                  |
| PATCH  | `/api/cooks/me`    | Update cook headline/specialties/`zone` (`null` clears the zone) - **403 for non-cooks** |
| GET    | `/api/cooks`       | Public cook directory (paginated), no auth               |
| GET    | `/api/cooks/{user_id}` | Public cook profile page (404 without a cook profile) |
| POST   | `/api/me/dishes`   | Add dish (cook only; price > 0 minor units; allergens from a fixed enum) |
| GET    | `/api/me/dishes`   | My dashboard list - own dishes incl. deactivated         |
| GET/PATCH/DELETE | `/api/me/dishes/{id}` | Manage own dish - another cook gets **404**    |
| GET    | `/api/dishes`      | Public menu - **active dishes only**, newest first; `?q=` text search (name, description, ingredients), `cook_id`, `zone` (+ `max_distance`), `min_price`/`max_price`, `dietary_tag` (repeat = all), `exclude_allergen` (repeat = any), `limit`/`offset` paging - see [Menu filters](#menu-filters) |
| GET    | `/api/dishes/{id}` | One active dish + cook name; deactivated -> **404**      |
| GET    | `/api/zones`       | Public zone list: `slug`, `name`, grid `x`/`y`, in grid order |
| GET    | `/api/cart`        | The cart - guest (cookie) or signed-in: `owner`, `cook`, items (newest first), `item_count`, `total` (minor units) - see [Cart](#cart) |
| POST   | `/api/cart/items`  | Add `{"dish_id", "quantity"?, "replace_cart"?}`; an existing line **grows**; another cook's dish -> 409 `different_cook` |
| PATCH  | `/api/cart/items/{dish_id}` | `{"quantity": n}` sets, `{"delta": +/-n}` increases/decreases (exactly one; result 1..100) |
| DELETE | `/api/cart/items/{dish_id}` | Remove a dish from the cart                     |
| DELETE | `/api/cart`        | Empty the cart                                           |
| GET    | `/api/v1`          | v1 marker (`{"version": "v1", ...}`)                     |
| GET    | `/`                | Backend service metadata (JSON) - the UI is served by the frontend process |
| GET    | `/docs`            | OpenAPI playground (disabled when `ENVIRONMENT=production`) |

Auth rules: passwords >= 8 chars hashed with stdlib `hashlib.scrypt` +
per-user random salt; emails unique/checked case-insensitively; failed logins
always return the same generic 401 (no account-existence leak); sessions are
stored as SHA-256 token hashes in the `sessions` table, so a DB leak cannot
replay logins. Roles are additive (`customer`, `cook`, or both) and enforced by
the `require_login` / `require_cook` dependencies - 401 always outranks 403 so
anonymous callers learn nothing about cook endpoints. Dishes are cook-owned
CRUD (`/api/me/dishes`): a foreign cook's dish id answers 404 (never reveals
existence), prices are positive integer minor units (also CHECK-enforced in
SQLite), allergens must come from the fixed `Allergen` enum, and deactivated
dishes are hidden from the public `/api/dishes` menu (and its detail route)
while owners still see them on the dashboard to reactivate. The public menu
supports `?q=` text search (below) plus `limit`/`offset` pagination returning
the match `total`, always newest first (insertion order). Seed `scripts/seed.py` with 9 zones, 10 cooks, 40 dishes and 5 customers is
idempotent: accounts are reused (passwords regenerated and printed), dishes
keyed on (cook, name) are never overwritten.

### Cart

**Everyone has a cart - guests too.** A signed-in user gets their account
cart; a guest gets one behind the HTTP-only `plateboard_cart` cookie, set by
the first add (random token; the database stores only its SHA-256, like
sessions). Reading never creates a cart. Carts are private: another owner's
line simply does not exist (404). Every cart endpoint answers **200 with the
whole cart** (`owner`, `cook`, `items`, `item_count`, `total`).

* **One cook per cart.** Adding another cook's dish is a 409
  `different_cook` (its `details` name the cart's cook) unless the request
  says `"replace_cart": true`, which empties the cart and starts it with that
  dish in one step.
* **Quantities 1..100** per dish - set with `{"quantity": n}`, changed with
  `{"delta": +/-n}`. Leaving the range is a 422 (`quantity_unavailable`),
  never a silent clamp; removing is `DELETE`. At most 50 distinct dishes.
* Only active dishes can be added (404 otherwise); a signed-in cook can never
  add **their own** dish (422 `own_dish`).
* **Checkout requires login, and login keeps the cart:** `POST
  /api/auth/login` moves this browser's guest cart to the account and clears
  the cookie. Own dishes are dropped; if the account already had a cart from
  the **same cook** the lines merge (quantities add up, max 100); if it was
  empty or from **another cook**, the guest cart - what the user just chose -
  replaces it.
* Changes to the dish show through: always the *current* price; a dish
  deactivated after being added stays listed with `"available": false`, is
  left out of `item_count`/`total` and can only be removed (PATCH -> 409
  `dish_unavailable`); a deleted dish leaves every cart.

### Menu filters

Zones are cells on an integer grid (`x` = column, `y` = row, one zone per
cell). A cook's kitchen sits in a zone (`POST /api/cooks` / `PATCH
/api/cooks/me` with `"zone": "<slug>"`), which places their dishes. The
distance between zones is the **Manhattan grid distance**
`|x1 - x2| + |y1 - y2|` (grid steps; `app/modules/zones/grid.py`).

`GET /api/dishes` filters - all optional, all combined with AND, evaluated in
SQL so `total` and paging stay exact; results stay newest first:

| Param | Meaning |
| ----- | ------- |
| `q=<text>` | text search: **every word** must appear (substring, any order) in the name, description or an ingredient; accent- and case-insensitive (`svickova` finds *Svíčková*), typed `%`/`_` literal; max 120 chars / 8 words |
| `zone=<slug>` | origin zone; alone = dishes from cooks **in** that zone. Items then carry `distance` |
| `max_distance=<n>` | with `zone`: cooks within `n` grid steps (0..1998); without `zone` -> 422 |
| `min_price` / `max_price` | inclusive, minor units; `min_price > max_price` -> 422 |
| `dietary_tag=<tag>` | repeatable; the dish must have **every** tag (exact tag, case-insensitive) |
| `exclude_allergen=<allergen>` | repeatable; drops dishes declaring **any** of them; unknown allergen -> 422 |

Dishes of cooks without a zone never match `zone`; an unknown zone slug is a
422 (`"type": "unknown_zone"`). Example:
`/api/dishes?zone=market-square&max_distance=1&dietary_tag=vegan&exclude_allergen=sesame&max_price=1000`.

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
      auth/                   # accounts, roles, profiles: scrypt hashing + sessions
      cooks/                  # become-a-cook, cook-only endpoints, public cook pages
      dishes/                 # cook-owned dish CRUD + public active-dish menu + filters
      zones/                  # grid zones, Manhattan grid_distance, GET /api/zones
      cart/                   # guest + account carts (/api/cart), login claim
      router.py               # mounts everything under /api
      deps.py                 # shared FastAPI dependencies (DB session)
      v1/                     # API version 1 - under development
    core/                     # settings, engine (WAL + FK pragmas), logging, errors, docs assets
    shared/                   # declarative Base, mixins, schema helpers
    main.py                   # app factory + single-process API entry point
  migrations/                 # Alembic (env.py reads DATABASE_URL from settings)
  scripts/seed.py             # idempotent demo data; prints fresh credentials
  tests/                      # per-test temp SQLite DB migrated by Alembic
  README.md
frontend/
  .env                        # local config (git-ignored, never pushed)
  .env.example                # documented template - committed
  src/app/                    # Next.js App Router: dish directory, cook pages,
                              # login/register, dashboard, /health probe
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
- API v1 starts from an intentionally empty slate: the pre-Plateboard scaffold
  domain (users/boards/cards) and its schema were removed; rebuild v1
  resources as routers/models under `app/api/v1/`. (Feature modules for the
  current, un-versioned API live in `app/modules/` - that folder is unrelated
  to the old scaffold.)

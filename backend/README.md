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
  `?q=` text search over name/description/ingredients, zone/distance, price
  range, dietary tag and allergen
  filters + `limit`/`offset` - see the root README's
  [Menu filters](../README.md#menu-filters)), `GET /api/dishes/{id}`
- Cart: `GET|DELETE /api/cart`, `POST /api/cart/items`,
  `PATCH|DELETE /api/cart/items/{dish_id}` - guests (HTTP-only cart cookie) and
  signed-in users; login moves a guest cart to the account (rules in the root
  README's [Cart](../README.md#cart) section)
- Zones: `GET /api/zones` - grid cells (slug, name, x/y) cooks are placed in;
  distance = Manhattan grid steps (`app/modules/zones/grid.py`)
- Seeding demo data: `uv run python scripts/seed.py` (safe to re-run; prints
  fresh login credentials)
- Docs: <http://127.0.0.1:8000/docs> (Swagger UI) and `/redoc` - blank page?
  See [API docs without a CDN](#api-docs-without-a-cdn)

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

## API docs without a CDN

`/docs` (Swagger UI) and `/redoc` are small HTML pages whose JavaScript/CSS
come from `cdn.jsdelivr.net`. If the **browser** cannot reach that CDN
(air-gapped VPS, locked-down network, sandbox) the page stays blank - the
browser console shows `SwaggerUIBundle is not defined` - even though the API
and `/api/v1/openapi.json` work. Serve the assets from the API instead:

```bash
DEST=/opt/plateboard/docs-assets          # any directory the API can read
mkdir -p "$DEST" && cd "$(mktemp -d)"
npm pack swagger-ui-dist@5 redoc@2        # the same majors FastAPI's CDN links use
tar xzf swagger-ui-dist-*.tgz -C "$DEST" --strip-components=1 \
  package/swagger-ui-bundle.js package/swagger-ui.css package/favicon-32x32.png
tar xzf redoc-*.tgz -C "$DEST" --strip-components=2 package/bundles/redoc.standalone.js
```

then set `DOCS_ASSETS_DIR=/opt/plateboard/docs-assets` in `backend/.env` and
restart. The pages become identical copies served from `/docs/assets/`
(`app/core/docs.py`, FastAPI's "self-hosting JavaScript and CSS for docs"
recipe); ReDoc also stops requesting Google Fonts. The API refuses to start if
the directory or one of `swagger-ui-bundle.js`, `swagger-ui.css`,
`redoc.standalone.js` is missing. Unset (the default) keeps FastAPI's CDN
pages, and `ENVIRONMENT=production` still disables all docs routes.

## Database

The development database is a single file at the backend root:
`backend/plateboard.db` (git-ignored, plus its `-wal`/`-shm` sidecars). Set via
`DATABASE_URL`; relative SQLite paths always resolve to this directory.

## Migrations (Alembic)

```bash
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "add widgets"   # -> 0007_add_widgets.py
uv run alembic downgrade -1
```

Migrations live in `migrations/versions/` (`0001_baseline.py` starts the v1
slate, `0002` adds auth, `0003` adds roles/profile fields + the cooks table,
`0004` adds the dishes table, `0005` adds zones + `cooks.zone_id`, `0006` adds
`carts` (guest token or account) + `cart_items`).
`migrations/env.py` reads the DSN from settings
(never from `alembic.ini`), and `uv run python -m app.main` runs
`upgrade head` on boot.

New revisions continue the numbered chain automatically: `alembic revision`
(plain or `--autogenerate`) assigns the next 4-digit id after the highest
existing one and names the file `NNNN_<slug>.py` (`process_revision_directives`
in `migrations/env.py` + `file_template`/`revision_environment` in
`alembic.ini`). `--rev-id` overrides the number. Autogenerate requires the
database to be at head; against a migrated database it currently finds no
differences (models and migrations agree - a test guards this).

## Seeding demo data

```bash
uv run python scripts/seed.py     # 9 zones, 10 cooks (40 dishes) + 5 customers
```

All accounts are invented and use `@example.com` emails. Passwords are
generated fresh at run time and printed - re-running reuses the existing
accounts but resets their passwords to what is printed, so **the printed
credentials always work**. Dishes are keyed on (cook, name): existing dishes
are left untouched, so dashboard edits and deactivations survive a re-run.
The script runs migrations first, so it works against a brand-new database.
The 3x3 demo zone grid is keyed on slug, and each seeded cook is placed in
a zone only while they have none - a zone picked via `PATCH /api/cooks/me`
survives a re-run.

## Tests

```bash
uv run pytest                       # 224 tests
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
  api/            # HTTP wiring only: router assembly, shared deps, versioning
    health.py     # GET /api/health (NOT versioned - stable probe URL)
    router.py     # mounts /api (health + auth + cooks + dishes + v1)
    deps.py       # shared DB-session dependency
    v1/           # API version 1, under development
  modules/        # domain features - each package owns router, schemas,
                  # models, service (e.g. auth: accounts + roles + profiles)
    auth/         # ...scrypt hashing and session dependencies
    cooks/        # become-a-cook, cook-only endpoints, public cook pages
    dishes/       # cook-owned menu CRUD + public active-dish menu + filters
    zones/        # grid zones, Manhattan grid_distance (+ SQL twin), GET /api/zones
    cart/         # guest + account carts: add/remove, set/adjust quantities, login claim
  core/           # settings, engine (WAL/FK pragmas), logging, error envelope,
                  # self-hosted docs assets (docs.py)
  shared/         # declarative Base + mixins, schema helpers
  models.py       # central ORM-model import for Alembic
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
| GET    | `/api/me`     | Current user: profile fields, roles, `created_at`/`updated_at` |
| PATCH  | `/api/me/profile` | Edit display_name/bio/area (length-validated); omitted keeps, `null` clears, blank is 422 |
| POST   | `/api/cooks`  | Become a cook: headline + specialty tags + optional `zone` slug (409 if already, 422 unknown zone) |
| GET    | `/api/cooks/me` | My cook profile - 403 without the cook role |
| PATCH  | `/api/cooks/me` | Update cook profile (`zone`: slug moves, `null` clears) - 403 without the cook role |
| GET    | `/api/cooks`  | Public cook directory (paginated), no auth |
| GET    | `/api/cooks/{user_id}` | Public cook profile page (404 without one) |
| POST   | `/api/me/dishes` | Add a dish (cook only; 422 unless price > 0 and allergens are known) |
| GET    | `/api/me/dishes` | My dashboard list - deactivated dishes included, newest first |
| GET    | `/api/me/dishes/{id}` | One of my dishes (another cook's id -> 404) |
| PATCH  | `/api/me/dishes/{id}` | Edit / deactivate (`{"active": false}`) / reactivate own dish |
| DELETE | `/api/me/dishes/{id}` | Remove own dish for good |
| GET    | `/api/dishes` | Public menu - active dishes only, newest first; `?q=` text search, `cook_id`, `zone` + `max_distance`, `min_price`/`max_price`, `dietary_tag`, `exclude_allergen`, `limit`/`offset` ([filters](../README.md#menu-filters)) |
| GET    | `/api/dishes/{id}` | One active dish (+ its cook's name); deactivated -> 404 |
| GET    | `/api/zones`  | Public zone list (slug, name, grid x/y)       |
| GET    | `/api/cart` | The cart (guest cookie or account): items, `cook`, `item_count`, `total` |
| POST   | `/api/cart/items` | Add a dish (`quantity` default 1; re-adding grows the line; one cook per cart, `replace_cart` to switch) |
| PATCH  | `/api/cart/items/{dish_id}` | Set `quantity` or adjust by `delta` (1..100) |
| DELETE | `/api/cart/items/{dish_id}` | Remove a dish |
| DELETE | `/api/cart` | Empty the cart |
| GET    | `/api/v1`     | v1 marker; feature routers get mounted here   |
| GET    | `/`           | Backend service metadata (JSON)               |

Config table and full VPS hosting (pm2 + nginx) are in the
[repo root README](../README.md).

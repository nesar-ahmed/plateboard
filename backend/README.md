# Plateboard backend

FastAPI + SQLAlchemy 2 (async) on **SQLite (WAL mode, foreign keys ON)**,
schema versioned with **Alembic**.

The backend is an **API-only** service with cookie-based auth, additive
**customer/cook/admin roles**, editable profiles, account settings (food
preferences, password change, sessions), **cook applications** decided by an
admin, cook-only endpoints,
cook-owned **dishes** (fixed allergen enum, minor-unit prices, public menu of
active dishes), carts, **favourite dishes**, **ratings and reviews**, **orders**, per-role
**dashboards** and in-app **notifications** (one inbox per panel), guarded by
the `require_login`/`require_customer`/`require_cook`/`require_admin`
dependencies. The
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
- Profiles & cooks: `PATCH /api/me/profile`, `POST /api/cooks` (apply to
  cook - `pending` until an admin accepts it), `GET /api/cooks/me/application`
  (where my application stands), `GET|PATCH /api/cooks/me` (cook role - granted
  on acceptance - required); public cook pages (accepted kitchens only):
  `GET /api/cooks` (directory), `GET /api/cooks/{user_id}` (profile + stats
  strip); each public card carries `verified` and live `availability`
- Kitchen availability: `GET|PUT /api/cooks/me/availability` (time zone,
  weekly hours, pause); orders are only placed while the kitchen takes them -
  see the root README's [Kitchen trust & availability](../README.md#kitchen-trust--availability)
- Dishes: `POST|GET /api/me/dishes`, `GET|PATCH|DELETE /api/me/dishes/{id}`
  (cook only, own dishes only; `active` = public/private, also on create);
  public menu: `GET /api/dishes` (active only,
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
- Account: `GET|PUT /api/me/preferences` (food profile), `POST /api/me/password`
  (signs out other sessions), `GET /api/me/sessions`,
  `POST /api/me/sessions/revoke-others`
- Addresses: `GET|POST /api/me/addresses`, `PATCH|DELETE /api/me/addresses/{id}`
  (login; max 10, exactly one default)
- Reviews: `GET|POST /api/me/reviews`, `GET /api/me/reviews/pending`,
  `GET|PATCH|DELETE /api/me/reviews/{id}` (customer role; only dishes from my
  orders that went the whole cycle - accepted, ready, received), cooks:
  `GET /api/cooks/me/reviews[/{id}]`, `PUT|DELETE /api/cooks/me/reviews/{id}/reply`;
  public: `GET /api/dishes/{id}/reviews`, `GET /api/cooks/{user_id}/reviews`;
  `rating` `{average, count}` on every public dish and cook - rules in the root
  README's [Reviews](../README.md#reviews) section
- Favourites: `GET /api/me/favourites`, `GET|PUT|DELETE /api/me/favourites/{dish_id}`,
  `POST /api/me/favourites/{dish_id}/cart` (customer role; max 50; hidden
  dishes stay listed as unavailable; rules in the root README's
  [Favourites](../README.md#favourites) section)
- Orders: `POST|GET /api/me/orders` (place my cart to one of my addresses / my
  orders; `fulfilment` pickup by default, delivery not offered yet),
  `GET /api/me/orders/{id}`, `POST /api/me/orders/{id}/cancel`,
  `POST /api/me/orders/{id}/receive` (I have the food: `ready` -> `completed`);
  cooks: `GET /api/cooks/me/orders[/{id}]` (`?sort=oldest` = request queue),
  `PATCH /api/cooks/me/orders/{id}` (status flow: accept, or reject with an
  optional `reason`, then ready) - rules in the root README's [Orders](../README.md#orders)
- Dashboards: `GET /api/me/dashboard` (customer), `GET /api/cooks/me/dashboard`
  + `GET /api/cooks/me/earnings` (cook), `GET /api/admin/dashboard` (admin) - see
  [Dashboards](../README.md#dashboards) and
  [Cook dashboard & earnings](../README.md#cook-dashboard--earnings); admin back office:
  `GET /api/admin/users`, `GET /api/admin/orders`, cook applications
  `GET /api/admin/cook-applications` + `POST .../{user_id}/accept|reject`
  (see the root README's [Cook applications](../README.md#cook-applications)),
  kitchen verification `POST|DELETE /api/admin/cooks/{user_id}/verification`
- Notifications: `GET /api/me/notifications` (`?audience=account|cook|admin`,
  `?unread=true`, paging), `GET /api/me/notifications/unread-count`,
  `POST /api/me/notifications/read-all`, `PATCH|DELETE /api/me/notifications/{id}`;
  written by feature services through `notifications.service.notify()` - see
  the root README's [Notifications](../README.md#notifications)
- Seeding demo data: `uv run python scripts/seed.py` (safe to re-run; one
  known password per role - see [Seeding demo data](#seeding-demo-data))
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
`carts` (guest token or account) + `cart_items`, `0007` adds `orders` +
`order_items` (snapshot lines), `0008` adds `addresses` + `orders.delivery_address`,
`0009` adds `users.excluded_allergens` + `users.dietary_preferences`, `0010`
adds `orders.cancel_reason`, `0011` adds `cooks.verified_at` / `verified_by_id`
/ `timezone` / `opening_hours` / `orders_paused`, `0012` adds `notifications`
(one row per recipient + event, partial index over unread rows), `0013` adds
the cook application to `cooks` - `status` (pending / accepted / rejected),
`submitted_at`, `reviewed_at` / `reviewed_by_id`, `rejection_reason`; existing
kitchens become accepted - `0014` adds `orders.fulfilment` (pickup /
delivery, CHECK-constrained, added in place: `orders` is a parent table) - and
`0015` adds `favourite_dishes` (PK user + dish, both CASCADE; a new table
nothing references, so its downgrade just drops it) - and `0016` adds
`reviews` (rating CHECK 1..5, unique customer + dish, reply + replied_at both
or neither; dish / order SET NULL, accounts CASCADE; also a new table, so the
downgrade drops it)).

**SQLite + parent tables:** dropping a column from a table other tables
reference (``users``, ``orders``, ...) must use native ``op.drop_column``
(SQLite >= 3.35), never ``batch_alter_table``: a batch "recreate" drops the
table, and with ``foreign_keys=ON`` that fires ``ON DELETE CASCADE`` on every
child row. ``tests/test_migrations.py`` guards the 0008-0011 downgrades.
The opposite case is fine: ``cooks`` is a *child* table (nothing references
it), so 0011 uses batch mode - which SQLite needs to drop its new FK column.
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
uv run python scripts/seed.py                      # 9 zones, 10 cooks (40 dishes), 5 customers, 1 admin
uv run python scripts/seed.py --random-passwords   # same, random passwords printed once
```

All accounts are invented and use `first.last@example.com` emails. Every
account gets **its role's demo password** (`DEMO_PASSWORDS` in the script):

| Role | Password | Frontend panel | Start with |
| ---- | -------- | -------------- | ---------- |
| admin | `plateboard-admin` | `/admin` | `morgan.ellis@example.com` |
| cook | `plateboard-cook` | `/cook` | `aiko.tanaka@example.com` (`SHOWCASE_COOK`) |
| customer | `plateboard-customer` | `/account` | `sam.porter@example.com` (`SHOWCASE_CUSTOMER`) |

Re-running reuses the existing accounts and resets their passwords to these,
so the documented logins always work (even after a password change in the
UI). **Production never gets known passwords:** with `ENVIRONMENT=production`
(or `--random-passwords`) each account gets a fresh random password instead,
printed once - `tests/test_seed.py` guards both. The output ends with the
login table and every account. Dishes are keyed on (cook, name): existing dishes
are left untouched, so dashboard edits and deactivations survive a re-run.
The script runs migrations first, so it works against a brand-new database.
The 3x3 demo zone grid is keyed on slug, and each seeded cook is placed in
a zone only while they have none - a zone picked via `PATCH /api/cooks/me`
survives a re-run.

Every seeded shopper gets a "Home" address in a grid zone (two customers also
a "Work" one) - only if they have none; demo orders carry a copy of it.

Each new kitchen's application was accepted by the admin a day after its
cook joined, and it gets its hours, pause switch and verification from
`KITCHENS` (presets in `HOURS_PRESETS`, zone `DEMO_TIMEZONE` = UTC): 8 of 10
are verified by the admin, Nadia and Kwame take orders any time (so a demo
order can always be placed), Olena is paused, the rest keep lunch / dinner /
daytime / evening hours. A kitchen "opened" when its cook joined (its
`created_at` is backdated), so "cooking since" is honest. Settings changed in
the UI survive a re-run.

The seed also creates the **admin** account (`morgan.ellis@example.com`, role
`admin` only) - the one way that role is granted; the API cannot. For the
dashboards, new accounts get deterministic "joined" dates in the past, and -
only while the seeded accounts have no orders yet - the seed adds a demo
history: 200 settled orders (mostly completed, ~15% cancelled - a cook who
turns one down gives a `cancel_reason`) over the last ~4 months, 4 completed
earlier today and 12 open ones (placed/accepted/ready) from the last 36 hours,
using the same snapshot rules as real orders and a fixed random seed, and an
open cart for three customers. Re-runs never add a second history; to rebuild
it, start from an empty database (delete `plateboard.db`, with the API
stopped).

**Cook applications + inboxes:** two customers have applied to cook
(`APPLICATIONS`) - Grace Okoro's application is **pending** (the admin's
review queue), Leo Fischer's was **rejected** with a reason - filed only for
customers without one. While the seeded accounts have no order notifications
yet, the seed also fills every inbox: each step of the last
`NOTIFICATION_DAYS` (7) days of orders, replayed through the live rules
(`app.modules.orders.notifications`, backdated), the kitchens' verification
notices and the applications' notices; only the last `UNREAD_HOURS` (24)
stay unread. Every row has a dedupe key, so nothing is ever written twice.

**Reviews:** while the seeded customers have no reviews, `REVIEW_SHARE`
(60%) of the dishes each of them received - from orders that went the whole
cycle, picked with the API's own rule (`reviews.service.full_cycle_conditions`)
- get a review (fixed `REVIEW_RANDOM_SEED`, mostly 4-5 stars, some without
words), written a few hours after receipt. Cooks replied to 40% of them -
75% for the showcase kitchen. The showcase customer's two most recently
received dishes stay unreviewed (`SHOWCASE_UNREVIEWED`), so
`GET /api/me/reviews/pending` has something to rate. The last
`NOTIFICATION_DAYS` of reviews are replayed through the live notification
rules (backdated; the cook's notice resolved where they replied) - once, while
no review notification exists.

**Favourites:** `DEMO_FAVOURITES` saves five dishes for the showcase
customer (Sam Porter) and three for Grace Okoro - only for customers without
any favourites. Sam's list mixes kitchens (his bag holds Nadia's dishes, so
adding Kwame's Jollof Rice asks for a new bag) and holds Aiko's private
"Oden no Mono" - saved while it was public, hidden since - so the list shows
an unavailable dish.

**Cook dashboard showcase:** `SHOWCASE_COOK` (Aiko Tanaka,
`aiko.tanaka@example.com`) gets about a third of the history, today's
completed orders, a queue of open requests (placed, accepted, ready) and a
cart waiting with her dishes - and already has one private dish - so every
block of `GET /api/cooks/me/dashboard` and `/api/cooks/me/earnings` has data.
The seed prints her email at the end.

## Tests

```bash
uv run pytest                       # 475 tests
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
    router.py     # mounts /api (health + auth + cooks + dishes + zones + cart +
                  # favourites + addresses + orders + reviews + dashboards + admin + v1)
    deps.py       # shared DB-session dependency
    v1/           # API version 1, under development
  modules/        # domain features - each package owns router, schemas,
                  # models, service (e.g. auth: accounts + roles + profiles)
    auth/         # ...scrypt hashing, session dependencies, food preferences,
                  # password change, session list / revoke
    cooks/        # cook applications, cook-only endpoints, public cook pages +
                  # stats, availability (pure availability.py: hours -> now)
    dishes/       # cook-owned menu CRUD + public active-dish menu + filters
    zones/        # grid zones, Manhattan grid_distance (+ SQL twin), GET /api/zones
    cart/         # guest + account carts: add/remove, set/adjust quantities, login claim
    reviews/      # ratings + reviews of received dishes (full order cycle), cook
                  # replies, ratings on dish/cook cards; notifications.py
    favourites/   # a customer's saved dishes: save/remove (max 50, atomic), hidden =
                  # unavailable, add a saved dish to the cart
    addresses/    # address book: one default per user (partial unique index)
    orders/       # place the cart (snapshot lines), customer/cook views, status flow,
                  # receipt; notifications.py: who hears about each step
    dashboards/   # customer / cook / admin dashboard aggregates + cook
                  # earnings (read-only)
    admin/        # back office: all users + all orders, cook applications,
                  # kitchen verification
    notifications/ # in-app inboxes per panel (account/cook/admin): type catalog
                  # (payload + text per audience), notify()/notify_admins(), inbox API
  core/           # settings, engine (WAL/FK pragmas), logging, error envelope,
                  # self-hosted docs assets (docs.py)
  shared/         # declarative Base + mixins, schema helpers
  models.py       # central ORM-model import for Alembic
  main.py         # create_app(), service-root route, API entry point
migrations/       # Alembic env.py + versions/
scripts/seed.py   # idempotent demo data: zones, cooks + dishes, customers, admin,
                  # addresses, demo orders + carts; prints credentials
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
| POST   | `/api/cooks`  | Apply to cook: headline + specialty tags + optional `zone` slug -> `pending` (409 `already_cook` / `application_pending`, 422 unknown zone) |
| GET    | `/api/cooks/me/application` | My cook application: pending / accepted / rejected (+ reason); 404 `no_application` |
| GET    | `/api/cooks/me` | My cook profile - 403 without the cook role |
| PATCH  | `/api/cooks/me` | Update cook profile (`zone`: slug moves, `null` clears) - 403 without the cook role |
| GET/PUT | `/api/cooks/me/availability` | Time zone + weekly hours + pause (PUT replaces all), with the computed availability - cook only |
| GET    | `/api/cooks`  | Public cook directory (paginated), no auth - `verified` + `availability` per card |
| GET    | `/api/cooks/{user_id}` | Public cook profile page + `stats` (404 without one) |
| POST   | `/api/me/dishes` | Add a dish (cook only; 422 unless price > 0 and allergens are known; `"active": false` = private draft) |
| GET    | `/api/me/dishes` | My dashboard list - public and private dishes, newest first |
| GET    | `/api/me/dishes/{id}` | One of my dishes (another cook's id -> 404) |
| PATCH  | `/api/me/dishes/{id}` | Edit / make private (`{"active": false}`) / publish (`{"active": true}`) own dish |
| DELETE | `/api/me/dishes/{id}` | Remove own dish for good |
| GET    | `/api/dishes` | Public menu - active dishes only, newest first; `?q=` text search, `cook_id`, `zone` + `max_distance`, `min_price`/`max_price`, `dietary_tag`, `exclude_allergen`, `limit`/`offset` ([filters](../README.md#menu-filters)) |
| GET    | `/api/dishes/{id}` | One active dish (+ its cook's name); deactivated -> 404 |
| GET    | `/api/zones`  | Public zone list (slug, name, grid x/y)       |
| GET    | `/api/cart` | The cart (guest cookie or account): items, `cook`, `item_count`, `total` |
| POST   | `/api/cart/items` | Add a dish (`quantity` default 1; re-adding grows the line; one cook per cart, `replace_cart` to switch) |
| PATCH  | `/api/cart/items/{dish_id}` | Set `quantity` or adjust by `delta` (1..100) |
| DELETE | `/api/cart/items/{dish_id}` | Remove a dish |
| DELETE | `/api/cart` | Empty the cart |
| GET    | `/api/me/favourites` | My favourite dishes, newest first (paging; `total`, `unavailable`, `max_favourites`) - customer role |
| GET    | `/api/me/favourites/{dish_id}` | One saved dish (404 if not on my list) |
| PUT    | `/api/me/favourites/{dish_id}` | Save an available dish (201 added / 200 already saved; 404 unknown or hidden, 422 `own_dish`, 409 `favourites_limit`) |
| DELETE | `/api/me/favourites/{dish_id}` | Remove it (204, idempotent) |
| GET    | `/api/me/reviews` | My reviews, newest first (`?dish_id=` one dish) - customer role |
| GET    | `/api/me/reviews/pending` | Dishes I received (full-cycle orders) and have not reviewed yet (`?dish_id=` one dish) |
| POST   | `/api/me/reviews` | Review a dish from one of my completed orders (422 `unknown_order` / `not_in_order`; 409 `order_not_completed` / `already_reviewed`) |
| GET/PATCH/DELETE | `/api/me/reviews/{id}` | One of my reviews / edit (`edited_at`) / delete |
| GET    | `/api/cooks/me/reviews` | Reviews of my dishes (`?rating=`, `?replied=`) + summary + `unreplied` - cook only |
| GET    | `/api/cooks/me/reviews/{id}` | One of them (another kitchen's -> 404) |
| PUT/DELETE | `/api/cooks/me/reviews/{id}/reply` | Write / rewrite / remove my reply |
| GET    | `/api/dishes/{id}/reviews` | A public dish's reviews + summary (hidden dish -> 404) |
| GET    | `/api/cooks/{user_id}/reviews` | A kitchen's reviews (all its dishes) + summary |
| POST   | `/api/me/favourites/{dish_id}/cart` | Add a saved dish to my cart (409 `dish_unavailable` while hidden; then the cart's rules) |
| GET/PUT | `/api/me/preferences` | Food profile (excluded allergens, diets) |
| POST   | `/api/me/password` | Change password (422 `wrong_password`); other sessions signed out |
| GET    | `/api/me/sessions` | Active sessions; `POST /api/me/sessions/revoke-others` ends the others |
| GET    | `/api/me/addresses` | My addresses, default first |
| POST   | `/api/me/addresses` | Add an address (409 `address_limit` past 10; 422 `unknown_zone`) |
| PATCH  | `/api/me/addresses/{id}` | Edit / make default |
| DELETE | `/api/me/addresses/{id}` | Remove (default passes to the newest) |
| POST   | `/api/me/orders` | Place my cart to `address_id`, `fulfilment` pickup by default (422 `unknown_address` / `fulfilment_unavailable`; 409 `cart_empty` / `cart_has_unavailable` / `cart_changed` / `kitchen_closed`) |
| GET    | `/api/me/orders` | My orders (`?status=` repeatable, paging), newest first |
| GET    | `/api/me/orders/{id}` | One of my orders (others -> 404) |
| POST   | `/api/me/orders/{id}/cancel` | Cancel while `placed` |
| POST   | `/api/me/orders/{id}/receive` | Confirm receipt: `ready` -> `completed` (the customer's step - never the cook's) |
| GET    | `/api/cooks/me/orders` | Orders placed with me (`?status=` repeatable, `?sort=newest\|oldest`) - 403 without the cook role |
| GET    | `/api/cooks/me/orders/{id}` | One of them (another cook's -> 404) |
| PATCH  | `/api/cooks/me/orders/{id}` | Move the status (accept / ready / cancel = reject, with an optional `reason`) |
| GET    | `/api/me/dashboard` | Customer dashboard (`?months=`) |
| GET    | `/api/cooks/me/dashboard` | Cook dashboard (`?days=`): money tiles, queue, performance, top customers, checklist, ... - cook only |
| GET    | `/api/cooks/me/earnings` | Cook earnings (`?start=`, `?end=`, `?group=day\|week\|month`) - cook only |
| GET    | `/api/admin/dashboard` | Admin dashboard (`?days=`) - admin only |
| GET    | `/api/admin/users` | All accounts with activity (`?role=`, `?q=`) - admin only |
| GET    | `/api/admin/orders` | All orders (`?status=` repeatable, `?cook_id=`, `?customer_id=`) - admin only |
| GET    | `/api/admin/cook-applications` | Cook applications (`?status=pending` default, oldest first; `accepted` / `rejected` / `all`) - admin only |
| POST   | `/api/admin/cook-applications/{user_id}/accept` | Accept: the applicant gains the `cook` role (409 `application_not_pending`) - admin only |
| POST   | `/api/admin/cook-applications/{user_id}/reject` | Reject with a required `{"reason"}` shown to the applicant (422 if blank; 409 `application_not_pending`) - admin only |
| POST/DELETE | `/api/admin/cooks/{user_id}/verification` | Verify / revoke an accepted kitchen (idempotent) - admin only |
| GET    | `/api/me/notifications` | My notifications, newest first (`?audience=`, `?unread=true`, paging) + `unread`; `cook`/`admin` inbox without the role -> 403 |
| GET    | `/api/me/notifications/unread-count` | Unread per panel (`total`, `account`, `cook`, `admin`) |
| POST   | `/api/me/notifications/read-all` | Mark all read (optional `audience`, `before`) |
| PATCH  | `/api/me/notifications/{id}` | `{"read": true\|false}` (others' -> 404) |
| DELETE | `/api/me/notifications/{id}` | Dismiss |
| GET    | `/api/v1`     | v1 marker; feature routers get mounted here   |
| GET    | `/`           | Backend service metadata (JSON)               |

Config table and full VPS hosting (pm2 + nginx) are in the
[repo root README](../README.md).

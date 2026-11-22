# Plateboard

Two independent apps that each run as their own process:

- **Backend** — FastAPI + SQLAlchemy 2 (async) on **SQLite with WAL mode and
  foreign keys enabled**, schema managed by **Alembic**. Cookie auth with
  **roles (customer/cook/admin)**, editable profiles, **cook applications**
  (an admin accepts or rejects them), cook endpoints, and cook-owned
  dishes (fixed allergen enum, minor-unit prices, public active-dish menu),
  carts, **favourite dishes** (max 50 per customer, straight to the cart), **ratings
  and reviews** (of dishes from completed orders, with the cook's reply), delivery **addresses**, **orders** (cart -> placed order -> cook's status flow ->
  the customer confirms receipt; pickup by default) and one
  read-only **dashboard API per role** (customer, cook, admin) plus admin
  back-office lists, and **in-app notifications** (one inbox per panel -
  account, cook, admin). API v1 lives in `backend/app/api/v1/` and is a work in progress. See
  `backend/README.md`.
- **Frontend** — React (Next.js 16), built in **`standalone` mode**: a
  self-contained Node server (`frontend/.next/standalone/`) you run directly,
  under **pm2**, or behind an **nginx** reverse proxy on a VPS. A "warm
  editorial" design system (self-hosted fonts, light + dark with a navbar
  switch): landing page,
  dish list with search + filters, dish and cook pages, split-screen
  login/register, cart drawer, checkout with saved/new delivery addresses,
  public cook pages with a verified badge, the next 24 hours of availability,
  a stats strip and "how ordering works", a **notification bell** in the header, a **user panel** at `/account/*` (overview with charts, orders + tracking
  and receipt confirmation, **favourites** (saved with a heart on any dish,
  straight to the bag), **ratings and reviews** on every dish page (summary,
  star filter, *Show more*, write / edit / delete your own),
  invoices, notifications, profile, addresses, payments, food preferences,
  login & security), and a **cook panel** at `/cook/*` (kitchen overview
  with the live order queue, money tiles and charts, orders with accept /
  reject, earnings, menu with public/private dishes, **reviews with inline
  replies** (a new review notifies the kitchen), kitchen profile, hours &
  pause), an **admin panel** at `/admin/*` (platform overview with a zone
  heat map, all users with kitchen verification, all orders, the cook-application
  review queue, the admin notification inbox); the old
  status probe lives on at
  `/health`. See `frontend/README.md`.

**Panel URLs:** every signed-in user has `/account/*` (the convention of
Shopify, Deliveroo, Airbnb, Etsy - private, singular, matches `/api/me`);
role panels get their own roots - `/cook/*` for cooks and `/admin/*` for
admins - rather than a REST-style `/users` (which reads as a public
directory). Logging in lands on the role's panel (admin -> `/admin`, cook ->
`/cook`, customer -> `/account`) unless a `?next=` page was asked for.

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

# once - demo data (9 zones / 10 cooks / 40 dishes / 5 customers / 1 admin, addresses,
# ~4 months of demo orders + 3 open carts for the dashboards; prints the logins below)
cd backend
uv run python scripts/seed.py
```

Open <http://localhost:3000/> — the landing page, served live from the
backend; the full menu is at `/dishes`. The dev server rewrites `/api/:path*` to `API_ORIGIN` (from
`frontend/.env`, default `http://127.0.0.1:8000`), so the UI fetches relative
URLs and the code is identical in production. Health probe: `/health`.

### Demo logins

The seed gives every account **its role's password** (the same on every run;
a re-run resets it). Log in at `/login` - without a `?next=` you land on your
role's panel:

| Role | Password | Panel | Start with | What you'll see |
| ---- | -------- | ----- | ---------- | --------------- |
| Admin | `plateboard-admin` | `/admin` | `morgan.ellis@example.com` | Platform overview, every user and order, a cook application to review |
| Cook | `plateboard-cook` | `/cook` | `aiko.tanaka@example.com` | The fullest demo kitchen: requests to accept/reject, earnings, menu |
| Customer | `plateboard-customer` | `/account` | `sam.porter@example.com` | ~30 orders, one still open, a bag waiting, 5 favourite dishes (one hidden by its cook) |

All seeded accounts (`first.last@example.com`):

* **Cooks** (`plateboard-cook`): aiko.tanaka, diego.fuentes, fatima.el-sayed,
  kwame.mensah, marco.greco, mei-ling.chen, nadia.rahman, olena.kovalenko,
  priya.sharma, tomas.novak
* **Customers** (`plateboard-customer`): grace.okoro, hana.kobayashi,
  leo.fischer, sam.porter, yusuf.demir - grace.okoro's cook application is
  **pending** (the admin's review queue), leo.fischer's was **rejected** with
  a reason
* **Admin** (`plateboard-admin`): morgan.ellis

Every panel's **notification inbox** is seeded too: the last week of orders,
step by step (unread for the last 24 hours), the kitchens' verification and
the two applications.

Cooks are customers too, so `/account` works for them as well; an admin's
`/account` holds their own login & security settings. These passwords exist
only for local demos: with `ENVIRONMENT=production` the seed never sets them
(each account gets a random password, printed once), and
`--random-passwords` does the same anywhere.

## Tests / quality (backend)

```bash
cd backend
uv run pytest            # 475 tests: health, auth, account (preferences, password, sessions), roles/cooks, cook applications, kitchen availability + verification + public stats, profiles, dishes, public menu + search + filters, zones, cart, favourites, reviews + ratings, addresses, orders, dashboards + cook earnings + admin lists, notifications + the events that send them, seed, pragmas, migrations, API surface, docs
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
cart items, `0007` adds orders and their snapshot lines, `0008` adds the
address book and the order's delivery-address copy, `0009` adds the users'
food preferences, `0010` adds the cook's optional `orders.cancel_reason`,
`0011` adds the kitchen's verification, time zone, weekly hours and pause
switch to `cooks`, `0012` adds the `notifications` table, `0013` turns
`cooks` into applications - `status` pending / accepted / rejected + the
review, existing kitchens accepted - `0014` adds `orders.fulfilment`,
pickup by default - `0015` adds `favourite_dishes`, a customer's saved
dishes - and `0016` adds `reviews`, the customers' ratings + words and the
cooks' replies). Downgrades that
drop a column from a *parent* table use
native `DROP COLUMN`, never a batch rebuild: with foreign keys on, rebuilding
a parent table would cascade-delete its children (a test guards this).

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
| `API_ORIGIN`      | `http://127.0.0.1:8000`  | dev proxy + standalone rewrite (read at build/dev start) **and** read at runtime by the Server Components that call the backend directly |
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
| GET/PUT | `/api/me/preferences` | Food profile: `excluded_allergens` (Allergen enum) + `dietary_preferences` (tags); PUT replaces both |
| POST   | `/api/me/password` | `{current_password, new_password}`; wrong current -> 422 `wrong_password`; signs out every *other* session |
| GET    | `/api/me/sessions` | Active sessions (`id` = short fingerprint, `current` flag) |
| POST   | `/api/me/sessions/revoke-others` | Sign out everywhere else |
| POST   | `/api/cooks`       | **Apply to cook**: creates the kitchen (headline ≤80, specialty tags, optional `zone` slug) as `pending` and notifies every admin; the `cook` role comes only with an admin's acceptance - see [Cook applications](#cook-applications). 409 `already_cook` / `application_pending` |
| GET    | `/api/cooks/me/application` | My application in any state: `status` pending / accepted / rejected (+ `rejection_reason`); 404 `no_application` |
| GET    | `/api/cooks/me`    | My cook profile - **403 for non-cooks** (applicants included) |
| PATCH  | `/api/cooks/me`    | Update cook headline/specialties/`zone` (`null` clears the zone) - **403 for non-cooks**; answers `verified_at` too |
| GET/PUT | `/api/cooks/me/availability` | When the kitchen takes orders: `timezone` (IANA), weekly `hours`, `orders_paused` (PUT replaces all three) + the computed `availability` - cook only; see [Kitchen trust & availability](#kitchen-trust--availability) |
| GET    | `/api/cooks`       | Public cook directory (paginated), no auth; each card has `verified` + live `availability` |
| GET    | `/api/cooks/{user_id}` | Public cook profile page + the `stats` strip (404 without a cook profile) |
| POST   | `/api/me/dishes`   | Add dish (cook only; price > 0 minor units; allergens from a fixed enum); `"active": false` saves it **private** (a draft) |
| GET    | `/api/me/dishes`   | My dashboard list - own dishes, public and private       |
| GET/PATCH/DELETE | `/api/me/dishes/{id}` | Manage own dish - another cook gets **404**    |
| GET    | `/api/dishes`      | Public menu - **active dishes only**, newest first; `?q=` text search (name, description, ingredients), `cook_id`, `zone` (+ `max_distance`), `min_price`/`max_price`, `dietary_tag` (repeat = all), `exclude_allergen` (repeat = any), `limit`/`offset` paging - see [Menu filters](#menu-filters) |
| GET    | `/api/dishes/{id}` | One active dish + cook name; deactivated -> **404**      |
| GET    | `/api/zones`       | Public zone list: `slug`, `name`, grid `x`/`y`, in grid order |
| GET    | `/api/cart`        | The cart - guest (cookie) or signed-in: `owner`, `cook`, items (newest first), `item_count`, `total` (minor units) - see [Cart](#cart) |
| POST   | `/api/cart/items`  | Add `{"dish_id", "quantity"?, "replace_cart"?}`; an existing line **grows**; another cook's dish -> 409 `different_cook` |
| PATCH  | `/api/cart/items/{dish_id}` | `{"quantity": n}` sets, `{"delta": +/-n}` increases/decreases (exactly one; result 1..100) |
| DELETE | `/api/cart/items/{dish_id}` | Remove a dish from the cart                     |
| DELETE | `/api/cart`        | Empty the cart                                           |
| GET    | `/api/me/favourites` | My favourite dishes, newest first (customer role; paging): each item is the public dish + `available` + `added_at`; page carries `total`, `unavailable`, `max_favourites` (50) - see [Favourites](#favourites) |
| GET    | `/api/me/favourites/{dish_id}` | One saved dish (404: not on my list) |
| PUT    | `/api/me/favourites/{dish_id}` | Save an available dish: **201** added, **200** already saved; unknown/hidden dish 404, own dish 422 `own_dish`, full list 409 `favourites_limit` |
| DELETE | `/api/me/favourites/{dish_id}` | Remove it (204, also when it was not on the list) |
| GET    | `/api/me/reviews` | My reviews, newest first (customer role; `?dish_id=`, paging) - see [Reviews](#reviews) |
| GET    | `/api/me/reviews/pending` | Dishes I received (orders through the whole cycle) and have not reviewed yet, each with the order to review it from (`?dish_id=`) |
| POST   | `/api/me/reviews` | Review a dish: `{"order_id", "dish_id", "rating" 1..5, "comment"?}` - only from my order that was accepted, made ready and received; 422 `unknown_order` / `not_in_order`, 409 `order_not_completed` (`details`: status + missing steps) / `already_reviewed` (`details.review_id`) |
| GET/PATCH/DELETE | `/api/me/reviews/{id}` | One of my reviews / change rating or words (`edited_at`) / remove it (204); others' -> 404 |
| GET    | `/api/cooks/me/reviews` | Reviews of my dishes (cook only; `?rating=`, `?replied=false` = to answer, paging) + `summary` + `unreplied` |
| GET    | `/api/cooks/me/reviews/{id}` | One of them (another kitchen's -> 404) |
| PUT/DELETE | `/api/cooks/me/reviews/{id}/reply` | Write or rewrite my public reply `{"reply"}` (≤1000) / take it down - both answer the review |
| GET    | `/api/dishes/{id}/reviews` | A public dish's reviews, newest first (`?rating=`, paging) + `summary` (average, count, per-star distribution); hidden dish -> 404 |
| GET    | `/api/cooks/{user_id}/reviews` | A kitchen's reviews across all its dishes (hidden and deleted ones too) + `summary`; no public kitchen -> 404 |
| POST   | `/api/me/favourites/{dish_id}/cart` | Add a saved dish to my cart (`{"quantity"?, "replace_cart"?}`, body optional) - answers with the whole cart; hidden dish 409 `dish_unavailable`, then the cart's rules (`different_cook`, ...) |
| GET    | `/api/me/addresses` | My delivery addresses, default first (login)            |
| POST   | `/api/me/addresses` | Add one (max 10; the first becomes the default; optional grid `zone`) |
| PATCH/DELETE | `/api/me/addresses/{id}` | Edit / `{"is_default": true}` / remove (the default passes to the newest); others' -> 404 |
| POST   | `/api/me/orders`   | Place an order from my cart (login; body `{"address_id", "note"?, "fulfilment"?}`): prices + address copied, cart emptied - `fulfilment` `pickup` (default; `delivery`: 422 `fulfilment_unavailable`, not offered yet); 422 `unknown_address`; 409 `cart_empty` / `cart_has_unavailable` / `cart_changed` / `kitchen_closed` - see [Orders](#orders) |
| GET    | `/api/me/orders`   | My orders, newest first (`?status=` repeatable = any of them, `limit`/`offset`) |
| GET    | `/api/me/orders/{id}` | One of my orders (someone else's -> 404)              |
| POST   | `/api/me/orders/{id}/cancel` | Cancel while still `placed` (else 409 `invalid_status_transition`) |
| POST   | `/api/me/orders/{id}/receive` | **Confirm I received it**: `ready` -> `completed` - the only way an order completes (else 409 `invalid_status_transition`) |
| GET    | `/api/cooks/me/orders` | Orders placed with me (cook only; `?status=` repeatable, `?sort=newest\|oldest`, paging) - `?status=placed&sort=oldest` is the request queue |
| GET    | `/api/cooks/me/orders/{id}` | One of them (another cook's -> 404)             |
| PATCH  | `/api/cooks/me/orders/{id}` | `{"status": ...}`: placed -> accepted \| cancelled, accepted -> ready \| cancelled (a ready order is completed by the customer); **accept** = `accepted`, **reject** = `{"status": "cancelled", "reason": "..."}` (reason optional, ≤200, only when cancelling) |
| GET    | `/api/me/dashboard` | Customer dashboard (any login; `?months=` 1..24, default 6) - see [Dashboards](#dashboards) |
| GET    | `/api/cooks/me/dashboard` | Cook dashboard (cook only; `?days=` 1..365, default 30) - see [Cook dashboard & earnings](#cook-dashboard--earnings) |
| GET    | `/api/cooks/me/earnings` | Cook earnings (cook only; `?start=`/`?end=` dates, default last 30 days, ≤366; `?group=day\|week\|month`) |
| GET    | `/api/admin/dashboard` | Admin dashboard (admin only; `?days=` 1..365, default 30) |
| GET    | `/api/admin/users` | All accounts + activity (admin; `?role=`, `?q=` email/name, paging) |
| GET    | `/api/admin/orders` | All orders (admin; `?status=` repeatable, `?cook_id=`, `?customer_id=`, paging) |
| GET    | `/api/admin/cook-applications` | The review queue (admin): `?status=pending` (default, oldest first) \| `accepted` \| `rejected` \| `all`, paging |
| POST   | `/api/admin/cook-applications/{user_id}/accept` | Accept (admin): the applicant gains the `cook` role; 409 `application_not_pending` |
| POST   | `/api/admin/cook-applications/{user_id}/reject` | Reject (admin) with a **required** `{"reason"}` (trimmed, non-blank, ≤300) shown to the applicant - 422 without one; 409 `application_not_pending` |
| POST/DELETE | `/api/admin/cooks/{user_id}/verification` | Verify a kitchen / revoke it (admin; idempotent; 404 without an accepted kitchen) - the public "verified" badge |
| GET    | `/api/me/notifications` | My notifications, newest first (`?audience=account\|cook\|admin`, `?unread=true`, paging) + the inbox's `unread` count - see [Notifications](#notifications) |
| GET    | `/api/me/notifications/unread-count` | Unread per panel: `{total, account, cook, admin}` (badges; cheap to poll) |
| POST   | `/api/me/notifications/read-all` | Mark all read - optional `{"audience", "before"}` |
| PATCH/DELETE | `/api/me/notifications/{id}` | `{"read": true\|false}` / dismiss; others' -> 404 |
| GET    | `/api/v1`          | v1 marker (`{"version": "v1", ...}`)                     |
| GET    | `/`                | Backend service metadata (JSON) - the UI is served by the frontend process |
| GET    | `/docs`            | OpenAPI playground (disabled when `ENVIRONMENT=production`) |

Auth rules: passwords >= 8 chars hashed with stdlib `hashlib.scrypt` +
per-user random salt; emails unique/checked case-insensitively; failed logins
always return the same generic 401 (no account-existence leak); sessions are
stored as SHA-256 token hashes in the `sessions` table, so a DB leak cannot
replay logins. Roles are additive (`customer`, `cook`, `admin`) and enforced by
the `require_login` / `require_customer` / `require_cook` / `require_admin` dependencies - 401 always
outranks 403 so anonymous callers learn nothing about protected endpoints. The
`admin` role is never granted through the API - only by `scripts/seed.py`. Dishes are cook-owned
CRUD (`/api/me/dishes`): a foreign cook's dish id answers 404 (never reveals
existence), prices are positive integer minor units (also CHECK-enforced in
SQLite), allergens must come from the fixed `Allergen` enum, and deactivated
dishes are hidden from the public `/api/dishes` menu (and its detail route)
while owners still see them on the dashboard to reactivate. The public menu
supports `?q=` text search (below) plus `limit`/`offset` pagination returning
the match `total`, always newest first (insertion order). `active` is the
dish's **public/private switch**: `true` = listed and orderable, `false` =
private (only its cook sees it - a draft, or a paused dish); new dishes are
public unless created with `"active": false`. Seed `scripts/seed.py` with 9 zones, 10 cooks, 40 dishes, 5 customers and 1 admin is
idempotent: accounts are reused (passwords reset to the role's demo password - see [Demo logins](#demo-logins)), dishes
keyed on (cook, name) are never overwritten, and the demo order history (200
settled orders over ~4 months, 4 completed today and 12 recent open ones,
fixed random seed; Aiko Tanaka's kitchen gets the biggest share) is only
created while the seeded accounts have no orders at all. New kitchens also get
hours, a pause switch and a verification from the seed's `KITCHENS` table (8
of 10 verified; two take orders any time, one is paused), and "opened" when
their cook joined.

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

### Favourites

**A customer's saved dishes** (`/api/me/favourites`, module
`app/modules/favourites/`) - a heart on a dish, and a list to order from.

* **Customers only** (`require_customer`): 401 for guests, 403 for an account
  without the `customer` role (the seed's admin-only account). Cooks are
  customers too, so they keep favourites of *other* kitchens' dishes.
* **Only available dishes can be saved**: an unknown or hidden (private)
  dish is a 404 - the public menu's answer. **Not your own dish**: a cook
  saving one of their own dishes is a 422 `own_dish`.
* **At most 50** (`MAX_FAVOURITES`) - the 51st is a 409 `favourites_limit`
  (`details.max_favourites`). Hidden dishes still take up room. The limit
  check and the insert are one SQL statement (`INSERT ... SELECT ... WHERE
  count < 50`), so two saves racing for the last slot cannot both win (a
  test forces that race).
* **Idempotent**: `PUT` answers 201 when it added the dish, 200 when it was
  already saved; `DELETE` is 204 either way - a double tap never errors.
* **Hidden dishes stay listed** as `available: false` (the cart's rule for
  deactivated dishes) and count in `unavailable`; they cannot go to the cart
  (409 `dish_unavailable`) until the cook publishes them again. A *deleted*
  dish leaves every list. Favourites link to the dish (not a snapshot), so
  price and name edits show through.
* **Straight to the cart**: `POST /api/me/favourites/{dish_id}/cart` adds a
  saved, available dish to the account cart through the cart service - same
  rules and the same whole-cart answer as `POST /api/cart/items` (lines
  grow, one cook per cart with `replace_cart`, 1..100 portions).

### Reviews

**Customers rate (1..5 stars) and review dishes they received; cooks reply.**
Module `app/modules/reviews/`, migration `0016`.

* **Only after the whole order cycle.** A dish can be reviewed from one of
  the customer's *own* orders that went every step: placed -> **accepted**
  by the cook -> marked **ready** by the cook -> **completed** by the
  customer confirming receipt. The service checks the status *and* all three
  stamps (`accepted_at`, `ready_at`, `completed_at`); open, rejected and
  cancelled orders never qualify. Checked in order: someone else's or an
  unknown order -> 422 `unknown_order`; a dish not on it -> 422
  `not_in_order`; not through the cycle -> 409 `order_not_completed`
  (`details.status` + `details.missing` steps). `GET /api/me/reviews/pending`
  lists exactly the dishes that qualify and are not reviewed yet.
* **One review per customer per dish** - a unique (customer, dish) pair in
  the database: reviewing it again (from any order, or in a parallel
  request) is a 409 `already_reviewed` naming the review to edit. The author
  edits it (`edited_at` stamped on a real change) or deletes it (then the dish
  can be reviewed again). Ratings are whole stars; `comment` is optional
  (≤1000, trimmed, blank = none).
* **Customers only write, cooks only reply** (`require_customer` /
  `require_cook`). One reply per review (≤1000), rewritable and removable;
  only the dish's cook can answer - another kitchen's review is a 404.
* **Public view** - the author as "First L." (`Sam P.`), never the
  customer's id or order. A dish's review page follows the dish (hidden ->
  404); a kitchen's page keeps the reviews of dishes it hid or deleted (a
  deleted dish's review keeps its `dish_name`, `dish_id` becomes null), so
  hiding a dish never resets a kitchen's record.
* **Ratings on cards** - every public dish (`/api/dishes`, `/api/dishes/{id}`,
  favourites) and kitchen (`/api/cooks`, `/api/cooks/{id}`) carries `rating`
  `{average, count}` (average: 2 decimals, null without reviews), batched in
  one query per page; review lists add `summary.distribution` (5 -> 1 stars).
* **Notifications** - a new review notifies the cook so they can reply
  (`review.posted`: the stars, the dish and the customer's words, shortened
  to 140 characters; resolved once they reply or the review is deleted); the
  cook's *first* reply notifies the reviewer (`review.replied`). Edits notify
  nobody.

### Orders

**Placing an order turns the signed-in user's cart into an order** (`POST
/api/me/orders`; guests log in first - their cart moves to the account),
for one of the caller's own addresses (`address_id` from
`/api/me/addresses`; anything else is a 422 `unknown_address`).

* **Fulfilment:** `pickup` - the customer collects the food - is the default
  and the only mode offered today; `delivery` is part of the contract
  (`orders.fulfilment`) but refused for now (422 `fulfilment_unavailable`,
  `ENABLED_FULFILMENTS` in `orders/models.py`). The address is the
  customer's contact for the cook, and the delivery address once delivery
  exists.

* The cart must hold at least one dish and **no unavailable lines** (409
  `cart_empty` / `cart_has_unavailable`, whose `details` name the dishes).
* **Snapshot lines:** each dish's name and *current* price are copied into the
  order, `total`/`item_count` are stored, and the cart is emptied - one
  transaction. Later dish edits never change an order; deleting the dish keeps
  the line (its `dish_id` becomes `null`). The chosen address is copied into
  `delivery_address` the same way - editing or deleting it later changes
  nothing on the order.
* If the cart changed while the order was being placed (double submit, an add
  in another tab), nothing is placed: 409 `cart_changed`.
* The kitchen must be **taking orders right now** (its weekly hours, not
  paused - see [Kitchen trust & availability](#kitchen-trust--availability)),
  else 409 `kitchen_closed` with `details.status` and `details.opens_at`;
  nothing changes. Filling the cart is always allowed.
* **Status flow** - the cook (`PATCH /api/cooks/me/orders/{id}`): `placed` ->
  `accepted` | `cancelled`, `accepted` -> `ready` | `cancelled`. Accepting a
  request is `accepted`; **rejecting** it is `cancelled` while still
  `placed` (`accepted_at` stays null), optionally with a `reason` the
  customer sees as `cancel_reason` (trimmed, ≤200 chars, only allowed with
  `cancelled`; customers cancel without one). The customer cancels only
  while `placed` (`POST .../cancel`) and **confirms receipt** of a `ready`
  order (`POST /api/me/orders/{id}/receive`) - `ready` -> `completed` is
  theirs alone: an order counts as completed (and earned) once the customer
  says they have the food. Every step stamps
  `accepted_at` / `ready_at` / `completed_at` / `cancelled_at` (+
  `cancelled_by`); anything else is 409 `invalid_status_transition` with the
  allowed targets in `details`. Moves are compare-and-set, so two racing
  changes cannot both win.
* Customers see their own orders, cooks the ones placed with them, admins all
  of them; any other order id is a 404.
* Placing and every move **notify the other side** in the same transaction
  (see [Notifications](#notifications)).

### Dashboards

One read-only document per audience, built with SQL aggregates:

| Endpoint | Audience | Contents |
| -------- | -------- | -------- |
| `GET /api/me/dashboard?months=6` | any signed-in user | order stats, monthly spending series, favourite cooks + dishes, latest 5 orders, cart snapshot |
| `GET /api/cooks/me/dashboard?days=30` | cook | money tiles (today / 7 days / month / lifetime + open pipeline), open-order queue (oldest first), order stats, daily revenue series, best-selling dishes, top customers, unique/repeat customers, request handling (acceptance rate, rejections, accept/prep minutes), average fulfilment minutes, cart demand, menu breakdown (public/private, prices, allergens, tags), kitchen zone, set-up checklist, latest 5 orders |
| `GET /api/cooks/me/earnings` | cook | earnings over a date range vs the range before, day/week/month series, per-dish earnings, lifetime + open pipeline |
| `GET /api/admin/dashboard?days=30` | admin | users by role + active sessions, daily signups, platform order stats + daily series, top cooks + dishes, per-zone activity (grid heat map), menu breakdown, open carts (guest vs account) |

Shared definitions: money is minor units; **value** = totals of orders that
were not cancelled (`booked_value`; `completed_value` is the completed part);
`open` = placed + accepted + ready. Summaries and rankings (top 5) are
all-time; series cover the window, one point per UTC day/month, oldest first,
with empty periods as zeros, bucketed by when the order was placed.

### Cook dashboard & earnings

The cook side is built from endpoints a kitchen needs every day:

| Need | Endpoint |
| ---- | -------- |
| Profile | `PATCH /api/me/profile` (name, bio, area) + `PATCH /api/cooks/me` (headline, specialties, kitchen zone) |
| Menu CRUD + public/private | `POST/GET /api/me/dishes`, `GET/PATCH/DELETE /api/me/dishes/{id}` - `active` is the switch |
| Answer order requests | `GET /api/cooks/me/orders?status=placed&sort=oldest`, then `PATCH /api/cooks/me/orders/{id}` with `accepted` or `{"status": "cancelled", "reason": ...}` |
| Run the kitchen | `accepted` -> `ready` on the same PATCH; the customer's receipt (`POST /api/me/orders/{id}/receive`) completes it |
| Home page | `GET /api/cooks/me/dashboard` |
| Money | `GET /api/cooks/me/earnings` |

**Earned** means *completed* - the customer confirmed they received the
food: payment happens at handover (no online payments yet), so an order
counts on the UTC day it was **completed** - not placed -
for `earnings` tiles and the earnings endpoint (the older `revenue` series and
`orders` block keep the shared "booked, by placement" definitions). Open orders
are not earned yet: `awaiting_acceptance` (placed - requests to answer) and
`in_progress` (accepted + ready). A **rejection** is a `placed` order the cook
cancelled (never accepted); `acceptance_rate` = accepted / (accepted +
rejected). Dashboard additions:

* `earnings` - `today`, `last_7_days`, `this_month`, `lifetime` (each
  `{orders, value}`) + `awaiting_acceptance`, `in_progress`;
* `queue` - open orders oldest first (max 20), for inline accept / reject /
  ready / complete;
* `performance` - accepted, rejected, `acceptance_rate`,
  `cancelled_after_accepting`, `cancelled_by_customer`, `cancellation_rate`,
  `average_accept_minutes` (placed -> accepted), `average_prep_minutes`
  (accepted -> ready); rates are 0..1, null before there is anything to rate;
* `top_customers` - the 5 best customers (orders, value, last order);
* `checklist` - set-up steps `display_name`, `bio`, `specialties`, `zone`,
  `public_dish`, `dish_descriptions` (every public dish described), with
  `done`/`total` (UI copy lives in the frontend).

`GET /api/cooks/me/earnings?start=&end=&group=`: inclusive UTC dates (`end`
defaults to today, `start` to 30 days ending at `end`, so `?start=` alone
means "since"; at most 366 days; bad ranges are 422s on `end`). Answers
`range`, `summary` (`earned`, `orders`, `portions`, `average_order_value`,
`cancelled_orders`/`cancelled_value` by cancellation day, `rejected_orders`),
`previous` (the same number of days right before - for trend arrows),
`series` (zero-filled per day, ISO week labelled by its Monday, or month),
`dishes` (every dish sold in the range, by value), `lifetime`,
`awaiting_acceptance` and `in_progress`.

Seeded data: log in as **`aiko.tanaka@example.com`** (`plateboard-cook`) -
the showcase kitchen with ~4 months of history, orders completed today,
requests waiting, a rejection with its reason, regular customers and a
private dish.

### Cook applications

**Becoming a cook is an application an admin decides.** `POST /api/cooks`
creates the kitchen (headline, specialties, zone) with `status: pending` and
notifies every admin. Until an admin accepts it the applicant is just a
customer: no `cook` role, 403 on every cook endpoint, no dishes, and the
kitchen is in neither the directory nor a public page. The applicant follows
it at `GET /api/cooks/me/application`.

* **Review** (admin): `GET /api/admin/cook-applications` is the queue -
  pending, oldest first (`?status=accepted|rejected|all` for the rest). `POST
  .../{user_id}/accept` adds the `cook` role (roles only grow - the cook
  stays a customer); `POST .../{user_id}/reject` **requires** a `reason`
  (trimmed, never blank, ≤300 - 422 otherwise) shown to the applicant, so
  they know what to change before applying again. Both stamp `reviewed_at` + `reviewed_by`
  and are compare-and-set: only a `pending` application can be decided (409
  `application_not_pending` - e.g. another admin was faster).
* **Applying again:** a rejected applicant may apply again - the application
  goes back to `pending` with the new details and the old decision cleared.
  An open application is 409 `application_pending`, a kitchen 409
  `already_cook`.
* **Notifications:** the admins hear about every (re)submission; the
  applicant hears the decision (with the reason) in `/account`; once decided,
  every admin's "new application" notice is marked read.
* Kitchens that existed before applications (migration `0013`) were accepted
  automatically. The admin's user list shows `cook_application` per account,
  and the admin dashboard counts `pending_cook_applications`. Verification -
  the badge below - is for accepted kitchens only.

### Kitchen trust & availability

What the public cook page (`/cooks/{id}`) shows beyond the profile:

* **Verified badge** - `cooks.verified_at` / `verified_by_id`, set by an
  admin (`POST|DELETE /api/admin/cooks/{id}/verification`, idempotent -
  verifying again keeps the first date; deleting the admin keeps the badge).
  Public cards carry `verified` + `verified_at`; the cook sees `verified_at`
  on `/api/cooks/me`, the back office on `/api/admin/users`.
* **Availability** - the cook sets an IANA `timezone`, weekly `hours`
  (`{"day": 0-6, "opens": "HH:MM", "closes": "HH:MM"|"24:00"}`, Monday = 0,
  kitchen wall time; at most 3 non-overlapping windows a day) and
  `orders_paused` (`GET|PUT /api/cooks/me/availability`). Every public card
  then carries `availability`: `status` (`open` / `closed` / `paused` /
  `anytime` - no fixed hours, every kitchen's state until it sets hours),
  `accepting_orders`, `closes_at` (open) / `opens_at` (closed, within a
  week), `next_24h` (the taking-orders windows from `as_of` to `as_of + 24
  h`, clipped), `timezone` and `as_of`. Back-to-back windows merge across
  midnight; hours follow the kitchen's wall clock through daylight-saving
  changes (`app/modules/cooks/availability.py`, pure and clock-injected).
  Instants are UTC - the UI shows them in the viewer's time. **Placing an
  order needs `accepting_orders`** (409 `kitchen_closed` otherwise).
* **Stats strip** - `GET /api/cooks/{id}` adds `stats`: `orders_completed`,
  `customers` / `returning_customers`, `acceptance_rate`,
  `average_ready_minutes` (placed -> ready) and `new_kitchen`. Counts only,
  never money; the rate and the time stay null until the kitchen answered 5
  requests (`PUBLIC_STATS_MIN_ORDERS`), and they reuse the cook dashboard's
  definitions. The directory list stays light (no stats).
* **How ordering works** - frontend copy on the profile page, filled in
  with the kitchen's own numbers and hours.

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

### Notifications

**One inbox per panel.** Every notification belongs to one recipient *and*
one `audience` - the panel it shows in: `account` (`/account`, every
signed-in user - admins included), `cook` (`/cook`) or `admin` (`/admin`).
An account that is customer and cook at once gets an order confirmation in
`/account` and new requests in `/cook`, separately. `cook` and `admin`
inboxes need the role: asking for one without it is a 403, and rows in an
inbox the caller can no longer see stay hidden (404 by id) but are kept.

* **What happened** - `type` from the catalog
  (`backend/app/modules/notifications/catalog.py`): `account.welcome`,
  `account.password_changed`, `cook_application.submitted` (admins) /
  `.accepted` / `.rejected` (the applicant), `kitchen.verified` /
  `.verification_revoked`, and the order lifecycle `order.placed`
  (customer: confirmation, cook: new request), `.accepted`, `.rejected`,
  `.cancelled_by_customer`, `.cancelled_by_cook` (customer + admins),
  `.ready` (for pickup - the default - or out for delivery), `.received`
  (the customer confirmed it), and reviews: `review.posted` (the cook) /
  `review.replied` (the reviewer). Each type has a payload model, a subject
  kind and the text per audience.
* **Snapshot, rendered on read** - a row stores a JSON `data` snapshot
  (names, totals, the cook's reason) validated against the type's payload;
  `title`/`body` are rendered from it when listed, so wording can change
  without a migration and later edits never rewrite old notifications.
  `subject` (`{"kind": "order"|"kitchen"|"review", "id"}`) is what the client links
  to - no foreign key, it may no longer exist. Retired types fall back to a
  generic title instead of breaking the inbox.
* **Written inside the change** - feature services call
  `notifications.service.notify()` / `notify_admins()` just before their own
  commit; neither commits, so a notification exists exactly when the change
  it reports was committed (a rolled-back order takes its notification
  with it). A `dedupe_key` makes an event idempotent per recipient (`INSERT
  ... ON CONFLICT DO NOTHING`); admin fan-out skips the acting admin.
* **Read state is server-side** - `PATCH {"read": true|false}` (the first
  read time is kept), `read-all` for one panel or all, up to `before` (the
  newest one on screen, so later arrivals stay unread), `DELETE` to dismiss.
  `unread-count` answers every badge in one call from a partial index over
  unread rows.

**What is sent** (each written by the feature's service, inside its own
transaction - a refused or rolled-back action notifies nobody):

| Event | Who hears (inbox) |
| ----- | ----------------- |
| Registration | the new account - welcome (`account`) |
| Password changed | the account - security notice with the sessions signed out (`account`) |
| Cook application submitted / resubmitted | every admin (`admin`) |
| Application accepted / rejected (+ the required reason) | the applicant (`account`); every admin's notice is resolved |
| Kitchen verified / badge revoked | the cook (`cook`) - only on a real change |
| Order placed | the customer - confirmation (`account`) + the cook - new request (`cook`) |
| Accepted, rejected (+ reason), ready (for pickup) | the customer (`account`) |
| Cancelled by the customer | the cook (`cook`) |
| Cancelled by the cook after accepting (+ reason) | the customer (`account`) + every admin (`admin`) |
| Received - the customer confirmed it | the cook (`cook`) |
| A dish reviewed | its cook (`cook`) - resolved once they reply (or the review is deleted) |
| The cook's first reply to a review | the reviewer (`account`) |

Actionable notices are **resolved** when acted on: the cook's "new order
request" is marked read once the request is answered or withdrawn, the
customer's "ready" once they confirm receipt. Order events are keyed
`order:{id}:{type}` (`app/modules/orders/notifications.py` - the one place
that decides who hears what; the seed replays demo history through it).

**In the frontend:** the header bell (every page, signed in) shows the
unread count of every inbox the user can read and the newest notifications
- a tab per inbox when there is more than one (a cook: *Kitchen* +
*Account*, an admin: *Admin* + *Account*), opening on the panel the user is
in - and each panel has its full inbox: `/account/notifications`,
`/cook/notifications`, `/admin/notifications` (one shared component), with
the unread count on the panel's *Notifications* item. Counts poll every 30 s
while the tab is visible and refresh when it comes back into view. Admins
review applications at `/admin/applications`; applicants follow theirs at
`/cook` (pending, the admin's reason, *Apply again*); customers confirm
receipt with *I've received my order* (see `frontend/README.md`).

**Where the code lives:**

| Piece | Backend | Frontend |
| ----- | ------- | -------- |
| Model, catalog, writing + the inbox API | `app/modules/notifications/` (`models`, `catalog`, `service`, `router`), migration `0012` | `src/lib/api.ts` (`AppNotification`, `NotificationPage`, `UnreadCounts`) |
| Who hears what | `auth/service.py`, `cooks/service.py`, `admin/service.py`, `orders/notifications.py` | `src/lib/notification-kinds.ts` (icon, tone, link per type; `INBOXES`) |
| Counts + badges | `GET /api/me/notifications/unread-count` (partial index) | `src/lib/notifications.tsx`, `CountPill` in `src/components/ui.tsx` |
| Bell + inboxes | - | `src/components/notification-bell.tsx`, `notification-inbox.tsx`, `notification-bits.tsx` |
| Cook applications | `cooks/service.py` (apply), `admin/service.py` (decide), migration `0013` | `src/components/kitchen-onboarding.tsx`, `src/app/admin/applications/` |
| Pickup + receipt | `orders/models.py` (`Fulfilment`, `CUSTOMER_TRANSITIONS`), migration `0014` | `src/components/receive-button.tsx`, `cook-order-actions.tsx` |
| Tests | `tests/test_notifications.py`, `test_notification_events.py`, `test_cook_applications.py` | - |

**Not built yet** (later phases of the notification plan - none of these
types exist in the catalog):

* **Bag notices** - a dish in the bag deactivated or repriced, the bag's
  kitchen paused / open again, a login replacing the account's bag with a
  guest bag.
* **More security notices** - a new sign-in, other sessions signed out
  (`revoke-others`; a password change already says how many it ended).
* **Kitchen signals** - a customer trying to order while the kitchen is
  closed, milestones (first order, first regular), and for admins an audit
  line when another admin verifies or revokes a kitchen.
* **Scheduled ones** - reminders for requests waiting too long, an
  automatic completion for ready orders the customer never confirms,
  digests, and pruning old read notifications: there is no scheduler yet.
* **Channels + preferences** - email / SMS (shown as *coming soon*), muting
  types, and pushing instead of polling (server-sent events).

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
    api/                      # HTTP wiring only: assembly, shared deps, versions
      health.py               # GET /api/health (intentionally NOT versioned)
      router.py               # mounts everything under /api
      deps.py                 # shared FastAPI dependencies (DB session)
      v1/                     # API version 1 - under development
    modules/                  # domain features - each owns router/schemas/models/service
      auth/                   # accounts, roles, profiles: scrypt hashing + sessions
      cooks/                  # cook applications, cook-only endpoints, public cook pages,
                              # stats strip, weekly hours + availability
      dishes/                 # cook-owned dish CRUD + public active-dish menu + filters
      zones/                  # grid zones, Manhattan grid_distance, GET /api/zones
      cart/                   # guest + account carts (/api/cart), login claim
      favourites/             # a customer's saved dishes (/api/me/favourites), max 50, -> cart
      reviews/                # ratings + reviews of received dishes, cook replies, ratings on cards
      addresses/              # address book (/api/me/addresses), one default per user
      orders/                 # place the cart, customer + cook order views, status flow,
                              # receipt, who-hears-what (notifications.py)
      dashboards/             # customer / cook / admin dashboard aggregates + cook earnings
      admin/                  # back office (users, orders, cook applications, verification) - admin only
      notifications/          # in-app inboxes (account / cook / admin), type catalog, notify()
    core/                     # settings, engine (WAL + FK pragmas), logging, errors, docs assets
    shared/                   # declarative Base, mixins, schema helpers
    models.py                 # central ORM-model import for Alembic
    main.py                   # app factory + single-process API entry point
  migrations/                 # Alembic (env.py reads DATABASE_URL from settings)
  scripts/seed.py             # idempotent demo data; demo logins per role
  tests/                      # per-test temp SQLite DB migrated by Alembic
  README.md
frontend/
  .env                        # local config (git-ignored, never pushed)
  .env.example                # documented template - committed
  src/app/                    # Next.js App Router: landing, /dishes (+ dish pages),
                              # /cooks, login/register, checkout, /account/* user
                              # panel, /cook/* cook panel, /admin/* admin
                              # panel, /health probe
  src/components/             # ui.tsx primitives, charts, nav, cart drawer, panels,
                              # notification bell + inbox
  src/lib/                    # API client + types, session, cart, notifications,
                              # panel contexts, hooks, formatting
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

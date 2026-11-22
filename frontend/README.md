# Plateboard frontend

React app built with Next.js 16 in **`output: "standalone"`** mode - the
configuration for self-hosting: `npm run build` produces a minimal,
dependency-trimmed Node server that you run as its own process (pm2, systemd,
Docker), typically behind an nginx reverse proxy on a VPS.

## Development (hot reload)

```bash
cp .env.example .env   # set API_ORIGIN (the backend URL) if it differs
npm install
npm run dev            # http://localhost:3000
```

Next.js loads `frontend/.env` automatically (only `NEXT_PUBLIC_*` vars reach
the browser; `API_ORIGIN` is server-side only, used by `next.config.ts` for
the `/api` rewrite and at runtime by the Server Components that call the
backend directly - landing, dish list, dish and cook pages).
`next dev` rewrites `/api/:path*` to the backend (`API_ORIGIN`, default
`http://127.0.0.1:8000`), so start the backend too
(`cd ../backend && uv run python -m app.main`). Browser code always fetches
relative `/api/*` URLs - the same shape in every environment. `.env` is
git-ignored; `.env.example` is the committed template.

## Pages

| Route            | What it does                                                        |
| ---------------- | ------------------------------------------------------------------- |
| `/`              | **Landing page** (Server Component): hero with search + neighbourhood picker (a plain GET form to `/dishes`, works before JS), popular diet chips, live stats, featured dishes, "how it works", cooks, allergen transparency, cook CTA. Old `/?zone=...` list links redirect to `/dishes` |
| `/dishes`        | Public dish list (active only, newest first): search bar + filters (neighbourhood/distance, price range, diet chips, excluded allergens) in a sticky sidebar (`lg`) or a bottom sheet (mobile); state lives in the URL (same params as `GET /api/dishes`, see `src/lib/dish-filters.ts`), so links/back button reproduce the list. **Server-rendered** via `src/lib/server-api.ts` (`API_ORIGIN`) |
| `/dishes/{id}`   | Dish page (Server Component, 404 for deactivated/unknown): plate art, cook, a **Save / Saved** heart pill (favourites), the star rating under the name (links to `#reviews`), price, quantity + add, ingredients, allergens, kitchen zone + "more dishes nearby", "more from this kitchen"; the cook's verified check and whether the kitchen takes orders now ("fill your bag now and order once it opens") |
| `/cooks`, `/cooks/{id}` | Cook directory (cards with the verified check and an open / closed / paused pill) and the cook profile (Server Components): verified badge, live availability, **stats strip** (orders handed over, returning customers, acceptance rate, usual ready time, cooking since - counts only, rates once the kitchen has a track record), the **next 24 hours** as a timeline, a verification card, **How ordering works** in four steps with the kitchen's own numbers, and the current menu |
| `/login`, `/register` | Split-screen auth; cookie sessions against `/api/auth/*`; `?next=/path` returns there afterwards (same-site paths only); without it, login lands on the role's panel (`homeFor`: admin `/admin`, cook `/cook`, customer `/account`). Registration also saves the name (`PATCH /api/me/profile`) |
| `/checkout`      | Signed-in only (guests go to `/login?next=/checkout`; the guest cart moves to the account at login): **1** delivery address - pick a saved one (default preselected) or add one inline (`/api/me/addresses`), **2** note for the cook, **3** order review; sticky summary (desktop) / action bar (mobile); *Place order* = `POST /api/me/orders`. The kitchen's status shows next to its name; while it isn't taking orders (closed / paused) *Place order* is disabled with a notice, and a 409 `kitchen_closed` becomes the same message |
| `/account`       | **User panel** overview (signed-in only; guests -> `/login?next=`): greeting, live tracker for the order that needs you (a *ready* one first - with *I've received my order*, else the newest open one), bag nudge, stat cards, monthly spending bars + order-status donut (`GET /api/me/dashboard`), recent orders, most-ordered dishes (with a link to the saved favourites), address / preferences / security shortcuts |
| `/account/orders` | Orders by tab (All / Active / Completed / Cancelled - `?status=` repeated), paginated; *I've received my order* on ready ones, *Track order*, *Invoice*, *Order again* (re-adds the dishes at today's prices; asks before replacing another kitchen's bag, reports dishes no longer on the menu) |
| `/account/orders/{id}` | Order detail: confirmation (`?placed=1`), status timeline, the address copy (a pickup order's contact for the cook), note, items + total; refreshes while open; *Cancel order* (with confirmation) while `placed`; a **ready** order shows *Ready for pickup* with **I've received my order** (`components/receive-button.tsx`: confirmation dialog, then `POST /api/me/orders/{id}/receive` - the customer's confirmation is what completes an order). The old `/orders/{id}` redirects here |
| `/account/orders/{id}/invoice` | Printable invoice for a completed order (built from the order's snapshot); *Print or save as PDF* - site chrome hidden, always the light palette on paper |
| `/account/favourites` | **Favourites** (customers only - the nav item is hidden otherwise; `GET /api/me/favourites`, reloaded on every visit): the dishes saved with the heart as menu cards, *N of 50 saved*, **+ Add** straight to the bag through `POST /api/me/favourites/{id}/cart` (another kitchen's bag asks first, like everywhere); un-hearting one removes it with **Undo**; dishes their cook has **hidden** sit apart under *Not available right now* - dimmed, no link to the (private) dish page, no add, and *Remove* asks first (a hidden dish can't be saved again); a full list says so |
| `/account/reviews/{id}` | One of my reviews with the **cook's reply** (`GET /api/me/reviews/{id}`) - where a *replied to your review* notification lands; *See it on the dish page* (editing happens there); works once the dish is hidden or deleted too |
| `/account/invoices` | Invoice list (completed orders) + totals |
| `/account/notifications` | The user panel's **notification inbox** (`GET /api/me/notifications?audience=account`): order updates, cook-application answers, account and security notices, newest first; *All* / *Unread* tabs (`?tab=`, paging); opening one goes where it points and marks it read, each row can be marked read / unread or dismissed, *Mark all as read* stops at the newest one on screen; read state lives on the server (every device agrees); new arrivals reload the list; channel settings preview (email/SMS "coming soon") |
| `/account/profile` | Display name, about, area (`PATCH /api/me/profile`); email read-only; *Apply to cook* prompt for non-cooks (links to the cook application at `/cook`) |
| `/account/addresses` | Address book: add, edit, make default, delete (with confirmation) |
| `/account/payments` | Static design: "pay the cook directly" today; saved cards / wallets shown as *coming soon* (no online payments yet) |
| `/account/preferences` | Food profile - allergens to avoid + diets (`GET/PUT /api/me/preferences`) with a live "N of M dishes fit" preview; `/dishes` then offers a one-tap *Apply* |
| `/account/security` | Change password (signs out other sessions), signed-in sessions, sign out everywhere else, log out |
| `/cook`          | **Cook panel** overview (the header shows the kitchen's live status, linking to `/cook/hours`) (signed-in cooks; guests -> `/login?next=`, signed-in non-cooks get the **cook application** instead - `components/kitchen-onboarding.tsx` follows `GET /api/cooks/me/application`: the form (`POST /api/cooks`), *with our team* while pending (what was sent, what happens next), the admin's **reason** and **Apply again** (the form, filled in) after a rejection; an acceptance - noticed through the account inbox, no reload needed - refreshes the session and opens the panel): greeting, set-up checklist, **needs your attention** queue (open orders, requests first, inline accept / reject / ready - a ready order just says it waits for the customer to confirm pickup; refreshes every 30 s), money tiles (today, 7 days, month, pipeline), 14-day earnings bars + status donut, best sellers, regulars, order-handling meters, menu / bag demand / repeat-customer tiles (`GET /api/cooks/me/dashboard` + `/earnings`) |
| `/cook/orders`   | Orders by tab - **Requests** and **In progress** oldest first (the queue), Completed, Cancelled, All; counts on the tabs; actions inline; *Reject* / *Cancel* ask for an optional reason (quick picks + text) the customer sees |
| `/cook/orders/{id}` | One order for the cook: next step + action on top (a ready order: *Waiting for … to confirm pickup* - only the customer completes it), timeline ("Rejected by you"), the customer's contact for pickup (tap-to-call phone), customer + note, lines; refreshes while open |
| `/cook/reviews`  | **Reviews** of the kitchen's dishes (`GET /api/cooks/me/reviews`): the kitchen rating (average, count, per-star bars, how many wait for a reply), tabs *To answer* (default, count badge) / *Answered* / *All* (`?tab=`, paging); each card: customer, stars, date, *edited*, dish (to the editor) and order links, the words, *Needs a reply* / *Answered*; **Reply** inline (starters by rating, 1000 chars, public) -> `PUT .../reply`, then *Edit* / *Remove* (confirmed, `DELETE .../reply`); a warning when the customer edited after the reply. `?open=<id>` (a *new review* notification) puts that review on top with the reply box open. The nav's *Reviews* item carries the count still to answer (`lib/kitchen-context.tsx`, polled with the requests) |
| `/cook/notifications` | The **kitchen inbox** (`audience=cook`): new order requests (read once answered), customers cancelling, customers confirming they have their food, the verified badge coming or going - the shared inbox component |
| `/cook/earnings` | Range tabs (7 days, 30 days, 3 months by week, 12 months by month; `?range=`): earned / orders with trend vs the previous range, average order, lost to cancellations, per-period bars, per-dish table with share of earnings, open pipeline, lifetime |
| `/cook/dishes`   | The whole menu (public + private, `?show=` tabs): **public/private switch** on every card (`PATCH active`), 12-month sales, edit, delete (confirm) |
| `/cook/dishes/new`, `/cook/dishes/{id}` | Dish editor: basics, price + portions, ingredients, diet chips, allergen grid, **Public / Private** choice (*Publish dish* / *Save private draft*), live preview of the menu card; edit adds a delete zone |
| `/cook/hours`    | Hours & availability (`GET/PUT /api/cooks/me/availability`): *Pause new orders* switch (saves at once), **No fixed hours** or **Weekly hours** (up to 3 windows a day, 00:00 as a closing time = midnight, *Copy Monday to every day*), time zone (with *use this device's zone*), and what customers see for the next 24 hours |
| `/cook/profile`  | Kitchen profile - headline, specialties, neighbourhood (`PATCH /api/cooks/me`) + name, area, story (`PATCH /api/me/profile`), one save, live preview of the public cook card; shows whether the kitchen is verified |
| `/dashboard`     | Old cook tools URL - redirects to `/cook` |
| `/admin`         | **Admin panel** overview (role `admin` only; guests -> `/login?next=`, other users see an "admins only" notice): 7 / 30 / 90-day window (`?days=`), people / kitchens / orders / order value, orders-per-day bars + status donut, new accounts per day, users by role + active sessions, a callout while cook applications wait for review, top kitchens and dishes (linking to their orders), a **zone heat map** of the service grid, menu diets + allergens, open bags (`GET /api/admin/dashboard`) |
| `/admin/users`   | Every account (`GET /api/admin/users`): role tabs with counts, search by email / name as you type (`?q=`), roles, joined, last login, orders placed / received - each linking to the filtered order list; cooks carry their verification with **Verify kitchen** / *Revoke* (confirmed) - `POST/DELETE /api/admin/cooks/{id}/verification`; applicants carry *Applied to cook* / *Application rejected*, linking to the review queue |
| `/admin/orders`  | Every order (`GET /api/admin/orders`): status tabs, kitchen / customer filter chips (`?cook_id=&cook=`, `?customer_id=&customer=`), rows that expand in place (timeline, cancel reason, lines, delivery area, note); `?open=<id>` starts with that order expanded (notification links) |
| `/admin/applications` | **Cook applications** - the review queue (`GET /api/admin/cook-applications`): *Pending* (oldest first; count badge) / *Accepted* / *Rejected* / *All* tabs (`?tab=`, paging); each card shows the applicant and the kitchen they described; **Accept** (confirmed: opens the kitchen) or **Reject** with a **required** reason (≤300, shown to the applicant - the button stays off until it is written) - `POST .../{id}/accept` / `.../reject`; a 409 (another admin was faster) is explained and the list refreshes |
| `/admin/notifications` | The **admin inbox** (`audience=admin`): new cook applications, kitchens cancelling accepted orders - the same inbox component as `/account/notifications` |
| `/health`        | The original status probe: polls `GET /api/health` every 5s |

**Header (every page):** logo, links (Dishes, Cooks, How it works), the
**light/dark switch**, the **notification bell** (signed in), the cart icon
with a count badge, and - signed out - a
single *Log in* button (the login page links to registration) or - signed in
- an account menu (*Admin panel* (`/admin`) for admins, *My kitchen*
(`/cook`) for cooks, *My account*, *Log out*); below `md` a menu sheet with
the same links. There is no
search in the header: searching lives on the landing hero and `/dishes`.

**Notifications (every page, signed in):** the header bell
(`src/components/notification-bell.tsx`) carries the unread count as a badge
(the cart's style: capped at "99+", pops when it changes, exact count in the
accessible label) and opens a dropdown - a full-width sheet on phones - with
the six newest notifications (open one: it is marked read on the way; *Mark
all read*; *See all notifications*). The same count badges the panel's
*Notifications* nav item. Counts live in `src/lib/notifications.tsx`
(`NotificationsProvider`: polls `GET /api/me/notifications/unread-count`
every 30 s while the tab is visible, again when it comes back into view, and
after the user's own actions that notify them - placing an order, changing
the password; the inbox actions go through it so every badge follows). Icons,
tones and links per type: `src/lib/notification-kinds.ts` (the text is the
backend's). **Inboxes** (`INBOXES` in the same file - which exist, who sees
them, where their pages are): **`account`** (every signed-in user) and
**`admin`** (admins) and **`cook`** (cooks) are all connected. The bell's
badge counts every connected inbox the user can see; with more than one (an
admin: *Admin* + *Account*) the dropdown has a tab per inbox, each with its
count, opening on the panel the user is in (else the first with unread
ones); a cook sees *Kitchen* + *Account*. Every inbox page is
`src/components/notification-inbox.tsx` (`/account/notifications`,
`/cook/notifications`, `/admin/notifications`). Kitchen links: an order (a
new request, a customer's cancellation or confirmation of receipt) opens
`/cook/orders/{id}`, a new review opens `/cook/reviews?open={id}` (reply box
open), the verified badge opens `/cook/profile`; the *Orders* and *Reviews*
badges re-count as soon as a new kitchen notification arrives. Account links:
a cook's reply to my review opens `/account/reviews/{id}`.
Admin links: a new cook application opens `/admin/applications`, a
kitchen's late cancellation opens `/admin/orders` filtered to that
kitchen's cancelled orders with the order expanded.

**Favourites (every page):** a heart on every dish card (over the plate
art, opposite the tags) and a *Save / Saved* pill on the dish page
(`components/favourite-button.tsx`: `PUT` / `DELETE /api/me/favourites/{id}`,
both idempotent). State lives in `src/lib/favourites.tsx`
(`FavouritesProvider`: the signed-in customer's whole list - at most 50, one
request - keyed to the user like the notification counts, so every heart and
the list page agree at once; mutations apply the API's answer). Guests get
the heart too - it sends them to `/login?next=` this page; it is hidden on
the cook's own dishes (the add spot says *Your dish*) and for accounts
without the `customer` role. A refusal (*at most 50 favourite dishes*, a dish
hidden meanwhile) shows in a small bubble beside the heart, with *Manage
favourites* when the list is full.

**Reviews (dish page, `#reviews`):** `components/dish-reviews.tsx` - a
summary card (average, stars, count, per-star bars that filter the list -
click again or the chip to clear; the summary always covers every review),
the reviews newest first (author as "First L.", *Verified order*, date,
*edited*, long words clamped with *Read more*, the cook's reply nested) and
**Show more reviews (N more)**, which appends the next page
(`REVIEWS_PAGE_SIZE` = 4 in `lib/reviews.ts`; duplicates skipped if a new
review shifted the offsets; the count is announced politely). The first page
is server-rendered with the dish. Next to the summary,
`components/review-composer.tsx` adapts to the viewer: guests get *Log in to
review* (back to `#reviews`), the dish's cook a note, a customer who received
the dish (`GET /api/me/reviews/pending?dish_id=`) a 1-5 star picker
(`components/star-input.tsx`: real radio inputs, hover preview with *Poor* ...
*Excellent*) + optional words (1000, counter) -> `POST /api/me/reviews`; after
reviewing, *Your review* with the cook's reply, **Edit** (`PATCH`) and
**Delete** (confirmed); anyone else is told when they can review. Any change
reloads the list and `router.refresh()`es the server-rendered rating under
the name. Read-only stars: `components/stars.tsx` (server-safe, fractions as
a partly filled star).

**Cart (every page):** "+ Add" on dish cards, quantity + add on the dish
page, the header's bag icon with a badge counting the portions in the bag
(hidden when empty, capped at "99+", pops when it changes; the exact count is
in the button's accessible label) and a slide-over drawer (steppers, remove,
clear, subtotal, checkout). Guests shop freely; checkout
asks them to log in and the backend keeps their cart. One cook per order:
adding another cook's dish asks whether to start a new bag. State lives in
`src/lib/cart.tsx` (`add(dish, quantity, source)`: `source="favourites"` adds
a saved dish through `/api/me/favourites/{id}/cart` - same answer, same
drawer, and the new-bag question retries through the same endpoint) (each API answer is the whole cart; `reload()` after an
order) and the signed-in user in `src/lib/session.tsx`.

Browser code fetches relative `/api/*` URLs (rewritten to `API_ORIGIN` in dev
and standalone, proxied by nginx in production). Server Components (landing,
dish list, dish page, cook pages) call the backend directly at `API_ORIGIN`
- so in production `API_ORIGIN` must be reachable from the Next server at
*runtime* (not only at build time). Prices are shown in major units and
stored as integer minor units (no currency symbol yet - a product decision).
The allergen list mirrors the backend enum (`src/lib/allergens.ts` <->
`backend/app/modules/dishes/models.py`).

## Design system

"Warm editorial": paper background, ink text, an ember accent, herb
(dietary) and saffron (allergen) secondaries.

* **Tokens** - semantic colours as CSS variables in `src/app/globals.css`
  (`bg-canvas`, `bg-surface`, `text-ink`, `border-line`, `bg-brand`, ...);
  dark mode swaps the variables on `<html data-theme="dark">` (screen only -
  print always uses the light palette), so components never need `dark:`
  classes (the pre-redesign `/health` still carries its own `zinc`/`dark:`
  classes, and Tailwind's `dark:` variant follows the same attribute). The
  theme is the visitor's choice from the navbar switch (`theme-toggle`,
  remembered in `localStorage`), else the system setting - followed live
  until they choose; a tiny inline script (`lib/theme.ts`) sets it before
  the first paint, so there is no flash of the wrong palette. Shadows `shadow-card` /
  `shadow-lift` / `shadow-pop`; animations `animate-fade-in` / `-rise` /
  `-slide-in` / `-pop`.
* **Type** - Fraunces (display headings, `font-display`) + Geist (UI). All
  fonts are **self-hosted from npm** (`geist`, `@fontsource-variable/fraunces`
  via `next/font/local`): no request to Google at build or run time.
* **Primitives** - `src/components/ui.tsx` (server-safe): `Container`/`Page`,
  `PageHeader` (`size="compact"` inside panels), `SectionHeading`, `Card`,
  `Field`, `Select`, button classes (`primaryButtonClass`,
  `darkButtonClass`, `ghostButtonClass`, ...), `ButtonLink`, `Badge`,
  `Tag`/`AllergenTag`, `Avatar`, `EmptyState`, `ErrorBanner`, `Spinner`,
  `Pager`, `CountPill` (the live count on a nav item or tab - unread,
  requests, pending applications; "99+"), and `railListClass` (swipe
  carousel on phones, grid from `sm`).
  Icons: `lucide-react`. Shared pieces on top: `ConfirmDialog` (may hold a
  field - focus goes to the safe choice once, on open; portalled to `<body>`
  so a sticky/transformed ancestor can't trap it under later content), `ReceiveButton`,
  `notification-bits` (icon tile, relative time, unread dot - shared by the
  bell and the inbox), `order-bits` (status badge/timeline/order card - `perspective="cook"`
  shows the customer and links into `/cook/orders`), `ReorderButton`, `FavouriteButton` (the heart: `overlay` on cards, `pill` on the dish page), `Stars` / `StarInput`, `DishReviews` + `ReviewComposer`,
  `AddressForm` (add + edit), `account-nav` + `account-shell`, and for the
  cook panel `cook-nav` + `cook-shell` (+ `lib/kitchen-context.tsx`: cook
  profile and the open-request count behind the *Orders* badge),
  `CookOrderActions`, `DishForm`, `KitchenOnboarding`; cook vocabulary and
  helpers (checklist copy, quick reasons, UTC ranges) in `lib/kitchen.ts`;
  for the admin panel `admin-nav` + `admin-shell` (+ `lib/admin-context.tsx`:
  the pending cook-application count behind the *Cook applications* badge;
  *Notifications* carries the admin inbox's unread count) and `lib/admin.ts`
  (`ordersOf` filter links). `order-bits` also has `perspective="admin"`
  ("Rejected by the cook", "Cancelled by the customer"). Kitchen trust:
  `VerifiedBadge` (server-safe) and `availability.tsx` - `AvailabilityPill`
  and the `NextHours` 24 h timeline, positioned from the API's `as_of` and
  labelled in the viewer's time (`<time suppressHydrationWarning>`), with
  the copy in `lib/availability.ts`.
* **Charts** - `src/components/charts.tsx`: `BarChart` (HTML/CSS columns,
  readable at any width; `showValues={false}` + `labelEvery` for dense
  series), `Donut` (SVG), `StatCard`, `Trend` (+/-% vs the previous period)
  and `Meter` (0..1 bar) - no chart library; colours from the tokens, so
  dark mode and print follow.
* **Dish visuals** - the data has no photos, so every dish gets
  deterministic "plate art" (`src/components/dish-art.tsx`,
  `src/lib/dish-visual.ts`): a food-toned gradient + plate + icon derived
  from the dish *name* only, so it looks identical on cards, in the bag and
  on orders.

Try it with seeded data: `cd ../backend && uv run python scripts/seed.py`
prints `@example.com` credentials you can log in with.

## Code conventions

* **Server first.** Public, indexable pages (landing, dishes, dish, cooks)
  are Server Components fetching through `src/lib/server-api.ts`; pages that
  depend on the signed-in user are Client Components fetching relative
  `/api/*` through `src/lib/api.ts`.
* **Data hooks.** Client pages load data with `useApi(path)`
  (`src/lib/use-api.ts`) - or, for polling/custom flows, a `load` callback
  started from a `setTimeout(..., 0)` kick-off (the React Compiler lint rule
  `react-hooks/set-state-in-effect` forbids synchronous setState in effects).
* **Titles.** Every route has a `<title>`: Server Components export
  `metadata`; Client Component pages get a tiny server `layout.tsx` that only
  exports it (the root template is `%s · Plateboard`, the account one
  `%s · Your account · Plateboard`).
* **Errors** render through `ErrorBanner` with `ApiError.lines` (the API's
  field errors) and the fallback "Could not reach the API"; form field
  errors go to `Field`'s `error` prop.
* **Layout safety.** Responsive grids always declare a base column count
  (`grid grid-cols-1 ... lg:grid-cols-[...]`) and use `minmax(0,1fr)` /
  `min-w-0` for flexible tracks, so long content never widens the page on
  phones.
* **Honest UI.** Features without a backend (online payments, email/SMS) are
  shown as *coming soon* with disabled controls, never as working.
* Checks: `npx tsc --noEmit` and `npm run lint` (ESLint with the Next + React
  Compiler rules) must pass.

**Stale styles in dev?** If the page keeps old CSS after editing
`globals.css` (Turbopack's persistent dev cache), stop `npm run dev`, delete
`.next/` and start it again.

## Build for hosting

```bash
npm ci
npm run build        # API_ORIGIN comes from .env; a shell variable (e.g.
                     # API_ORIGIN=http://127.0.0.1:8000 npm run build) overrides it
```

That runs `next build` plus the `postbuild` step that copies `public/` and
`.next/static/` into `.next/standalone/` (required - Next intentionally leaves
assets out of the standalone folder). Result:

```text
.next/standalone/
  server.js          # <- this is the whole web app
  node_modules/...   # only the modules the server needs
  .next/, public/    # pages + copied assets
```

Fonts are local files from `node_modules` (`next/font/local`, see
`src/app/layout.tsx`), copied into `.next/static/media` at build time - the
build works offline and the running server never fetches fonts.

Run it (it binds from the runtime env `HOSTNAME` and `PORT`, defaults
`0.0.0.0`/`3000` - note these are **not** read from `.env`):

```bash
HOSTNAME=127.0.0.1 PORT=3000 node .next/standalone/server.js
npm start   # same command, default bind 0.0.0.0:3000
```

No `node_modules` install needed next to `server.js` - the standalone folder is
self-contained, which is why pm2 and Docker images like it.

## Production wiring

- **pm2 / nginx:** the repo-root [README](../README.md) shows how to run this
  server plus the backend under pm2 and how to split traffic in nginx
  (`/api/` -> backend, `/_next/static/` -> disk, everything else -> here).
- The `API_ORIGIN` rewrite destination is fixed when the build runs; with nginx
  routing `/api/` itself it never fires, so relative fetches work either way.

Full hosting walkthrough and the backend's commands: [root README](../README.md)
and [`../backend/README.md`](../backend/README.md).

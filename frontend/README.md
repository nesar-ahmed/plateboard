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
the `/api` rewrite and at runtime by the server-rendered dish list).
`next dev` rewrites `/api/:path*` to the backend (`API_ORIGIN`, default
`http://127.0.0.1:8000`), so start the backend too
(`cd ../backend && uv run python -m app.main`). The app fetches the relative
URL `/api/health` - same shape in every environment. `.env` is git-ignored;
`.env.example` is the committed template.

## Pages

| Route            | What it does                                                        |
| ---------------- | ------------------------------------------------------------------- |
| `/`              | Public dish list (active only, newest first): text search + filters for zone/distance, price range, dietary tags and excluded allergens; state lives in the URL (same params as `GET /api/dishes`, see `src/lib/dish-filters.ts`), so links/back button reproduce the list. **Server-rendered**: the page fetches dishes + zones on the server (`src/lib/server-api.ts`, via `API_ORIGIN`), so cards are in the HTML |
| `/dishes/{id}`   | Dish detail (404 for deactivated/unknown), link to its cook, kitchen zone + "more dishes nearby" link |
| `/cooks`         | Public cook directory (`GET /api/cooks`)                             |
| `/cooks/{id}`    | Cook profile page (with zone) + their current menu (`?cook_id=` filter) |
| `/login`, `/register` | Cookie-auth sessions against `/api/auth/*`; `?next=/path` returns there afterwards (same-site paths only) |
| `/checkout`      | Signed-in only (guests go to `/login?next=/checkout`; the guest cart moves to the account at login): order summary; *Place order* waits for the orders API |
| `/dashboard`     | Signed-in: profile form (blanking a field clears it), become-a-cook (with kitchen zone), cook profile (headline, specialties, zone), and my-dishes CRUD (create/edit/deactivate/reactivate/delete) |
| `/health`        | The original status probe: polls `GET /api/health` every 5s - status pill, database state, SQLite pragmas, version |

**Cart (every page):** "Add to cart" on dish cards and the dish page (with a
quantity picker), a cart icon with the portion count in the navbar, and a
slide-over drawer (quantity steppers, remove, clear, total, checkout). Guests
shop freely; checkout asks them to log in and the backend keeps their cart.
One cook per order: adding another cook's dish asks whether to start a new
cart. State lives in `src/lib/cart.tsx` (each API answer is the whole cart)
and the signed-in user in `src/lib/session.tsx`.

Everything fetches relative `/api/*` URLs (rewritten to `API_ORIGIN` in dev
and standalone, proxied by nginx in production). The exception is the dish list
(`/`), a Server Component that calls the backend directly at `API_ORIGIN` -
so in production `API_ORIGIN` must be reachable from the Next server at
*runtime* (not only at build time). Prices are shown in major
units and stored as integer minor units; the dashboard form does the
conversion. The allergen checkbox list mirrors the backend enum
(`src/lib/allergens.ts` ↔ `backend/app/modules/dishes/models.py`).

Try it with seeded data: `cd ../backend && uv run python scripts/seed.py`
prints `@example.com` credentials you can log in with.

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

The Geist fonts come from `next/font/google` (`src/app/layout.tsx`) and are
applied app-wide through Tailwind's `font-sans`/`font-mono` theme (no
`font-family` override in `globals.css`). They are downloaded once at build
time and self-hosted in `.next/static/media`, so the build machine needs to
reach `fonts.googleapis.com`; the running server never does.

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

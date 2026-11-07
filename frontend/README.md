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
the browser; `API_ORIGIN` is server-side only, used by `next.config.ts`).
`next dev` rewrites `/api/:path*` to the backend (`API_ORIGIN`, default
`http://127.0.0.1:8000`), so start the backend too
(`cd ../backend && uv run python -m app.main`). The app fetches the relative
URL `/api/health` - same shape in every environment. `.env` is git-ignored;
`.env.example` is the committed template.

## What it shows

The health dashboard polls `GET /api/health` every 5 seconds: status pill
(**ok** when healthy), database state, SQLite journal mode and foreign-key
enforcement, backend version and environment.

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

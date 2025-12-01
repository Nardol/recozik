# Recozik Web UI

Accessible dashboard for the Recozik identify services. Users sign in with a username/password (session cookies) and
can:

- Upload audio clips and monitor identify jobs (live updates + polling fallback).
- Inspect job history with screen-reader-friendly tables.
- Administrators: list/create tokens, toggle AudD access, and tune quota limits.

The UI is built with Next.js (App Router) and consumes the FastAPI backend documented in `docs/deploy-backend.md`.

## Prerequisites

- Node.js 20+
- Running backend at `http://localhost:8000` for local development, or configure `NEXT_PUBLIC_RECOZIK_API_BASE` to point
  at your server

## Authentication

- Sign in with the credentials configured on the backend (see `RECOZIK_WEB_ADMIN_USERNAME/RECOZIK_WEB_ADMIN_PASSWORD` or
  users created via `/auth/register`).
- Sessions use secure HttpOnly cookies; the "keep me signed in" checkbox enables a 7‑day refresh token. A CSRF token
  (`recozik_csrf`) is added automatically as `X-CSRF-Token` on mutating requests.
- The dashboard no longer accepts raw API tokens; admin users can still create tokens for the CLI from the "Admin" panel
  (use `X-API-Token` with the backend API).

## Commands

```bash
# install
npm install

# start dev server
npm run dev

# lint & type-check
npm run lint

# run component tests
npm test

# end-to-end tests (Playwright)
npx playwright install --with-deps chromium firefox webkit
npm run test:e2e
# includes axe-core accessibility smoke checks
# visual baselines (chromium only), opt-in:
# VISUAL_SNAPSHOTS=1 npm run test:e2e -- tests/e2e/visual.spec.ts --update-snapshots

# e2e without backend (mock API)
MOCK_API_PORT=9999 \
NEXT_PUBLIC_RECOZIK_API_BASE=http://localhost:9999/api \
RECOZIK_WEB_API_BASE=http://localhost:9999/api \
RECOZIK_INTERNAL_API_BASE=http://localhost:9999/api \
PORT=3000 BASE_URL=http://localhost:3000 VISUAL_SNAPSHOTS=0 \
node tests/e2e/mock-api-server.js & MOCK_PID=$! && \
npx wait-on http://localhost:9999/health && \
npm run test:e2e -- --reporter=line tests/e2e/joblist.spec.ts && \
kill $MOCK_PID

# production build
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Set `NEXT_PUBLIC_RECOZIK_API_BASE` in `.env.local` before building: use `http://localhost:8000` when running the backend
directly, or `/api` when routing through the Docker/Nginx stack. See `docs/deploy-frontend.md` for deployment
instructions (bare-metal + container recipe).

# Recozik Web UI

Accessible dashboard for the Recozik identify services. Users authenticate with the same API tokens used by the CLI and can:

- Upload audio clips and monitor identify jobs (live updates + polling fallback).
- Inspect job history with screen-reader friendly tables.
- Administrators: list/create tokens, toggle AudD access, and tune quota limits.

The UI is built with Next.js (App Router) and consumes the FastAPI backend documented in `docs/deploy-backend.md`.

## Prerequisites

- Node.js 20+
- Running backend (default `http://localhost:8000`) or the `NEXT_PUBLIC_RECOZIK_API_BASE` env variable pointing to your server

## Commands

```bash
# install
npm install

# start dev server
npm run dev

# lint & type-check
npm run lint

# production build
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Set `NEXT_PUBLIC_RECOZIK_API_BASE` in `.env.local` to the backend base URL before building (the Docker stack defaults to `/api`). See `docs/deploy-frontend.md` for deployment instructions (bare-metal + container recipe).

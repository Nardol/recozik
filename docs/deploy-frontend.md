# Deploying the Recozik web frontend

The React/Next.js frontend in `packages/recozik-webui` provides an accessible dashboard for operators and admins. It consumes the FastAPI backend over HTTPS.

## Prerequisites

- Node.js 20 LTS (or newer)
- npm 10+
- A running backend reachable over HTTPS (see `docs/deploy-backend.md`)
- Reverse proxy (Caddy, Nginx, Apache) to terminate TLS for both the backend and frontend

## 1. Install dependencies

```bash
cd /path/to/recozik/packages/recozik-webui
npm install
```

## 2. Configure environment

Copy the sample env file and update the API base URL:

```bash
cp .env.example .env.local
# Edit .env.local
NEXT_PUBLIC_RECOZIK_API_BASE=https://recozik.example.com
```

The value must point to the publicly accessible backend hostname (without a trailing slash). The frontend never stores tokens server-side; tokens live in the browser.

## 3. Build & start (bare-metal)

```bash
npm run build
npm run start -- --hostname 0.0.0.0 --port 3000
```

Place your reverse proxy in front of the Next.js server, handle TLS there, and forward `/` traffic to port 3000.

## 4. Reverse proxy example (Caddy)

```
recozik-ui.example.com {
  reverse_proxy 127.0.0.1:3000
  encode zstd gzip
}

recozik-api.example.com {
  reverse_proxy 127.0.0.1:8000
}
```

Ensure both origins share the same top-level domain so that browsers treat them as trusted peers.

## 5. Accessibility & smoke tests

- Sign in with an admin token and verify the dashboard announces status updates via screen reader.
- Upload an audio file and confirm the job table refreshes and the live region announces progress.
- Navigate via keyboard only (Tab/Shift+Tab) and ensure focus outlines are visible.
- Run `npm run lint` to execute ESLint + Next.js type checks.

## 6. Containerized deployment (Docker Compose)

To spin up the backend, dashboard, and Nginx with a single command:

```bash
cd docker
cp .env.example .env  # customise tokens + API keys
docker compose up --build
# Podman users can rely on the shim:
# podman-compose up --build
```

- Dashboard: <http://localhost:8080>
- Backend API: <http://localhost:8080/api>

The frontend container defaults to `NEXT_PUBLIC_RECOZIK_API_BASE=/api`, so browsers automatically target the same origin served by Nginx. Override the variable in `.env` if you expose the stack under a different hostname or path.

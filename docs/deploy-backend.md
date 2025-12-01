# Deploying the Recozik web backend

The FastAPI backend in `packages/recozik-web` exposes the CLI features over HTTP (token auth, quotas, upload jobs,
WebSockets). This guide explains how to run it on a bare-metal host.

## Prerequisites

- Linux host with Python 3.11 or later
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Optional: systemd (or another process manager) to keep the service running

## 1. Install dependencies

```bash
cd /path/to/recozik
uv sync --all-groups
```

The sync step creates `.venv/` and installs both runtime and development dependencies.

## 2. Configure environment variables

All settings live under the `RECOZIK_WEB_` prefix. The most important ones:

| Variable                            | Description                                                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `RECOZIK_WEB_BASE_MEDIA_ROOT`       | Directory that stores uploads, SQLite databases, and cached media. Default: current working directory. |
| `RECOZIK_WEB_UPLOAD_SUBDIR`         | Relative path under the media root for temporary uploads. Default: `uploads`.                          |
| `RECOZIK_WEB_ADMIN_TOKEN`           | Token with `admin` role used for the CLI + admin API.                                                  |
| `RECOZIK_WEB_ADMIN_USERNAME`        | Username for the seeded admin account (default: `admin`).                                              |
| `RECOZIK_WEB_ADMIN_PASSWORD`        | Password for the seeded admin account (must be set to a strong value in production).                   |
| `RECOZIK_WEB_PRODUCTION_MODE`       | Set to `true` to enforce Secure+Strict cookies and reject default admin token/password.                |
| `RECOZIK_WEB_ACOUSTID_API_KEY`      | Your AcoustID key used during identification.                                                          |
| `RECOZIK_WEB_AUDD_TOKEN`            | Optional AudD token. Leave unset to disable.                                                           |
| `RECOZIK_WEB_JOBS_DATABASE_URL`     | SQLModel URL for the jobs database. Default: SQLite file next to the media root.                       |
| `RECOZIK_WEB_AUTH_DATABASE_URL`     | SQLModel URL for the auth/token database. Default: SQLite file next to the media root.                 |
| `RECOZIK_WEB_RATE_LIMIT_ENABLED`    | Toggle global rate limiting (default: `true`).                                                         |
| `RECOZIK_WEB_RATE_LIMIT_PER_MINUTE` | Default API window (60/min). Auth endpoints enforce their own stricter 5/min limit.                    |

> **Security:** Generate a strong random value for `RECOZIK_WEB_ADMIN_TOKEN` (for example `openssl rand -hex 32`). Never
> reuse the placeholder token in production.

Example `.env` snippet:

```bash
RECOZIK_WEB_BASE_MEDIA_ROOT=/var/lib/recozik
RECOZIK_WEB_ADMIN_TOKEN=your-secure-random-token-here
RECOZIK_WEB_ADMIN_USERNAME=admin
RECOZIK_WEB_ADMIN_PASSWORD=change-me-strong
RECOZIK_WEB_ACOUSTID_API_KEY=xxx
RECOZIK_WEB_AUDD_TOKEN=
RECOZIK_WEB_UPLOAD_SUBDIR=uploads
RECOZIK_WEB_PRODUCTION_MODE=true
```

Create the media root and uploads directory with the correct permissions before launching the app.

### Session-based auth & CSRF

- Web UI uses session cookies: `recozik_session` (access), `recozik_refresh` (refresh), plus `recozik_csrf` for CSRF
  double-submit. Cookies are `Secure`/`SameSite=Strict` in production, `Lax` in development.
- Mutating endpoints expect header `X-CSRF-Token` matching the `recozik_csrf` cookie; the dashboard sets it
  automatically.
- CLI/automation still use `X-API-Token` (admin/readonly or generated tokens) as a fallback.

## 3. Run the FastAPI application

Use `uvicorn` (installed via `uv sync`) to serve the app:

```bash
uv run uvicorn recozik_web.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info
```

Enable CORS or TLS termination at the reverse proxy layer if you plan to access the API from the public Internet or the
React frontend.

### Multi-worker deployments

The backend seeds admin and readonly users/tokens during application startup (via the FastAPI lifespan handler). When
running with multiple workers (e.g., `gunicorn -w 4` or `uvicorn --workers 4`), each worker process executes the startup
seeding independently, which can cause brief SQLite lock contention as workers concurrently attempt to upsert the same
seed tokens.

**Impact:** This is safe—SQLite's `UNIQUE` constraints and the `upsert` logic prevent data corruption—but you may observe
transient `SQLITE_BUSY` warnings in logs during startup. The locks resolve automatically within milliseconds.

**Recommended deployment patterns:**

1. **Container orchestration (Kubernetes, Docker Swarm):** Run **one worker per container** and scale horizontally by
   adding more containers. This is the preferred approach for production:

   ```bash
   # Each container runs a single uvicorn process
   uvicorn recozik_web.app:app --host 0.0.0.0 --port 8000
   ```

   When using Kubernetes, scale replicas instead of workers:

   ```yaml
   spec:
     replicas: 4 # Four pods, each with one worker
   ```

2. **Bare-metal multi-worker:** If you need multiple workers in a single process (e.g., `gunicorn -w 4` on a VM), the
   startup locks are harmless. Ensure the SQLite database files are on a local filesystem (not NFS) with proper
   permissions.

3. **Pre-seed at build time (optional):** For deterministic container images, you can seed users/tokens during the Docker
   build step to eliminate runtime seeding entirely:

   ```dockerfile
   # In Dockerfile, after installing dependencies
   RUN python -c "from recozik_web.auth import seed_users_and_tokens_on_startup; \
                  from recozik_web.config import get_settings; \
                  seed_users_and_tokens_on_startup(get_settings())"
   ```

   Note: This approach requires that `RECOZIK_WEB_ADMIN_TOKEN` and related secrets are available at build time, which may
   not be desirable for security reasons.

**Troubleshooting:** If you see persistent lock errors (lasting > 1 second) during startup, verify that:

- The database files (`auth.db`, `jobs.db`) are on a **local** filesystem, not a network mount
- The `RECOZIK_WEB_BASE_MEDIA_ROOT` directory has correct ownership/permissions
- No other process is holding locks on the SQLite files

For high-availability setups with multiple backend instances, use one worker per container and a load balancer
(e.g., Nginx, Traefik) to distribute requests.

## 4. Optional: systemd service

```ini
[Unit]
Description=Recozik Web API
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/recozik
EnvironmentFile=/etc/recozik-web.env
ExecStart=/path/to/recozik/.venv/bin/uvicorn recozik_web.app:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=recozik
Group=recozik
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/recozik
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
```

Reload systemd, enable, and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now recozik-web.service
```

## 5. Health checks

- `GET /health` returns `{ "status": "ok" }`.
- `GET /whoami` confirms token metadata.
- `GET /jobs/{id}` and `WS /ws/jobs/{id}` validate job persistence and streaming.

## 6. Containerized deployment (Docker Compose)

The repository ships with ready-to-use Docker definitions under `docker/`:

```bash
cd docker
cp .env.example .env  # edit tokens/keys inside
docker compose up --build
# or, with Podman (older releases ship the podman-compose shim):
# podman-compose up --build
# start the reverse proxy only when needed
# docker compose --profile reverse-proxy up --build
```

This stack launches three containers:

1. **backend** – Python image built from `docker/backend.Dockerfile`, storing uploads/SQLite data under the
   `recozik-data` volume (mounted at `/data`).
2. **frontend** – Next.js dashboard served via `npm run start` (see `docker/frontend.Dockerfile`).
3. **nginx** – Fronts both services on port `8080`, exposing:
   - `http://localhost:8080` → dashboard
   - `http://localhost:8080/api` → FastAPI REST endpoints

Update `.env` with your production tokens/keys before deploying. The Compose setup is also handy for local development
if you don't want to maintain a bare-metal Nginx installation.

Compose-specific `.env` keys (all optional but recommended to set explicitly):

| Variable                      | Purpose / maps to backend env                      | Default in example |
| ----------------------------- | -------------------------------------------------- | ------------------ |
| `RECOZIK_ADMIN_TOKEN`         | Admin API token → `RECOZIK_WEB_ADMIN_TOKEN`        | `dev-admin`        |
| `RECOZIK_WEB_ADMIN_USERNAME`  | Seeded admin username                              | `admin`            |
| `RECOZIK_WEB_ADMIN_PASSWORD`  | Seeded admin password                              | `dev-password`     |
| `RECOZIK_WEB_READONLY_TOKEN`  | Optional readonly API token                        | empty              |
| `RECOZIK_ACOUSTID_API_KEY`    | AcoustID key                                       | `demo-key`         |
| `RECOZIK_AUDD_TOKEN`          | AudD token (leave empty to disable)                | empty              |
| `RECOZIK_WEB_PRODUCTION_MODE` | Enforce secure cookies/HSTS, block default secrets | `false`            |
| `RECOZIK_WEB_BASE_MEDIA_ROOT` | Media + DB root mounted into the backend container | `/data`            |
| `RECOZIK_WEB_UPLOAD_SUBDIR`   | Relative upload folder under the media root        | `uploads`          |
| `RECOZIK_WEBUI_UPLOAD_LIMIT`  | Upload size limit passed at frontend build time    | `100mb`            |

Replace every development placeholder before exposing the stack publicly.

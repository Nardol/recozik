# Deploying the Recozik web backend

The FastAPI backend in `packages/recozik-web` exposes the CLI features over HTTP (token auth, quotas, upload jobs, WebSockets). This guide explains how to run it on a bare-metal host.

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

| Variable                        | Description                                                                                            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `RECOZIK_WEB_BASE_MEDIA_ROOT`   | Directory that stores uploads, SQLite databases, and cached media. Default: current working directory. |
| `RECOZIK_WEB_UPLOAD_SUBDIR`     | Relative path under the media root for temporary uploads. Default: `uploads`.                          |
| `RECOZIK_WEB_ADMIN_TOKEN`       | Token with `admin` role used for the CLI + admin API.                                                  |
| `RECOZIK_WEB_ACOUSTID_API_KEY`  | Your AcoustID key used during identification.                                                          |
| `RECOZIK_WEB_AUDD_TOKEN`        | Optional AudD token. Leave unset to disable.                                                           |
| `RECOZIK_WEB_JOBS_DATABASE_URL` | SQLModel URL for the jobs database. Default: SQLite file next to the media root.                       |
| `RECOZIK_WEB_AUTH_DATABASE_URL` | SQLModel URL for the auth/token database. Default: SQLite file next to the media root.                 |

Example `.env` snippet:

```bash
RECOZIK_WEB_BASE_MEDIA_ROOT=/var/lib/recozik
RECOZIK_WEB_ADMIN_TOKEN=change-me
RECOZIK_WEB_ACOUSTID_API_KEY=xxx
RECOZIK_WEB_AUDD_TOKEN=
RECOZIK_WEB_UPLOAD_SUBDIR=uploads
```

Create the media root and uploads directory with the correct permissions before launching the app.

## 3. Run the FastAPI application

Use `uvicorn` (installed via `uv sync`) to serve the app:

```bash
uv run uvicorn recozik_web.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info
```

Enable CORS or TLS termination at the reverse proxy layer if you plan to access the API from the public Internet or the React frontend.

## 4. Optional: systemd service

```
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

## 6. Future containerization

The backend works bare-metal, but you can containerize it later by:

1. Copying `pyproject.toml`, `uv.lock`, and `packages/recozik-*` into an image.
2. Running `uv sync --locked` at build time.
3. Exposing port 8000 and mounting the media root as a volume.

# Repository Guidelines

## Project Structure & Module Organization

- `src/recozik/cli.py` – Typer app registration + backward-compatible shims (exposes lazy symbols such as `compute_fingerprint`, `LookupCache`, completion helpers).
- `src/recozik/commands/` – Feature-focused command modules (`inspect`, `fingerprint`, `identify`, `identify_batch`, `rename`, `config`, `completion`).
- `src/recozik/cli_support/` – Thin re-export layer pointing to the shared service helpers (locale resolution, path helpers, metadata/log formatting, prompts, lazy dependency loaders).
- `packages/recozik-services/src/recozik_services/` – Service layer consumed by the CLI and future GUIs (identify, batch identify, rename runners plus callback/prompt protocols). Implement new behaviour here first so every frontend stays in sync.
- `packages/recozik-services/src/recozik_services/security.py` – Auth/authorization/quota protocols + default policies every frontend must wire up.
- `packages/recozik-web/src/recozik_web/` – FastAPI backend exposing the shared services over HTTP (token auth, quota policy wiring, filesystem identify endpoint, async upload/jobs API + polling/WebSocket hooks).
- `packages/recozik-webui/` – Next.js dashboard that consumes the HTTP API (token login, upload panel, job monitoring, admin token management). Keep accessibility (screen readers, keyboard navigation) in mind when adding components.
- `packages/recozik-core/src/recozik_core/` – Core libraries (`fingerprint.py`, `cache.py`, `config.py`, `audd.py`, `i18n.py`, locales) consumed by the CLI, backend, and UI.
- `tests/` – Pytest suites mirroring CLI features and performance guards (includes `test_cli_import_time.py`).
- `README.md` – User-facing quick start; keep it in sync when commands change.
- `dist/`, `build/`, and `.venv/` are generated artifacts; never commit them.

## Build, Test, and Development Commands

- `uv sync --all-groups` – Install runtime + dev dependency groups defined in `pyproject.toml`.
- `uv run recozik …` – Execute CLI commands (e.g., `uv run recozik identify sample.flac`).
- `uv run ruff check --fix` – Run Ruff with automatic fixes (must pass before committing).
- `uv run ruff format` – Apply Ruff formatter to keep code style consistent.
- `uv run mypy` – Run static type checks (entire `src/recozik` + `recozik_core` must stay clean).
- `uv run pytest` – Run the full automated test suite.
- `cd packages/recozik-webui && npm install && npm run lint` – Install frontend dependencies and run Next.js lint/type checks before touching the dashboard.
- `cd docker && docker compose up --build` – Launch the full stack (backend + frontend + Nginx). Populate `docker/.env` with real tokens/keys before sharing instructions.
- `uv build` – Produce wheel + sdist for validation before releases.

> **Permission reminder:** Always request elevated permissions before running any `uv` command (`uv run …`, `uv sync …`, etc.).

## Coding Style & Naming Conventions

- Python 3.10–3.13, 4-space indentation, type hints encouraged. Python 3.14 stays experimental until upstream (librosa/numba) ships stable wheels.
- CLI options use kebab-case (e.g., `--log-format`); internal functions use snake_case.
- Keep Typer command logic inside the relevant module under `src/recozik/commands/`; `cli.py` should only register commands and surface compatibility wrappers.
- When adding or modifying core behaviour (identify/batch/rename workflows), write it under `packages/recozik-services` first, then add the thin CLI glue that builds requests and forwards callbacks/prompts.
- When touching completion logic, update both `src/recozik/commands/completion.py` and the wrapper wiring in `cli.py` so tests that monkeypatch `recozik.cli` continue to work.
- Sanitize filenames using `_sanitize_filename`; reuse helpers instead of ad-hoc logic.
- Route every user-facing string through `recozik_core.i18n._` using an English msgid. Update the relevant `.po` file under `packages/recozik-core/src/recozik_core/locales/<lang>/LC_MESSAGES/` and recompile the `.mo` file when strings change.
- Store AcoustID/AudD secrets via `recozik_core.secrets` (system keyring); never write them in plaintext config files.
- Honor locale precedence in this order: CLI option `--locale` > environment variable `RECOZIK_LOCALE` > config `[general].locale` > system locale.
- Favor readability-first helpers (`cli_support.options.resolve_option`, `cli_support.audd_helpers.get_audd_support`, etc.) so new code avoids redundant logic.

## Testing Guidelines

- Framework: Pytest (`tests/` modules prefixed `test_`).
- Cover new CLI flags with focused tests using `CliRunner` and temp directories.
- When adding dependencies, verify `uv run pytest` passes locally and in dry-run modes (`--dry-run`, `--json`).
- Prefer deterministic fixtures; avoid network calls in tests.
- Keep the import-time guard (`tests/test_cli_import_time.py`) passing; if startup logic gets heavier, adjust thresholds deliberately and document why.
  - Quick check: `uv run python scripts/measure_import_time.py` (helper script) or the inline snippet from README to confirm the import stays under 0.5 s.

## Commit & Pull Request Guidelines

- Commit messages follow imperative tone (e.g., “Add interactive selection to rename-from-log”) and include `-s` for signed-off compliance.
- Each commit should keep tests passing; squash only when history becomes noisy.
- Pull requests should summarize behavior changes, list new CLI flags, and note docs/tests touched. Include sample commands or log snippets when relevant.
- Link to issues or TODO comments when closing tasks; attach screenshots only if UI output changes (e.g., help text).

## Agent-Specific Tips

- Always run `git status` before exiting to ensure a clean tree.
- If GPG signing blocks commits, rerun with elevated permissions (`with_escalated_permissions: true`).
- Request the user's approval before running any `uv …` command and rerun with `with_escalated_permissions: true` once granted (it unlocks workspace access, not sudo).
- See `TRANSLATION.md` for the translation workflow (extraction, `.mo` compilation, multi-locale testing).
- When updating the web backend or dashboard, keep `docs/deploy-backend.md` and `docs/deploy-frontend.md` current so operators can redeploy without guesswork.
- When adding new commands, create a dedicated module under `src/recozik/commands/`, surface any required backward-compatible aliases via `cli.py`, and extend this doc/README as needed.
- Always sanity-check execution costs: keep lazy imports intact, avoid unnecessary `Path.resolve()` churn in hot paths, and document trade-offs if a feature must slow things down.

---

## Core Library Cheat Sheet (packages/recozik-core)

| Component        | Purpose & Notes                                                                                                                                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fingerprint.py` | Provides `compute_fingerprint`, `lookup_recordings`, `FingerprintResult`, and `AcoustIDMatch`. Raise `FingerprintError` / `AcoustIDLookupError` for user-facing failures.                                           |
| `cache.py`       | `LookupCache` stores AcoustID responses in JSON (default `~/.cache/recozik/lookup-cache.json`). Honor `enabled` and `ttl`; call `save()` after writes.                                                              |
| `audd.py`        | Handles AudD standard + enterprise uploads, snippet preparation (12 s mono WAV), and converts AudD results into `AcoustIDMatch`. Watch for `AudDLookupError` and use `AudDMode` / `AudDEnterpriseParams`.           |
| `config.py`      | `AppConfig` encapsulates `[acoustid]`, `[audd]`, `[cache]`, `[musicbrainz]`, `[identify]`, `[identify_batch]`, `[rename]`, `[general]`. Use `load_config`, `write_config`, and keyring helpers for API keys/tokens. |
| `musicbrainz.py` | `MusicBrainzClient` enforces rate limits (default 1 req/s), retries, and the `MusicBrainzSettings` structure reused in CLI + backend. `looks_like_mbid` avoids bogus lookups.                                       |
| `i18n.py`        | Locale resolution + `_()` helper. Always wrap user-visible strings before they reach CLI/HTTP/UI layers.                                                                                                            |

Whenever you add new behaviour, extend the shared core/service first so CLI, backend, and web UI stay aligned.

## Backend FastAPI Overview (packages/recozik-web)

### REST & WebSocket endpoints

| Endpoint                      | Description & Params                                                                                                                                                             | Notes                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `POST /identify/from-path`    | JSON payload referencing a file under `base_media_root`. Accepts `audio_path`, `refresh_cache`, `metadata_fallback`, `prefer_audd`, `force_audd_enterprise`, `enable_audd`, etc. | Validates paths against traversal/symlink attacks and enforces feature/quota policies. |
| `POST /identify/upload`       | Multipart upload (`file`) with the same options; persists temp file then enqueues a job. Returns `{job_id, status}`.                                                             | Upload size limited by `max_upload_mb`; allowed extensions set via config.             |
| `GET /jobs/{job_id}`          | Returns job detail (`status`, timestamps, messages, serialized identify result).                                                                                                 | Restricted to owner or admin.                                                          |
| `GET /jobs`                   | Lists recent jobs (`limit`, `offset`, optional `user_id` for admins).                                                                                                            | Default limit 20, cap 100.                                                             |
| `WebSocket /ws/jobs/{job_id}` | Streams job snapshots + status/message/result events.                                                                                                                            | Requires `X-API-Token` header; closes on unauthorized access.                          |
| `GET /whoami`                 | Echoes token profile (user_id, roles, allowed features).                                                                                                                         | Handy for smoke tests.                                                                 |
| `GET/POST /admin/tokens`      | Admin-only list/create tokens; payload mirrors `TokenCreateModel` (user, display name, roles, allowed features, quota limits).                                                   | Configurable hash storage via `auth.db`.                                               |

### Auth & quota model

- Tokens are supplied via `X-API-Token` header (or cookie for WebSocket). Static tokens: `RECOZIK_WEB_ADMIN_TOKEN`, optional `RECOZIK_WEB_READONLY_TOKEN`. Dynamic tokens stored in SQLite (`auth.db`).
- `ServiceFeature` values: `identify`, `identify_batch`, `rename`, `audd`, `musicbrainz_enrich`. Tokens carry an `allowed_features` set; `TokenAccessPolicy` rejects unsupported calls with 403.
- Quotas use `QuotaScope` keys (`acoustid_lookup`, `musicbrainz_enrich`, `audd_standard_lookup`, `audd_enterprise_lookup`). `InMemoryQuotaPolicy` + optional persistent policy (`persistent_quota.py`) enforce per-user limits and raise 429.

### Backend settings (`RECOZIK_WEB_*`)

| Variable                                                                         | Meaning (defaults in `WebSettings`)                                         |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `ADMIN_TOKEN`, `READONLY_TOKEN`                                                  | Default admin/readonly API tokens (set strong random values in production). |
| `ACOUSTID_API_KEY`, `AUDD_TOKEN`, `AUDD_ENDPOINT_*`                              | Credentials forwarded to `identify_track`.                                  |
| `BASE_MEDIA_ROOT`, `UPLOAD_SUBDIR`, `MAX_UPLOAD_MB`, `ALLOWED_UPLOAD_EXTENSIONS` | File-system sandbox + upload limits.                                        |
| `CACHE_ENABLED`, `CACHE_TTL_HOURS`                                               | Server-side LookupCache options.                                            |
| `MUSICBRAINZ_*`                                                                  | Toggle + user-agent metadata for enrichment.                                |
| `JOBS_DB_FILENAME`, `AUTH_DB_FILENAME`, `JOBS_DATABASE_URL`, `AUTH_DATABASE_URL` | SQLModel persistence paths/URLs.                                            |
| `CORS_ENABLED`, `CORS_ORIGINS`, `SECURITY_*`, `RATE_LIMIT_*`                     | HTTP hardening (CORS, HSTS, CSP, throttling).                               |

See `packages/recozik-web/src/recozik_web/config.py` for the exhaustive list.

## Web UI Overview (packages/recozik-webui)

- **Architecture**: Next.js (App Router) with localized routes (`/[locale]`). `app/page.tsx` redirects based on `Accept-Language`; `LanguageSwitcher` lets users toggle manually.
- **Job upload**: `JobUploader` posts a multipart form via `uploadAction`, forwarding `metadata_fallback`, `prefer_audd`, `force_audd_enterprise`. On success, it pushes the queued job into the dashboard state.
- **Job monitoring**: `JobList` combines WebSocket updates (`createJobWebSocket`) with periodic polling using `fetchJobDetail`. Live regions/table semantics keep the view screen-reader friendly.
- **Admin tooling**: `AdminTokenManager` uses `/admin/tokens` to list/create tokens (roles, features, quota scopes). Only shows up when `whoami.roles` contains `admin`.
- **API client**: `src/lib/api.ts` centralizes calls (`fetchWhoami`, `uploadJob`, `fetchJobs`, `createToken`) and enforces the `X-API-Token` header. `NEXT_PUBLIC_RECOZIK_API_BASE` must point to the backend (default `/api`).
- **Accessibility**: Keep `SkipLink`, `aria-live` regions, focus management, and translation keys intact when modifying layouts.
- **Dev commands**: `npm install`, `npm run dev`, `npm run lint`, `npm run build`, `npm run start -- --hostname 0.0.0.0 --port 3000`.

## Docker / Compose Stack

- `docker/docker-compose.yml` wires backend, frontend, and Nginx. Use `docker/.env` to define `RECOZIK_WEB_*`, `NEXT_PUBLIC_RECOZIK_API_BASE`, tokens, secrets, volume paths.
- Commands: `cd docker && docker compose up --build` for full stack; `docker compose down -v` to wipe volumes if needed.
- Ensure media directories mounted in compose match `RECOZIK_WEB_BASE_MEDIA_ROOT`; keep TLS/certs and reverse proxy headers aligned with the backend security middleware.

## Environment Variable Quick Reference

| Context        | Keys                                                                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| CLI / services | `ACOUSTID_API_KEY`, `AUDD_API_TOKEN`, `RECOZIK_LOCALE`, `AUDD_*` tuning vars (mode, skip, every, limit, endpoints), `RECOZIK_CONFIG_FILE`. |
| Backend        | `RECOZIK_WEB_*` settings listed above (auth, cache, upload, security).                                                                     |
| Web UI         | `NEXT_PUBLIC_RECOZIK_API_BASE` (use `/api` when front+back sit behind the Docker proxy).                                                   |
| Docker         | `.env` file mirrors backend + frontend vars; supply tokens and storage paths once to keep all services consistent.                         |

Keep these tables up to date whenever behaviour or configuration changes so every agent (CLI, backend, UI) consumes the same source of truth.

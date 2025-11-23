# Repository Guidelines

## Project Structure & Module Organization

- `src/recozik/cli.py` – Typer app registration + backward-compatible shims (exposes lazy symbols such as `compute_fingerprint`, `LookupCache`, completion helpers).
- `src/recozik/commands/` – Feature-focused command modules (`inspect`, `fingerprint`, `identify`, `identify_batch`, `rename`, `config`, `completion`).
- `src/recozik/cli_support/` – Thin re-export layer pointing to the shared service helpers (locale resolution, path helpers, metadata/log formatting, prompts, lazy dependency loaders).
- `packages/recozik-services/src/recozik_services/` – Service layer consumed by the CLI and future GUIs (identify, batch identify, rename runners plus callback/prompt protocols). Implement new behaviour here first so every frontend stays in sync.
- `packages/recozik-services/src/recozik_services/security.py` – Auth/authorization/quota protocols + default policies every frontend must wire up.
- `packages/recozik-web/src/recozik_web/` – FastAPI backend exposing the shared services over HTTP (token auth, quota policy wiring, filesystem identify endpoint, async upload/jobs API + polling/WebSocket hooks).
- `packages/recozik-webui/` – Next.js dashboard that consumes the HTTP API (username/password session login, upload panel, job monitoring, admin token management). Keep accessibility (screen readers, keyboard navigation) in mind when adding components.
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
- Frontend (web UI):
  - `cd packages/recozik-webui && npm install && npm run lint` – Install deps and lint/type-check the dashboard.
  - `cd packages/recozik-webui && npm test -- --run` – Run Vitest component/unit tests (jsdom + Testing Library).
  - `cd packages/recozik-webui && npm run test:e2e` – Playwright E2E suite (includes axe-core accessibility smoke); ensure browsers are installed with `npx playwright install --with-deps chromium firefox webkit`.
  - Local E2E with mock API (no backend needed):
    ```bash
    cd packages/recozik-webui
    export MOCK_API_PORT=9999
    NEXT_PUBLIC_RECOZIK_API_BASE=http://localhost:$MOCK_API_PORT \
    RECOZIK_WEB_API_BASE=http://localhost:$MOCK_API_PORT \
    RECOZIK_INTERNAL_API_BASE=http://localhost:$MOCK_API_PORT \
    PORT=3000 BASE_URL=http://localhost:3000 VISUAL_SNAPSHOTS=0
    node tests/e2e/mock-api-server.js & MOCK_PID=$!
    npx wait-on http://localhost:$MOCK_API_PORT/health
    npm run test:e2e -- --reporter=line tests/e2e/joblist.spec.ts
    kill $MOCK_PID
    ```
    Install Playwright browsers once with `npx playwright install chromium firefox webkit` (no `--with-deps` if system deps are preinstalled).
  - E2E storage helper: `packages/recozik-webui/tests/e2e/bootstrap-auth.js` can pre-generate `tests/e2e/storage/auth.json` with mock session cookies for ad-hoc runs (see `packages/recozik-webui/tests/README.md`).
  - `cd packages/recozik-webui && npm run test:e2e -- tests/e2e/visual.spec.ts --update-snapshots` – Update visual baselines (chromium only) for UI screenshots; keep viewport and data deterministic.
  - `cd packages/recozik-webui && npm run build` – Production build; CI runs lint → tests → build in that order.
- `cd docker && docker compose up --build` – Launch the full stack (backend + frontend + Nginx). Populate `docker/.env` with real tokens/keys before sharing instructions.
- `uv build` – Produce wheel + sdist for validation before releases.

> **Permission reminder:** Always request elevated permissions before running any `uv` command (`uv run …`, `uv sync …`, etc.).

## Coding Style & Naming Conventions

- Supported Python versions mirror `pyproject.toml` (see the `requires-python` constraint). Treat the version baked into `docker/backend.Dockerfile` as the recommended runtime for automation agents, while any interpreter allowed by `pyproject.toml` stays valid for local development. Python versions beyond that declared range are considered experimental until upstream dependencies (librosa/numba) publish official wheels.
- CLI options use kebab-case (e.g., `--log-format`); internal functions use snake_case.
- Keep Typer command logic inside the relevant module under `src/recozik/commands/`; `cli.py` should only register commands and surface compatibility wrappers.
- When adding or modifying core behaviour (identify/batch/rename workflows), write it under `packages/recozik-services` first, then add the thin CLI glue that builds requests and forwards callbacks/prompts.
- When touching completion logic, update both `src/recozik/commands/completion.py` and the wrapper wiring in `cli.py` so tests that monkeypatch `recozik.cli` continue to work.
- Sanitize filenames using `sanitize_filename` from `recozik_services.cli_support.paths`; reuse helpers instead of ad-hoc logic.
- Route every user-facing string through `recozik_core.i18n._` using an English msgid. Update the relevant `.po` file under `packages/recozik-core/src/recozik_core/locales/<lang>/LC_MESSAGES/` and recompile the `.mo` file when strings change.
- Store AcoustID/AudD secrets via `recozik_core.secrets` (system keyring); never write them in plaintext config files.
- Honor locale precedence in this order: CLI option `--locale` > environment variable `RECOZIK_LOCALE` > config `[general].locale` > system locale.
- Favor readability-first helpers (`cli_support.options.resolve_option`, `cli_support.audd_helpers.get_audd_support`, etc.) so new code avoids redundant logic.

## Documentation & Localization Policy

- Every behavioural or structural change must be reflected in the relevant docs: `.github/copilot-instructions.md`, `README.md`, `README.fr.md`, `docs/deploy-*.md` (EN + FR), `TRANSLATION.md`, and any feature-specific guides.
- Frontend changes that affect UX, routes, or strings must update both English and French documentation plus the Next.js copy in `packages/recozik-webui/src/i18n`. Use the existing message keys and add translations for each locale file before committing UI changes.
- When adding or modifying translatable strings (CLI/services/frontend), run `python scripts/compile_translations.py` to regenerate `.mo` files and review `packages/recozik-core/src/recozik_core/locales/**/LC_MESSAGES/recozik.po` for parity.
- Keep `AGENTS.md` (and its symlinked copies `CLAUDE.md`, `GEMINI.md`) in sync with this file; edit `.github/copilot-instructions.md` and let the symlinks inherit the content unless something breaks.
- Before merging, confirm that new instructions needed by automation agents (Codex, Copilot, Jules, etc.) are captured in `.github/copilot-instructions.md` so all AI helpers share the same expectations.

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
- If pre-commit blocks commits, rerun with elevated permissions (`with_escalated_permissions: true`).
- If GPG signing blocks commits, rerun with elevated permissions (`with_escalated_permissions: true`).
- Request the user's approval before running any `uv …` command and rerun with `with_escalated_permissions: true` once granted (it unlocks workspace access, not sudo).
- See `TRANSLATION.md` for the translation workflow (extraction, `.mo` compilation, multi-locale testing).
- When updating the web backend or dashboard, keep `docs/deploy-backend.md` and `docs/deploy-frontend.md` current so operators can redeploy without guesswork.
- When adding new commands, create a dedicated module under `src/recozik/commands/`, surface any required backward-compatible aliases via `cli.py`, and extend this doc/README as needed.
- Always sanity-check execution costs: keep lazy imports intact, avoid unnecessary `Path.resolve()` churn in hot paths, and document trade-offs if a feature must slow things down.
- Keep frontend localisation healthy: UI copy lives under `packages/recozik-webui/src/i18n`, so every new label/helptext needs translations for all supported locales plus any accessibility notes (aria labels, live regions). Run `npm run lint` after changing text or locale files.

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

- Sessions: UI uses password login (`/auth/login`) issuing HttpOnly cookies (`recozik_session` + `recozik_refresh`). Backends still accept `X-API-Token` for CLI/automation. Static tokens: `RECOZIK_WEB_ADMIN_TOKEN`, optional `RECOZIK_WEB_READONLY_TOKEN`. Dynamic tokens stored in SQLite (`auth.db`).
- `ServiceFeature` values: `identify`, `identify_batch`, `rename`, `audd`, `musicbrainz_enrich`. Tokens carry an `allowed_features` set; `TokenAccessPolicy` rejects unsupported calls with 403.
- Quotas use `QuotaScope` keys (`acoustid_lookup`, `musicbrainz_enrich`, `audd_standard_lookup`, `audd_enterprise_lookup`). `InMemoryQuotaPolicy` + optional persistent policy (`persistent_quota.py`) enforce per-user limits and raise 429.

### Backend settings (`RECOZIK_WEB_*` prefix)

All backend environment variables inherit the `RECOZIK_WEB_` prefix defined in `WebSettings`. Examples:

| Variable                                                                                                                         | Meaning (defaults in `WebSettings`)                                         |
| -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `RECOZIK_WEB_ADMIN_TOKEN`, `RECOZIK_WEB_READONLY_TOKEN`                                                                          | Default admin/readonly API tokens (set strong random values in production). |
| `RECOZIK_WEB_ACOUSTID_API_KEY`, `RECOZIK_WEB_AUDD_TOKEN`, `RECOZIK_WEB_AUDD_ENDPOINT_STANDARD/ENTERPRISE`                        | Credentials forwarded to `identify_track`.                                  |
| `RECOZIK_WEB_BASE_MEDIA_ROOT`, `RECOZIK_WEB_UPLOAD_SUBDIR`, `RECOZIK_WEB_MAX_UPLOAD_MB`, `RECOZIK_WEB_ALLOWED_UPLOAD_EXTENSIONS` | File-system sandbox + upload limits.                                        |
| `RECOZIK_WEB_CACHE_ENABLED`, `RECOZIK_WEB_CACHE_TTL_HOURS`                                                                       | Server-side LookupCache options.                                            |
| `RECOZIK_WEB_MUSICBRAINZ_*`                                                                                                      | Toggle + user-agent metadata for enrichment.                                |
| `RECOZIK_WEB_JOBS_DB_FILENAME`, `RECOZIK_WEB_AUTH_DB_FILENAME`, `RECOZIK_WEB_JOBS_DATABASE_URL`, `RECOZIK_WEB_AUTH_DATABASE_URL` | SQLModel persistence paths/URLs.                                            |
| `RECOZIK_WEB_CORS_ENABLED`, `RECOZIK_WEB_CORS_ORIGINS`, `RECOZIK_WEB_SECURITY_*`, `RECOZIK_WEB_RATE_LIMIT_*`                     | HTTP hardening (CORS, HSTS, CSP, throttling).                               |

See `packages/recozik-web/src/recozik_web/config.py` for the exhaustive list.

## Web UI Overview (packages/recozik-webui)

- **Architecture**: Next.js (App Router) with localized routes (`/[locale]`). `app/page.tsx` redirects based on `Accept-Language`; `LanguageSwitcher` lets users toggle manually.
- **Job upload**: `JobUploader` posts a multipart form via `uploadAction`, forwarding `metadata_fallback`, `prefer_audd`, `force_audd_enterprise`. On success, it pushes the queued job into the dashboard state.
- **Job monitoring**: `JobList` combines WebSocket updates (`createJobWebSocket`) with periodic polling using `fetchJobDetail`. Live regions/table semantics keep the view screen-reader friendly.
- **Admin tooling**: `AdminTokenManager` uses `/admin/tokens` to list/create tokens (roles, features, quota scopes). Only shows up when `whoami.roles` contains `admin`.
- **API client**: `src/lib/api.ts` centralizes calls (`fetchWhoami`, `uploadJob`, `fetchJobs`, `createToken`) and enforces the `X-API-Token` header. `NEXT_PUBLIC_RECOZIK_API_BASE` must point to the backend (default `/api`).
- **Accessibility**: Keep `SkipLink`, `aria-live` regions, focus management, and translation keys intact when modifying layouts.
- **Localization**: Strings live in `packages/recozik-webui/src/i18n`. Add new keys to every locale file and verify both English and French output before shipping. Prefer structured message IDs instead of inline literals.
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

## Security & External Agent Notes

- Run `uv run python scripts/token_audit.py --database-url <url>` whenever the auth DB schema changes or before releases to ensure all stored tokens use hashed format (see `DEPLOYMENT_SECURITY.md` for the full checklist).
- Backend environments must honour `RECOZIK_WEB_SECURITY_*`, rate-limit knobs, and TLS guidance in `DEPLOYMENT_SECURITY.md`. Document any deviation directly in `docs/deploy-backend*.md`.
- Autonomous agents (Jules, Copilot, Codex Web…) work in isolated Linux VMs; spell out the system prep in `GEMINI.md` so they can bootstrap without human intervention. Include at minimum:
  - Debian/Ubuntu packages derived from `docker/backend.Dockerfile`:
    ```bash
    sudo apt-get update && sudo apt-get install -y \
      curl libsndfile1 ffmpeg libchromaprint1 libchromaprint-tools gettext
    ```
    Add other binary deps (e.g. `msgfmt`, `ffprobe`) if tests require them.
  - Project bootstrap commands: `uv sync --all-groups`, `uv run pytest`, `uv run ruff check --fix`, `uv run mypy`, `npm install`, `npm run lint`, `npm run build`.
  - Node.js ≥20 (frontend) and Python 3.11 (backend) availability; document how to install them when the base image lacks the right versions (e.g. `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -` followed by `sudo apt-get install -y nodejs`).
  - Any additional secrets or environment variables required to run integration tests (dummy API tokens, local `.env` expectations) so Jules can inject them via its secure vault.

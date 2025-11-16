# Repository Guidelines

## Project Structure & Module Organization

- `src/recozik/cli.py` – Typer app registration + backward-compatible shims (exposes lazy symbols such as `compute_fingerprint`, `LookupCache`, completion helpers).
- `src/recozik/commands/` – Feature-focused command modules (`inspect`, `fingerprint`, `identify`, `identify_batch`, `rename`, `config`, `completion`).
- `src/recozik/cli_support/` – Thin re-export layer pointing to the shared service helpers (locale resolution, path helpers, metadata/log formatting, prompts, lazy dependency loaders).
- `packages/recozik-services/src/recozik_services/` – Service layer consumed by the CLI and future GUIs (identify, batch identify, rename runners plus callback/ prompt protocols). Implement new behaviour here first so every frontend stays in sync.
- `packages/recozik-services/src/recozik_services/security.py` – Auth/authorization/quota protocols + default policies every frontend must wire up.
- `packages/recozik-web/src/recozik_web/` – FastAPI backend exposing the shared services over HTTP (token auth, quota policy wiring, filesystem-based identify endpoint, async upload/jobs API + polling/WebSocket hooks).
- `packages/recozik-webui/` – Next.js dashboard that consumes the HTTP API (token login, upload panel, job monitoring, admin token management). Keep accessibility (screen readers, keyboard navigation) in mind when adding components.
- `packages/recozik-core/src/recozik_core/` – Core libraries (`fingerprint.py`, `cache.py`, `config.py`, `audd.py`, `i18n.py`, locales) consumed by the CLI and future GUIs.
- `tests/` – Pytest suites mirroring CLI features and performance guards (includes `test_cli_import_time.py`).
- `README.md` – User-facing quick start; AGENTS should cross-check when updating commands.
- `dist/`, `build/`, and `.venv/` are generated artifacts; never commit them.

## Build, Test, and Development Commands

- `uv sync --all-groups` – Install runtime + dev dependency groups defined in `pyproject.toml`.
- `uv run recozik …` – Execute CLI commands (e.g., `uv run recozik identify sample.flac`).
- `uv run ruff check --fix` – Run Ruff with automatic fixes (must pass before committing).
- `uv run ruff format` – Apply Ruff formatter to keep code style consistent.
- `uv run mypy` – Run static type checks (entire `src/recozik` + `recozik_core` must stay clean).
- `uv run pytest` – Run the full automated test suite.
- `cd packages/recozik-webui && npm install && npm run lint` – Install frontend dependencies and run Next.js lint/type checks (required before touching the dashboard).

> **Permission reminder:** Always request elevated permissions before running any `uv` command (`uv run …`, `uv sync …`, etc.).

- `uv build` – Produce wheel + sdist for validation before releases.

## Coding Style & Naming Conventions

- Python 3.10–3.13, 4-space indentation, type hints encouraged. Python 3.14 remains experimental until upstream (librosa/numba) ships stable wheels.
- CLI options use kebab-case (e.g., `--log-format`); internal functions use snake_case.
- Keep Typer command logic inside the relevant module under `src/recozik/commands/`; `cli.py` should only register commands and surface compatibility wrappers.
- When adding or modifying core behaviour (identify/batch/rename workflows), write it under `packages/recozik-services` first, then add the thin CLI glue that builds requests and forwards callbacks/prompts.
- When touching completion logic, update both `src/recozik/commands/completion.py` and the wrapper wiring in `cli.py` so tests that monkeypatch `recozik.cli` continue to work.
- Sanitize filenames using `_sanitize_filename`; reuse helpers instead of ad-hoc logic.
- Route every user-facing string through `recozik_core.i18n._` using an English msgid. Update the relevant `.po` file under `packages/recozik-core/src/recozik_core/locales/<lang>/LC_MESSAGES/` and recompile the `.mo` file when strings change.
- Store AcoustID/AudD secrets via `recozik_core.secrets` (system keyring); never write them in plaintext config files.
- Honor locale precedence in this order: CLI option `--locale` > environment variable `RECOZIK_LOCALE` > config `[general].locale` > system locale.
- Favor readability-first helpers. Prefer `cli_support.options.resolve_option` for CLI/config reconciliation, `cli_support.audd_helpers.get_audd_support` for AudD fallbacks, and other shared utilities so new code stays maintainable and avoids redundant, slow logic.

## Testing Guidelines

- Framework: Pytest (`tests/` modules prefixed `test_`).
- Cover new CLI flags with focused tests using `CliRunner` and temp directories.
- When adding dependencies, verify `uv run pytest` passes locally and in dry-run modes (`--dry-run`, `--json`).
- Prefer deterministic fixtures; avoid network calls in tests.
- Keep the import-time guard (`tests/test_cli_import_time.py`) passing; if you introduce heavier startup logic, adjust the threshold deliberately and document the change.
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
- When adding new commands, create a dedicated module under `src/recozik/commands/`, surface any required backward-compatible aliases via `cli.py`, and extend `AGENTS.md`/README as needed.
- Always sanity-check execution costs: keep lazy imports intact, avoid unnecessary `Path.resolve()` churn in hot paths, and document any trade-offs if a feature must slow things down.

# Repository Guidelines

## Project Structure & Module Organization
- `src/recozik/` – Typer CLI entry points (`cli.py`), fingerprint utilities (`fingerprint.py`), caching (`cache.py`), and config helpers (`config.py`).
- `tests/` – Pytest suites mirroring CLI features: completion, identify, batch, rename.
- `README.md` – User-facing quick start; AGENTS should cross-check when updating commands.
- `dist/`, `build/`, and `.venv/` are generated artifacts; never commit them.

## Build, Test, and Development Commands
- `uv sync --all-groups` – Install runtime + dev dependency groups defined in `pyproject.toml`.
- `uv run recozik …` – Execute CLI commands (e.g., `uv run recozik identify sample.flac`).
- `uv run pytest` – Run the full automated test suite.
- `uv build` – Produce wheel + sdist for validation before releases.

## Coding Style & Naming Conventions
- Python 3.10–3.12, 4-space indentation, type hints encouraged.
- CLI options use kebab-case (e.g., `--log-format`); internal functions use snake_case.
- Keep Typer command functions in `cli.py`; supporting utilities go in dedicated modules.
- Sanitize filenames using `_sanitize_filename`; reuse helpers instead of ad-hoc logic.

## Testing Guidelines
- Framework: Pytest (`tests/` modules prefixed `test_`).
- Cover new CLI flags with focused tests using `CliRunner` and temp directories.
- When adding dependencies, verify `uv run pytest` passes locally and in dry-run modes (`--dry-run`, `--json`).
- Prefer deterministic fixtures; avoid network calls in tests.

## Commit & Pull Request Guidelines
- Commit messages follow imperative tone (e.g., “Add interactive selection to rename-from-log”) and include `-s` for signed-off compliance.
- Each commit should keep tests passing; squash only when history becomes noisy.
- Pull requests should summarize behavior changes, list new CLI flags, and note docs/tests touched. Include sample commands or log snippets when relevant.
- Link to issues or TODO comments when closing tasks; attach screenshots only if UI output changes (e.g., help text).

## Agent-Specific Tips
- Always run `git status` before exiting to ensure a clean tree.
- If GPG signing blocks commits, rerun with elevated permissions (`with_escalated_permissions: true`).
- Clean the uv cache (`rm -f ~/.cache/uv/sdists-v9/.git`) if CLI commands fail with permission errors.

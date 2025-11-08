# Gemini Code Assistant Context

This document summarizes the repository context for code assistants working on `recozik`.

## Project Overview

`recozik` is a command-line tool written in Python for music recognition. It generates audio fingerprints using Chromaprint, queries the AcoustID service to identify tracks, and provides utilities to batch-process and rename audio files based on the retrieved metadata.

The CLI is built using the Typer framework. It also includes an optional fallback to the AudD music recognition API. The project emphasizes a clean, terminal-first user experience and includes internationalization support (English and French).

### Key Technologies

- **Language:** Python (3.10-3.13; 3.14 pending upstream wheel support)
- **CLI Framework:** Typer
- **Dependency Management:** uv
- **Code Style:** Ruff for formatting and linting
- **Testing:** Pytest
- **Core Libraries:** `librosa`, `soundfile`, `mutagen`, `pyacoustid`, `requests`

### Code Structure

- `src/recozik/cli.py`: The main Typer application entry point where all commands are registered.
- `src/recozik/commands/`: Contains the implementation for each CLI command (e.g., `inspect`, `identify`, `rename-from-log`).
- `src/recozik/cli_support/`: Shared helper modules for tasks like configuration, locale handling, and file system operations.
- `packages/recozik-core/src/recozik_core/locales/`: Contains translation files (`.po`, `.mo`) for internationalization using gettext.
- `tests/`: Contains the pytest test suite.
- `scripts/`: Utility scripts, such as for compiling translations.

## Building and Running

The project uses `uv` to manage dependencies and virtual environments.

- **Install all dependencies (runtime and dev):**

  ```bash
  uv sync --all-groups
  ```

- **Run a CLI command:**

  ```bash
  uv run recozik <command> [OPTIONS]
  ```

  For example:

  ```bash
  uv run recozik inspect "path/to/my/song.mp3"
  ```

- **Build the project (wheel and sdist):**
  ```bash
  uv build
  ```

## Development Conventions

- **Formatting:** Code is formatted using Ruff.

  ```bash
  uv run ruff format
  ```

- **Linting:** Ruff is also used for linting. The CI pipeline runs `pre-commit` to enforce this.

  ```bash
  uv run ruff check --fix
  ```

- **Testing:** The test suite is run with pytest. Tests are located in the `tests/` directory and use fixtures defined in `tests/conftest.py`. The test environment is automatically configured to use the English locale.

  ```bash
  uv run pytest
  ```

- **Typing:** Mypy now covers the entire `src/recozik` tree (plus `recozik_core`). Always run `uv run mypy` before sending changes and keep any new modules within those checked paths.

- **Import-time guard:** `tests/test_cli_import_time.py` enforces that loading `recozik.cli` stays under 0.5 s. Run `uv run python scripts/measure_import_time.py` (or the here-doc from the README) before adding heavy imports.

- **Commit Messages:** Commits should use the imperative mood (e.g., "Add feature for X") and be signed off (`git commit -s`).

- **Internationalization (i18n):** User-facing strings are wrapped in a `_()` function for gettext. To update translations:
  1.  Edit the `.po` files in `packages/recozik-core/src/recozik_core/locales/<lang>/LC_MESSAGES/`.
  2.  Compile the messages into `.mo` files using the provided script:
      ```bash
      uv run python scripts/compile_translations.py
      ```

- **Configuration:** Application configuration (e.g., API keys) is stored in `config.toml` in a platform-specific user config directory. The `recozik config` subcommand group provides an interface for managing these settings.

## Expectations for Gemini Contributions

- Keep additions easy to read and maintain. Lean on existing helpers—most CLI/config reconciliation now lives in `src/recozik/cli_support/options.py:resolve_option`, and AudD fallbacks should go through `cli_support/audd_helpers.py:get_audd_support`.
- Preserve fast startup and execution paths. Avoid redundant filesystem resolution or eager imports; prefer lazy loading patterns already in the codebase.
- When you introduce new logic, call out performance implications in the PR description and add targeted tests if the change alters behaviour or timing.

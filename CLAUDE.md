# CLAUDE.md

This file provides guidance for working with code in this repository when using the Claude coding environment.

## Project Overview

Recozik is a terminal-first audio fingerprinting tool that computes Chromaprint fingerprints, queries the AcoustID service, and helps batch-identify or rename audio files. It's a Python CLI application built with Typer, currently in public alpha phase.

**Important**: Python 3.10-3.13 verified. Python 3.14 is under evaluation while we wait for stable librosa/numba wheels.

## Essential Commands

### Environment Setup

```bash
# Install uv package manager first
pip install uv

# Create virtual environment and install all dependencies
uv sync --all-groups
```

### Running the CLI

```bash
# All CLI commands must be prefixed with 'uv run'
uv run recozik <command>

# Examples
uv run recozik inspect path/to/file.wav
uv run recozik identify path/to/file.wav
uv run recozik identify-batch music/ --recursive
```

### Code Quality

```bash
# Format code (auto-fix)
uv run ruff format

# Lint code (with auto-fixes where safe)
uv run ruff check --fix

# Always run both before committing
```

### Testing

```bash
# Run full test suite
uv run pytest

# Run specific test file
uv run pytest tests/test_fingerprint_lookup.py

# Run specific test
uv run pytest tests/test_fingerprint_lookup.py::test_name

# Run with verbose output
uv run pytest -v

# Run with coverage (if configured)
uv run pytest --cov=recozik
```

### Internationalization

```bash
# Compile translations after editing .po files
uv run python scripts/compile_translations.py
```

### Build

```bash
# Build wheel and sdist for release validation
uv build
```

## Architecture

### Module Organization

The codebase is structured for **fast import times** and **maintainability**:

- **`src/recozik/cli.py`**: Typer application entry point. Registers all commands and subcommands. Uses lazy loading for heavy dependencies to keep import times fast.
- **`src/recozik/commands/`**: Individual command implementations:
  - `inspect.py`: Extract basic audio metadata
  - `fingerprint.py`: Generate Chromaprint fingerprints
  - `identify.py`: Single-file AcoustID lookup
  - `identify_batch.py`: Batch processing with caching
  - `rename.py`: Apply renaming from JSONL logs
  - `config.py`: Configuration management (API keys, settings)
  - `completion.py`: Shell completion script management
- **`src/recozik/cli_support/`**: Shared utilities for commands:
  - `locale.py`: i18n locale detection and management
  - `metadata.py`: Audio metadata extraction (mutagen wrapper)
  - `paths.py`: Filesystem utilities and path handling
  - `logs.py`: Logging helpers for batch operations
  - `prompts.py`: Interactive prompts for CLI
  - `deps.py`: **Lazy dependency loaders** to defer expensive imports

### Core Modules

- **`fingerprint.py`**: Core fingerprinting logic using pyacoustid/Chromaprint. Returns `FingerprintResult`, `AcoustIDMatch` objects. Handles merge logic for deduplicating AcoustID responses.
- **`audd.py`**: Optional AudD fallback service integration. Converts AudD responses to `AcoustIDMatch` format for consistency.
- **`cache.py`**: JSON-backed LookupCache with TTL support for AcoustID results.
- **`config.py`**: TOML configuration management. Default paths via `platformdirs`. Supports `RECOZIK_CONFIG_FILE` environment variable override.
- **`i18n.py`**: GNU gettext integration with automatic system locale detection. Patches Typer/Click modules to translate built-in strings.

### Key Design Patterns

1. **Lazy Loading**: Heavy imports (librosa, pyacoustid) are deferred via `cli_support/deps.py` to keep CLI startup fast. The `__getattr__` pattern in `cli.py` provides backward-compatible access.

2. **Deduplication**: `fingerprint.py:_merge_matches()` merges duplicate AcoustID recordings by `recording_id`, combining metadata and releases from multiple result entries.

3. **Unified Match Format**: AudD results are converted to `AcoustIDMatch` objects via `audd.py:AudDMatch.to_acoustid_match()` to provide a consistent interface regardless of source.

4. **Configuration Precedence**: For all settings (locale, API keys, cache):
   - CLI option (highest priority)
   - Environment variable
   - Config file value
   - Default value (lowest priority)

5. **Locale Management**: Tests force English locale via `conftest.py:force_english_locale` autouse fixture to ensure predictable assertion strings. Override `RECOZIK_LOCALE` in individual tests to check translations.

## Testing Guidelines

- Tests automatically use English locale via `conftest.py` autouse fixture
- To test translations, override `RECOZIK_LOCALE` environment variable in the test
- Use `cli_runner` fixture from `conftest.py` for Typer CLI testing
- Use `rename_env` fixture for rename command tests (provides helper methods)
- Mock external services (AcoustID, AudD) in tests to avoid network calls

## Claude Coding Checklist

- **Clarity first.** New code should be easy to scan. Reuse shared helpers such as `cli_support.options.resolve_option` and `cli_support.audd_helpers.get_audd_support` instead of duplicating parameter or AudD logic.
- **Think about runtime.** Maintain lazy import patterns and avoid heavy `Path.resolve()` loops in hot paths. If a feature introduces measurable overhead, justify it and add coverage.
- **Leave the trail tidy.** Update docs/tests alongside behaviour changes, and explain notable trade-offs in the PR summary so humans can follow your reasoning.

## Configuration Management

Configuration is loaded from TOML files with this structure:

```toml
[acoustid]
api_key = "your_key"

[audd]
api_token = "optional_token"

[cache]
enabled = true
ttl_hours = 24

[output]
template = "{artist} - {title}"

[metadata]
fallback = true

[logging]
format = "text"  # or "jsonl"
absolute_paths = false

[rename]
log_cleanup = "ask"  # or "always", "never"

[general]
locale = "en"  # or "fr", "fr_FR", etc.
```

Default config paths (via `platformdirs`):

- Linux/macOS: `~/.config/recozik/config.toml`
- Windows: `%APPDATA%\recozik\config.toml`

Override with `RECOZIK_CONFIG_FILE` environment variable.

## Important Notes

- **Never commit API keys**: The `config.toml` file should never be committed. API keys are user-specific secrets.
- **AudD is opt-in**: AudD fallback requires users to provide their own token and accept AudD's terms. Always display "Powered by AudD Music (fallback)" attribution when used.
- **Chromaprint dependency**: The CLI requires `fpcalc` (Chromaprint) to be installed and on PATH. Tests may mock this if `fpcalc` is unavailable.
- **Translation workflow**: After modifying `.po` files, always run `python scripts/compile_translations.py` to regenerate `.mo` binaries before testing.
- **Commit conventions**: Use imperative commit messages and sign commits with `-s` (Developer Certificate of Origin).

## Common Development Tasks

### Adding a new CLI command

1. Create command implementation in `src/recozik/commands/your_command.py`
2. Import and register in `src/recozik/cli.py` using `@app.command()` decorator
3. Add tests in `tests/test_cli_your_command.py`
4. Wrap user-facing strings with `_()` from `recozik.i18n`
5. Update translation catalogs if needed

### Adding internationalization

1. Wrap strings with `_()` from `recozik.i18n`
2. Update `.po` files in `src/recozik/locales/*/LC_MESSAGES/`
3. Run `python scripts/compile_translations.py`
4. Test with `RECOZIK_LOCALE=fr uv run recozik ...`

### Modifying fingerprinting logic

- Edit `src/recozik/fingerprint.py`
- Note: `_normalize_fingerprint_output()` handles version differences in pyacoustid (return order varies)
- Deduplication logic in `_merge_matches()` is critical for clean batch results
- Always return consistent data structures (`FingerprintResult`, `AcoustIDMatch`)

### Working with the cache

- Cache implementation in `src/recozik/cache.py`
- Keys are `fingerprint:rounded_duration`
- TTL enforcement happens at read time (stale entries are ignored)
- Call `cache.save()` explicitly to persist (not automatic)

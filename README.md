# recozik

Recozik is a terminal-first tool that computes [Chromaprint](https://acoustid.org/chromaprint) fingerprints, queries the AcoustID service, and helps you batch-identify or rename audio files. The CLI keeps output screen-reader friendly and now ships with built-in localisation.

- [Project summary](#project-summary)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuring AcoustID](#configuring-acoustid)
- [Usage examples](#usage-examples)
- [Internationalisation](#internationalisation)
- [Development workflow](#development-workflow)
- [Testing](#testing)
- [Contributing](#contributing)

> 🇫🇷 Besoin de la documentation en français ? Consultez [README.fr.md](README.fr.md).

## Project summary

| Command                   | Purpose                                                                       |
| ------------------------- | ----------------------------------------------------------------------------- |
| `recozik inspect`         | Print basic metadata about an audio file.                                     |
| `recozik fingerprint`     | Generate Chromaprint / `fpcalc` fingerprints.                                 |
| `recozik identify`        | Look up a single file against the AcoustID API.                               |
| `recozik identify-batch`  | Process an entire directory tree, cache results, and emit text or JSONL logs. |
| `recozik rename-from-log` | Apply suggestions produced by the batch command and organise your library.    |
| `recozik completion ...`  | Manage shell completion scripts for Bash, Zsh, Fish, or PowerShell.           |
| `recozik config ...`      | Persist and inspect local configuration (AcoustID key, cache, templates…).    |

## Project status

Recozik is currently in a public alpha phase. Interfaces and outputs may change without notice until the 1.0 release. Track changes in [CHANGELOG.md](CHANGELOG.md) and in the GitHub Releases page.

## Prerequisites

- Python 3.10, 3.11, or 3.12 (Chromaprint/librosa does not yet support 3.13).
- [Chromaprint](https://acoustid.org/chromaprint) binaries; the CLI relies on the `fpcalc` executable.
  - Linux: install the `chromaprint`/`libchromaprint-tools` package from your distribution.
  - Windows: download the Chromaprint zip, extract it, and add the folder with `fpcalc.exe` to `PATH`.
- Optional build tooling (`msgfmt`) if you modify translations.

## Installation

### From PyPI (after the first public release)

```bash
pip install recozik
```

### From source with uv

The project uses [uv](https://docs.astral.sh/uv/) to manage environments:

```bash
pip install uv
uv sync --all-groups
```

The command above creates a project-local virtual environment and installs runtime + development dependencies defined in `pyproject.toml`.

## Configuring AcoustID

1. Create an account on <https://acoustid.org> and generate an API key (`Account → Create API Key`).
2. Persist the key with the CLI (will prompt if missing):
   ```bash
   uv run recozik config set-key
   ```
   Default configuration paths:
   - Linux/macOS: `~/.config/recozik/config.toml`
   - Windows: `%APPDATA%\recozik\config.toml`
3. Inspect the current configuration:
   ```bash
   uv run recozik config show
   ```

The config file supports additional settings (cache TTL, output templates, logging mode). See the [sample layout](#development-workflow) below.
Never commit the generated `config.toml` or share your personal AcoustID key; treat it like any other secret credential.

## Usage examples

Inspect a file:

```bash
uv run recozik inspect path/to/file.wav
```

Generate a fingerprint and export it as JSON:

```bash
uv run recozik fingerprint path/to/file.wav --output fingerprint.json
```

Use `--show-fingerprint` to print the raw fingerprint (note: very long string).

Identify a single track via AcoustID:

```bash
uv run recozik identify path/to/file.wav --limit 5 --json
```

Batch-identify a folder and write results to JSONL:

```bash
uv run recozik identify-batch music/ --recursive --log-format jsonl --log-file logs/recozik.jsonl
```

Useful options: `--pattern`, `--ext`, `--best-only`, `--refresh`, `--template "{artist} - {title}"`.

Rename files using a previous batch log (dry-run by default):

```bash
uv run recozik rename-from-log logs/recozik.jsonl --root music/ --apply
```

Add `--interactive` to pick a suggestion manually, `--metadata-fallback` to use embedded tags when AcoustID fails, and `--backup-dir` to keep a copy of originals.

Install shell completion:

```bash
uv run recozik completion install --shell bash
```

Or inspect the generated script without installing it:

```bash
uv run recozik completion install --shell zsh --no-write
```

## Internationalisation

Recozik uses GNU gettext. English msgids live in the code; translations ship in `src/recozik/locales/`.

Locale precedence:

1. CLI option `--locale` (highest priority)
2. Environment variable `RECOZIK_LOCALE`
3. Config value `[general].locale` in `config.toml`
4. System locale (falls back to English when no catalogue matches)

Updating translations:

1. Modify the relevant `.po` file (e.g. `src/recozik/locales/fr/LC_MESSAGES/recozik.po`).
2. Run `python scripts/compile_translations.py` to regenerate `.mo` binaries.
3. Execute tests in English (default) and in the target locale if you added coverage.
4. See [TRANSLATION.md](TRANSLATION.md) for the full workflow and tips.

## Development workflow

Common commands (always request permission before running `uv …` as per the repo guidelines):

```bash
uv sync --all-groups            # install runtime + dev dependencies
uv run recozik …                # execute any CLI command
uv run ruff format              # auto-format
uv run ruff check --fix         # lint and apply safe fixes
uv run pytest                   # run the full test suite
uv run recozik completion …     # manage shell completion scripts
uv build                        # build wheel + sdist for release validation
```

Sample configuration (`config.toml`):

```toml
[acoustid]
api_key = "your_api_key"

[cache]
enabled = true
ttl_hours = 24

[output]
template = "{artist} - {title}"

[metadata]
fallback = true

[logging]
format = "text"
absolute_paths = false

[general]
locale = "en"
```

## Code structure

- `src/recozik/cli.py` registers the Typer application and exposes backwards-compatible aliases for tests and integrations.
- `src/recozik/commands/` contains the command implementations split by feature (`inspect`, `identify`, `identify-batch`, `rename-from-log`, `config`, `completion`).
- `src/recozik/cli_support/` provides shared helpers (locale handling, filesystem utilities, metadata parsing, logging helpers, and lazy dependency loaders).

This layout keeps the import-time fast while making the command code easier to navigate and test.

## Testing

```bash
uv run ruff format
uv run ruff check --fix
uv run pytest
```

A pytest fixture (`tests/conftest.py`) forces the English locale during tests, so assertions stay predictable. Override `RECOZIK_LOCALE` inside a test when you want to check translated output.

## Contributing

- Follow the linting/testing flow above before committing.
- Use imperative, signed-off commit messages (`git commit -s`).
- When adding user-facing strings, wrap them with `_()` from `recozik.i18n` and update the translation catalogues.
- See [TRANSLATION.md](TRANSLATION.md) for localisation details.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow, the [Code of Conduct](CODE_OF_CONDUCT.md), and the [security policy](SECURITY.md) before opening an issue or pull request.

Issues and pull requests are welcome—thank you for helping to improve Recozik!

> _Transparency:_ this project was implemented with the assistance of OpenAI Codex.

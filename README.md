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
| `recozik identify`        | Look up a single file against the AcoustID API (AudD fallback optional).      |
| `recozik identify-batch`  | Process an entire directory tree, cache results, and emit text or JSONL logs. |
| `recozik rename-from-log` | Apply suggestions produced by the batch command and organise your library.    |
| `recozik completion ...`  | Manage shell completion scripts for Bash, Zsh, Fish, or PowerShell.           |
| `recozik config ...`      | Persist and inspect local configuration (AcoustID key, cache, templates…).    |

## Project status

Recozik is currently in a public alpha phase. Interfaces and outputs may change without notice until the 1.0 release. Track changes in [CHANGELOG.md](CHANGELOG.md) and in the GitHub Releases page.

## Prerequisites

- Python 3.10 through 3.13 (librosa 0.11+ supports 3.13; Recozik bundles the `standard-*`/`audioop-lts` backfill packages automatically).
- [Chromaprint](https://acoustid.org/chromaprint) binaries; the CLI relies on the `fpcalc` executable.
  - Linux: install the `chromaprint`/`libchromaprint-tools` package from your distribution.
  - Windows: download the Chromaprint zip, extract it, and add the folder with `fpcalc.exe` to `PATH`.
- Optional build tooling (`msgfmt`) if you modify translations.
- Optional FFmpeg CLI + `pip install recozik[ffmpeg-support]` to let the AudD fallback and `recozik inspect` decode formats unsupported by libsndfile (for example large WMA files).

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
   - Override: set the environment variable `RECOZIK_CONFIG_FILE=/path/to/config.toml` before running the CLI.
3. Inspect the current configuration:
   ```bash
   uv run recozik config show
   ```

The config file supports additional settings (cache TTL, output templates, logging mode). See the [sample layout](#development-workflow) below.
Never commit the generated `config.toml` or share your personal AcoustID key; treat it like any other secret credential.

## Optional AudD fallback

Recozik can also call the [AudD Music Recognition API](https://audd.io) when AcoustID does not return a match. The integration is strictly opt-in:

1. Create an AudD account and generate an API token. Each user of Recozik needs to supply **their own** token and remains responsible for AudD’s usage limits and terms (the public “API Test License Agreement” only covers 90 days of evaluation).
2. Store the token with `uv run recozik config set-audd-token` (remove it later with `uv run recozik config set-audd-token --clear`), export it via the `AUDD_API_TOKEN` environment variable, or pass it per command with `--audd-token`.
3. When AudD recognises a track, the JSON output still exposes a `source` field (`acoustid` or `audd`) and the batch logs append `Source: AudD.` so you know where every suggestion came from—no console banner required.
4. For formats that libsndfile cannot decode (e.g. WMA > 10 MB), install `ffmpeg` and the optional extra `pip install recozik[ffmpeg-support]`. Recozik will retry the snippet extraction through FFmpeg before giving up on AudD.

By default the CLI prints the lookup strategy to `stderr` (for example, “Identification strategy: AcoustID first, AudD fallback.”). Toggle it per run with `--announce-source/--silent-source`, or persist the setting through `announce_source` configuration keys.

On a per-run basis you can disable the integration entirely with `--no-audd`, or prioritise AudD over AcoustID with `--prefer-audd`. Remember that the two commands read separate configuration sections: `identify` pulls defaults from `[identify]`, while `identify-batch` only honours values defined under `[identify_batch]` (keys: `audd_enabled`, `prefer_audd`, `announce_source`).

Tip: keep the token disabled in shared scripts unless every user has accepted AudD’s terms and provided their own credentials.

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

By default the batch command scans files with `.mp3`, `.flac`, `.wav`, `.ogg`, `.m4a`, `.aac`, `.opus`, and `.wma` extensions. Add `--ext` flags to override the selection.

Useful options: `--pattern`, `--ext`, `--best-only`, `--refresh`, `--template "{artist} - {title}"`.

Rename files using a previous batch log (dry-run by default):

```bash
uv run recozik rename-from-log logs/recozik.jsonl --root music/ --apply
```

Add `--interactive` to pick a suggestion manually, `--metadata-fallback` to use embedded tags when AcoustID fails, `--backup-dir` to keep a copy of originals, and `--keep-template-duplicates` when you want to review proposals that render to the same filename.
The rename workflow also honours configuration keys under `[rename]`:

- `default_mode`: selects the implicit behaviour for `--dry-run/--apply` (`dry-run` by default, set to `apply` to skip the preview step).
- `interactive`: toggles interactive selection without passing `--interactive` (defaults to `false`).
- `confirm_each`: requests confirmation before each rename when set to `true` (defaults to `false`).
- `conflict_strategy`: default collision behaviour (`append`, `skip`, or `overwrite`; default `append`).
- `metadata_confirm`: controls whether metadata fallbacks require confirmation (defaults to `true`).
- `deduplicate_template`: collapses proposals that would generate the same target filename when `true` (default). Override with the CLI flag `--deduplicate-template/--keep-template-duplicates`.
- `log_cleanup`: controls whether the JSONL log is deleted after a successful `--apply` run (`ask`, `always`, or `never`; default `ask`). You can override it per command with `--log-cleanup`.
- `require_template_fields`: skips matches that are missing values referenced by the template (defaults to `false`). Toggle it per run with `--require-template-fields/--allow-missing-template-fields`.

Two optional sections also tune the identification commands:

- `[identify]` sets the default limit (`3`), JSON output mode (`false`), cache refresh behaviour (`false`), and the AudD integration defaults (`audd_enabled = true`, `prefer_audd = false`) for the single-file `identify` command only.
- `[identify_batch]` controls the per-file result limit (`3`), `best_only` mode (`false`), recursion (`false`), log destination (unset → `recozik-batch.log` in the current directory), and the AudD defaults (`audd_enabled = true`, `prefer_audd = false`) exclusively for `identify-batch`.

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

[audd]
# api_token = "your_audd_token"

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

# Settings in [identify] only affect the single-file `identify` command.
[identify]
limit = 3
json = false
refresh = false
audd_enabled = true
prefer_audd = false
announce_source = true

# The batch command reads only values defined under [identify_batch]; nothing leaks
# over from [identify].
[identify_batch]
limit = 3
best_only = false
recursive = false
# log_file = "recozik-batch.log"
audd_enabled = true
prefer_audd = false
announce_source = true

[rename]
# default_mode = "dry-run"
# interactive = false
# confirm_each = false
conflict_strategy = "append"
metadata_confirm = true
log_cleanup = "ask"
require_template_fields = false
deduplicate_template = true

[general]
locale = "en"
```

## Configuration reference

Each command reads only the section that matches its name. Values under `[identify]` never fall back to `[identify_batch]`, and the batch command does not reuse single-file defaults. Duplicate keys (for example `audd_enabled`, `prefer_audd`, `announce_source`, or `limit`) must therefore be set in both sections if you want the same behaviour across commands.

| Scope                          | Name                      | Type / Values                     | Default                     | Description                                                           | How to configure                                                                       |
| ------------------------------ | ------------------------- | --------------------------------- | --------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Config file `[acoustid]`       | `api_key`                 | string                            | unset                       | AcoustID client key used for lookups.                                 | `uv run recozik config set-key` or edit `config.toml`.                                 |
| Config file `[audd]`           | `api_token`               | string                            | unset                       | AudD fallback token when AcoustID has no match.                       | `uv run recozik config set-audd-token` or edit `config.toml`.                          |
| Config file `[cache]`          | `enabled`                 | boolean                           | `true`                      | Enables the local lookup cache.                                       | Edit `config.toml`.                                                                    |
| Config file `[cache]`          | `ttl_hours`               | integer                           | `24`                        | Cache time-to-live in hours (minimum 1).                              | Edit `config.toml`.                                                                    |
| Config file `[output]`         | `template`                | string                            | `"{artist} - {title}"`      | Default template for identify/rename output.                          | Edit `config.toml` or pass `--template`.                                               |
| Config file `[metadata]`       | `fallback`                | boolean                           | `true`                      | Whether rename uses embedded tags when no match is available.         | Edit `config.toml` or toggle `--metadata-fallback/--no-metadata-fallback`.             |
| Config file `[logging]`        | `format`                  | `text` \| `jsonl`                 | `"text"`                    | Log output format.                                                    | Edit `config.toml`.                                                                    |
| Config file `[logging]`        | `absolute_paths`          | boolean                           | `false`                     | Emit absolute paths in rename logs.                                   | Edit `config.toml`.                                                                    |
| Config file `[general]`        | `locale`                  | string (e.g. `en`, `fr_FR`)       | auto (system locale)        | Preferred locale when CLI option/env var are unset.                   | Edit `config.toml`.                                                                    |
| Config file `[identify]`       | `limit`                   | integer >= 1                      | `3`                         | Default number of results returned by `identify`.                     | Edit `config.toml`.                                                                    |
| Config file `[identify]`       | `json`                    | boolean                           | `false`                     | Show JSON output by default.                                          | Edit `config.toml`.                                                                    |
| Config file `[identify]`       | `refresh`                 | boolean                           | `false`                     | Ignore the cache unless explicitly disabled.                          | Edit `config.toml`.                                                                    |
| Config file `[identify]`       | `audd_enabled`            | boolean                           | `true`                      | Enable AudD support when a token is configured.                       | Edit `config.toml` or pass `--use-audd/--no-audd`.                                     |
| Config file `[identify]`       | `prefer_audd`             | boolean                           | `false`                     | Try AudD before AcoustID when enabled.                                | Edit `config.toml` or pass `--prefer-audd/--prefer-acoustid`.                          |
| Config file `[identify]`       | `announce_source`         | boolean                           | `true`                      | Print the planned lookup strategy to `stderr`.                        | Edit `config.toml` or pass `--announce-source/--silent-source`.                        |
| Config file `[identify_batch]` | `limit`                   | integer >= 1                      | `3`                         | Maximum results stored per file in batch mode.                        | Edit `config.toml`.                                                                    |
| Config file `[identify_batch]` | `best_only`               | boolean                           | `false`                     | Record only the top proposal for each file.                           | Edit `config.toml`.                                                                    |
| Config file `[identify_batch]` | `recursive`               | boolean                           | `false`                     | Include sub-directories by default.                                   | Edit `config.toml`.                                                                    |
| Config file `[identify_batch]` | `log_file`                | string (path)                     | unset → `recozik-batch.log` | Default destination for batch logs.                                   | Edit `config.toml`.                                                                    |
| Config file `[identify_batch]` | `audd_enabled`            | boolean                           | `true`                      | Enable AudD support during batch identification.                      | Edit `config.toml` or pass `--use-audd/--no-audd`.                                     |
| Config file `[identify_batch]` | `prefer_audd`             | boolean                           | `false`                     | Try AudD before AcoustID in batch runs.                               | Edit `config.toml` or pass `--prefer-audd/--prefer-acoustid`.                          |
| Config file `[identify_batch]` | `announce_source`         | boolean                           | `true`                      | Print the batch lookup strategy to `stderr`.                          | Edit `config.toml` or pass `--announce-source/--silent-source`.                        |
| Config file `[rename]`         | `default_mode`            | `dry-run` \| `apply`              | `"dry-run"`                 | Default behaviour when neither `--dry-run` nor `--apply` is provided. | Edit `config.toml`.                                                                    |
| Config file `[rename]`         | `interactive`             | boolean                           | `false`                     | Enables interactive selection without `--interactive`.                | Edit `config.toml`.                                                                    |
| Config file `[rename]`         | `confirm_each`            | boolean                           | `false`                     | Asks for confirmation before each rename by default.                  | Edit `config.toml`.                                                                    |
| Config file `[rename]`         | `conflict_strategy`       | `append` \| `skip` \| `overwrite` | `"append"`                  | Collision policy applied when no CLI flag is passed.                  | Edit `config.toml`.                                                                    |
| Config file `[rename]`         | `metadata_confirm`        | boolean                           | `true`                      | Request confirmation for metadata-based renames.                      | Edit `config.toml`.                                                                    |
| Config file `[rename]`         | `log_cleanup`             | `ask` \| `always` \| `never`      | `"ask"`                     | Cleanup policy for JSONL logs after `rename-from-log --apply`.        | Edit `config.toml` or pass `--log-cleanup`.                                            |
| Config file `[rename]`         | `require_template_fields` | boolean                           | `false`                     | Reject matches missing placeholders required by the template.         | Edit `config.toml` or use `--require-template-fields/--allow-missing-template-fields`. |
| Config file `[rename]`         | `deduplicate_template`    | boolean                           | `true`                      | Collapse proposals leading to the same target filename.               | Edit `config.toml` or use `--deduplicate-template/--keep-template-duplicates`.         |
| Environment                    | `RECOZIK_CONFIG_FILE`     | path                              | unset                       | Absolute or relative path to a custom `config.toml`.                  | Export before running the CLI.                                                         |
| Environment                    | `RECOZIK_LOCALE`          | locale string                     | unset                       | Forces the active locale (higher priority than config file).          | Export before running the CLI.                                                         |
| Environment                    | `AUDD_API_TOKEN`          | string                            | unset                       | AudD token used when `--audd-token` is omitted.                       | Export before running the CLI.                                                         |
| Environment (auto)             | `_RECOZIK_COMPLETE`       | internal                          | auto-managed                | Shell-completion hook managed by Typer; not meant to be set manually. | Set automatically by generated completion scripts.                                     |

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

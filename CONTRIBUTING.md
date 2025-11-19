# Contributing to recozik

Thanks for your interest in improving recozik! This guide summarizes how to get a local environment running and the expectations for pull requests.

## Prerequisites

- Python 3.10–3.13 installed on your machine (3.14 is still experimental upstream).
- The [Chromaprint](https://acoustid.org/chromaprint) tooling (`fpcalc`) available on your `PATH` for fingerprint generation.
- [`uv`](https://docs.astral.sh/uv/) installed (`pip install uv`).

## Setting up the project

1. Install runtime and development dependencies:
   ```bash
   uv sync --all-groups
   ```
2. Activate the virtual environment created by uv if you need an interactive shell:
   ```bash
   source .venv/bin/activate
   ```
   (On Windows use `.venv\Scripts\activate`.)
3. Run the test suite to ensure the environment works:
   ```bash
   uv run pytest
   ```

## Development workflow

- Format code with `uv run ruff format`.
- Lint with `uv run ruff check --fix` before opening a PR.
- Add or update tests whenever you change CLI behaviour.
- Compile translations with `python scripts/compile_translations.py` after editing `.po` files and keep English/French `.po` files in sync.
- Update the Next.js locale bundles (`packages/recozik-webui/src/i18n`) whenever you touch UI copy. Run `npm run lint` to validate the frontend.

## Documentation & localization expectations

- Any change to CLI options, service behaviour, backend routes, or web UI must include documentation updates: `.github/copilot-instructions.md`, `README.md`, `README.fr.md`, `docs/deploy-*.md` (EN + FR), `TRANSLATION.md`, and any feature-focused docs.
- Keep `AGENTS.md` (and its symlinked counterparts) synced when new workflow or permission requirements are introduced for automation agents.
- When a new translatable string is introduced (CLI/services/frontend), wrap it in `_()` (Python) or add it to the i18n dictionaries (Next.js), then recompile the `.mo` catalogs with `python scripts/compile_translations.py`.

## Commit conventions

- Use imperative commit messages (e.g. `Add interactive rename mode`).
- Sign commits with `-s` to include a Developer Certificate of Origin.
- Keep commits focused and leave the tree green (tests passing).

## Pull request expectations

- Describe behaviour changes and any new CLI options.
- Mention documentation updates and highlight testing performed.
- Provide reproduction steps or sample commands when fixing bugs.
- Link related issues or TODOs.

## Code of Conduct

By participating you agree to uphold the [Code of Conduct](CODE_OF_CONDUCT.md). Please report unacceptable behaviour to `security@zajda.fr`.

## Security disclosures

Do not file security vulnerabilities through public issues. Instead, follow the [security policy](SECURITY.md).

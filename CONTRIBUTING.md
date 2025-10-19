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
- Compile translations with `python scripts/compile_translations.py` after editing `.po` files.

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

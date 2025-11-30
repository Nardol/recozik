# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- Split the codebase into a uv workspace: the reusable core now lives in `packages/recozik-core` while the CLI stays under `src/recozik`, keeping backwards-compatible shims for existing imports.
- Moved gettext catalogs into the core package and updated docs/tooling (README, TRANSLATION.md, AGENTS.md, scripts) to point to the new location.
- Added uv lock/workspace metadata and ensured Ruff/pytest cover both the CLI and the new core package.
- Stored AcoustID/AudD credentials in the system keyring via `recozik_core.secrets`, added `ACOUSTID_API_KEY` env fallback, and stopped writing secrets in plaintext config files.
- Automatically migrate legacy plaintext secrets from `config.toml` into the keyring on the next run, rewriting the file with placeholders.
- Added optional MusicBrainz enrichment for `identify` and `identify-batch`, including new `--with-musicbrainz/--without-musicbrainz` toggles and missing-only controls.
- Normalized AudD responses now capture MusicBrainz identifiers when returned by the API, letting cached results retain MBIDs and improving downstream metadata merges.
- Internal: introduced the `recozik-services` workspace package, rewired CLI commands to call its identify/batch/rename runners, and added docs/tests for the shared service layer that future GUIs will consume.
- Migrated the Next.js web interface from `middleware.ts` to the new `proxy.ts` entry point so locale routing keeps working on Next 16.
- **BREAKING**: Added comprehensive user management system to the web backend with User table, role-based access control (admin/operator/readonly), per-user feature permissions, and quota limits. Changed `SessionToken.user_id` from string to integer foreign key. **Migration required** - see MIGRATION.md for upgrade instructions. New admin endpoints: user CRUD, password reset, session management. Frontend includes UserManager component with full user administration UI.

## [0.10.0] - 2025-10-31

- Added AudD snippet offset controls

## [0.9.0] - 2025-10-29

- Added AudD enterprise API support.

## [0.8.0] - 2025-10-28

- Streamlined AudD identification output and display a strategy banner when fallbacks engage.

## [0.7.0] - 2025-10-28

- Handled empty metadata fallback results more gracefully during identification.

## [0.6.0] - 2025-10-25

- Streamlined CLI option resolution and AudD helper flows to reduce duplication.
- Documented expectations for AI optimization usage.

## [0.5.0] - 2025-10-24

- Added optional FFmpeg integration to support compressed audio formats in the CLI.
- Hardened AudD fallbacks by redacting tokens from diagnostics and closing snippet file handles.

## [0.4.0] - 2025-10-23

- Added AudD snippet handling and clarified fallback messaging.
- Expanded identification documentation with default tables and configuration guidance.

## [0.3.1] - 2025-10-23

- Prevented duplicate rename proposals when templates render identical filenames.

## [0.3.0] - 2025-10-19

- Added toggles to control the AudD fallback preference used during identification.

## [0.2.1] - 2025-10-19

- Enabled config-driven defaults for rename interactions and other CLI options.
- Added template-aware filtering for rename-from-log content suggestions.
- Documented Python 3.13 support alongside new configuration override examples.

## [0.2.0] - 2025-10-17

- Introduced AudD fallback support when AcoustID cannot resolve a track.

## [0.1.2] - 2025-10-15

- Deduplicated AcoustID matches before proposing renames.
- Added post-dry-run apply prompts and log cleanup controls to rename-from-log.
- Localized dry-run messaging in French and consolidated rename test helpers.

## [0.1.1] - 2025-10-13

- Reorganized the CLI into modular Typer commands and improved import-time performance.
- Added batch rename support with caching plus richer rename-from-log interactions, including interactive selection, export, and confirmations.
- Introduced gettext-based localization, localizing rename status output and expanding documentation for contributors.

## [0.1.0] - 2025-09-29

- First tagged version of recozik with CLI commands for inspecting, fingerprinting, identifying, and batching audio processing.

"""Command-line interface for recozik."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from string import Formatter
from typing import Any

import click
import requests
import typer
from typer.completion import (
    get_completion_script as generate_completion_script,
)
from typer.completion import (
    install as install_completion,
)
from typer.completion import (
    shellingham as completion_shellingham,
)

from .cache import LookupCache
from .config import AppConfig, default_config_path, load_config, write_config
from .fingerprint import (
    AcoustIDLookupError,
    AcoustIDMatch,
    FingerprintError,
    FingerprintResult,
    compute_fingerprint,
    lookup_recordings,
)
from .i18n import (
    _,
    detect_system_locale,
    resolve_preferred_locale,
    set_locale,
)

try:  # pragma: no cover - depends on the environment
    import mutagen  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on the environment
    mutagen = None  # type: ignore[assignment]

_ENV_LOCALE_VAR = "RECOZIK_LOCALE"
_LOGGER = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help=_("Music recognition based on audio fingerprints."),
)
config_app = typer.Typer(
    add_completion=False,
    help=_("Manage local configuration."),
)
completion_app = typer.Typer(
    add_completion=False,
    help=_("Shell auto-completion helpers."),
)

app.add_typer(config_app, name="config")
app.add_typer(completion_app, name="completion")

DEFAULT_AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus"}
_VALIDATION_TRACK_ID = "9ff43b6a-4f16-427c-93c2-92307ca505e0"
_VALIDATION_ENDPOINT = "https://api.acoustid.org/v2/lookup"


def _resolve_path(path: Path) -> Path:
    """Normalize user-provided paths while expanding ``~``."""
    return path.expanduser().resolve()


def _apply_locale(
    ctx: typer.Context | None,
    *,
    config: AppConfig | None = None,
    override: str | None = None,
) -> None:
    """Install the locale following CLI/env/config precedence."""
    ctx_locale = None
    if ctx is not None:
        ctx.ensure_object(dict)
        if isinstance(ctx.obj, dict):
            ctx_locale = ctx.obj.get("cli_locale")

    env_locale = os.environ.get(_ENV_LOCALE_VAR)
    config_locale = config.locale if config else None

    final_locale = resolve_preferred_locale(
        override,
        ctx_locale,
        env_locale,
        config_locale,
        detect_system_locale(),
    )
    set_locale(final_locale)


@app.callback()
def main(
    ctx: typer.Context,
    locale_option: str | None = typer.Option(
        None,
        "--locale",
        help=_("Override the locale for this invocation (examples: en, fr, fr_FR)."),
    ),
) -> None:
    """Top-level callback for the CLI application."""
    ctx.ensure_object(dict)
    ctx.obj["cli_locale"] = locale_option
    if locale_option:
        set_locale(locale_option)


@app.command(help=_("Display basic metadata extracted from an audio file."))
def inspect(
    ctx: typer.Context,
    audio_path: Path = typer.Argument(
        ...,
        help=_("Path to the audio file to analyse."),
    ),
) -> None:
    """Display basic metadata for the provided audio file."""
    _apply_locale(ctx)
    resolved = _resolve_path(audio_path)
    if not resolved.is_file():
        typer.echo(_("File not found: {path}").format(path=resolved))
        raise typer.Exit(code=1)

    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - depends on the runtime environment
        typer.echo(
            _("The soundfile library is missing; run `uv sync` to install project dependencies.")
        )
        raise typer.Exit(code=1) from exc

    try:
        info = sf.info(str(resolved))
    except RuntimeError as exc:
        typer.echo(_("Unable to read the audio file: {error}").format(error=exc))
        raise typer.Exit(code=1) from exc

    typer.echo(_("File: {path}").format(path=resolved))
    typer.echo(_("Format: {format}, {subtype}").format(format=info.format, subtype=info.subtype))
    typer.echo(_("Channels: {channels}").format(channels=info.channels))
    typer.echo(_("Sample rate: {samplerate} Hz").format(samplerate=info.samplerate))
    typer.echo(_("Frame count: {frames}").format(frames=info.frames))
    typer.echo(_("Estimated duration: {duration:.2f} s").format(duration=info.duration))

    metadata = _extract_audio_metadata(resolved)
    if metadata:
        typer.echo(_("Embedded metadata:"))
        if artist := metadata.get("artist"):
            typer.echo(_("  Artist: {value}").format(value=artist))
        if title := metadata.get("title"):
            typer.echo(_("  Title: {value}").format(value=title))
        if album := metadata.get("album"):
            typer.echo(_("  Album: {value}").format(value=album))
    elif mutagen is None:  # pragma: no cover - depends on installations
        typer.echo(_("No metadata available (mutagen library missing)."))


@app.command(help=_("Generate the Chromaprint fingerprint of an audio file."))
def fingerprint(
    ctx: typer.Context,
    audio_path: Path = typer.Argument(
        ...,
        help=_("Path to the audio file to fingerprint."),
    ),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help=_("Explicit path to the fpcalc executable when Chromaprint is not on PATH."),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=_("File where the fingerprint should be written in JSON format."),
    ),
    show_fingerprint: bool = typer.Option(
        False,
        "--show-fingerprint",
        help=_("Show full fingerprint in console (long and less convenient for screen readers)."),
    ),
) -> None:
    """Generate a Chromaprint fingerprint for an audio file."""
    _apply_locale(ctx)
    resolved_audio = _resolve_path(audio_path)
    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        result: FingerprintResult = compute_fingerprint(resolved_audio, fpcalc_path=resolved_fpcalc)
    except FingerprintError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(_("Estimated duration: {duration:.2f} s").format(duration=result.duration_seconds))

    if output is not None:
        resolved_output = _resolve_path(output)
        payload = {
            "audio_path": str(resolved_audio),
            "duration_seconds": result.duration_seconds,
            "fingerprint": result.fingerprint,
            "fpcalc_path": str(resolved_fpcalc) if resolved_fpcalc else None,
        }
        resolved_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        typer.echo(_("Fingerprint saved to {path}").format(path=resolved_output))

    if show_fingerprint:
        typer.echo(_("Chromaprint fingerprint:"))
        typer.echo(result.fingerprint)


@app.command(help=_("Identify a track using the AcoustID API."))
def identify(
    ctx: typer.Context,
    audio_path: Path = typer.Argument(
        ...,
        help=_("Path to the audio file to identify."),
    ),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help=_("Explicit path to the fpcalc executable when Chromaprint is not on PATH."),
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help=_("AcoustID API key to use (takes priority over the configuration file)."),
    ),
    limit: int = typer.Option(
        3,
        "--limit",
        min=1,
        max=10,
        help=_("Number of results to display."),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_("Display the results as JSON (useful for scripting or screen readers)."),
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help=_("Output template (placeholders: {artist}, {title}, {album}, {score}, ...)."),
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help=_("Ignore the local cache and force a new API request."),
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help=_("Custom configuration file path (tests)."),
    ),
) -> None:
    """Identify a track with the AcoustID API."""
    _apply_locale(ctx)
    resolved_audio = _resolve_path(audio_path)
    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _apply_locale(ctx, config=config)

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        typer.echo(_("No AcoustID API key configured."))
        if _prompt_yes_no(_("Would you like to save it now?"), default=True):
            new_key = _configure_api_key_interactively(config, config_path)
            if not new_key:
                typer.echo(_("No key was stored. Operation cancelled."))
                raise typer.Exit(code=1)
            key = new_key
            try:
                config = load_config(config_path)
            except RuntimeError:
                config = AppConfig(acoustid_api_key=key)
            _apply_locale(ctx, config=config)
        else:
            typer.echo(_("Operation cancelled."))
            raise typer.Exit(code=1)

    try:
        fingerprint_result: FingerprintResult = compute_fingerprint(
            resolved_audio,
            fpcalc_path=resolved_fpcalc,
        )
    except FingerprintError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    cache = LookupCache(
        enabled=config.cache_enabled,
        ttl=timedelta(hours=max(config.cache_ttl_hours, 1)),
    )

    matches = None
    if config.cache_enabled and not refresh:
        matches = cache.get(fingerprint_result.fingerprint, fingerprint_result.duration_seconds)

    if matches is None:
        try:
            matches = lookup_recordings(key, fingerprint_result)
        except AcoustIDLookupError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        if config.cache_enabled:
            cache.set(fingerprint_result.fingerprint, fingerprint_result.duration_seconds, matches)
            cache.save()
    else:
        matches = list(matches)

    if not matches:
        typer.echo(_("No matches found."))
        cache.save()
        return

    matches = matches[:limit]

    if json_output:
        payload = [match.to_dict() for match in matches]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        cache.save()
        return

    template_value = _resolve_template(template, config)

    for idx, match in enumerate(matches, start=1):
        typer.echo(_("Result {index}: score {score:.2f}").format(index=idx, score=match.score))
        typer.echo(f"  {_format_match_template(match, template_value)}")
        if match.release_group_title:
            typer.echo(_("  Album: {value}").format(value=match.release_group_title))
        elif match.releases:
            primary = match.releases[0]
            album = primary.title or _("Unknown album")
            suffix = f" ({primary.date})" if primary.date else ""
            typer.echo(_("  Album: {value}{suffix}").format(value=album, suffix=suffix))
        typer.echo(_("  Recording ID: {identifier}").format(identifier=match.recording_id))
        if match.release_group_id:
            typer.echo(
                _("  Release Group ID: {identifier}").format(identifier=match.release_group_id)
            )

    cache.save()


@app.command(
    "identify-batch",
    help=_("Identify audio files in a directory and persist the results."),
)
def identify_batch(
    ctx: typer.Context,
    directory: Path = typer.Argument(
        ...,
        help=_("Directory containing the audio files."),
    ),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help=_("Explicit path to the fpcalc executable when Chromaprint is not on PATH."),
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help=_("AcoustID API key to use (takes priority over the configuration file)."),
    ),
    limit: int = typer.Option(
        3,
        "--limit",
        min=1,
        max=10,
        help=_("Number of proposals to keep for each file."),
    ),
    best_only: bool = typer.Option(
        False,
        "--best-only",
        help=_("Store only the best proposal for each file."),
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive/--no-recursive",
        help=_("Search recursively in sub-directories."),
    ),
    pattern: list[str] = typer.Option(
        [],
        "--pattern",
        help=_("Glob pattern to apply (can be repeated)."),
    ),
    extension: list[str] = typer.Option(
        [],
        "--ext",
        "--extension",
        help=_("File extension to include (e.g. mp3). Can be repeated."),
    ),
    log_file: Path | None = typer.Option(
        None,
        "--log-file",
        "-o",
        help=_("Report output file (default: recozik-batch.log)."),
    ),
    append: bool = typer.Option(
        False,
        "--append/--overwrite",
        help=_("Append to the existing log instead of recreating it."),
    ),
    log_format: str | None = typer.Option(
        None,
        "--log-format",
        help=_("Log format: text or jsonl."),
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help=_("Template for proposals ({artist}, {title}, {album}, {score}, ...)."),
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help=_("Ignore the local cache and force a new API call."),
    ),
    metadata_fallback: bool | None = typer.Option(
        None,
        "--metadata-fallback/--no-metadata-fallback",
        help=_(
            "Use embedded metadata when AcoustID returns no match; follows configuration defaults."
        ),
    ),
    absolute_paths: bool | None = typer.Option(
        None,
        "--absolute-paths/--relative-paths",
        help=_("Control how paths are written in the log (overrides configuration)."),
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help=_("Custom configuration file path (tests)."),
    ),
) -> None:
    """Identify audio files in a directory and record the results."""
    _apply_locale(ctx)
    resolved_dir = _resolve_path(directory)
    if not resolved_dir.is_dir():
        typer.echo(_("Directory not found: {path}").format(path=resolved_dir))
        raise typer.Exit(code=1)

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _apply_locale(ctx, config=config)

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        typer.echo(_("No AcoustID API key configured."))
        if _prompt_yes_no(_("Would you like to save it now?"), default=True):
            new_key = _configure_api_key_interactively(config, config_path)
            if not new_key:
                typer.echo(_("No key was stored. Operation cancelled."))
                raise typer.Exit(code=1)
            key = new_key
            try:
                config = load_config(config_path)
            except RuntimeError:
                config = AppConfig(acoustid_api_key=key)
            _apply_locale(ctx, config=config)
        else:
            typer.echo(_("Operation cancelled."))
            raise typer.Exit(code=1)

    template_value = _resolve_template(template, config)
    log_format_value = (log_format or config.log_format).lower()
    if log_format_value not in {"text", "jsonl"}:
        typer.echo(_("Invalid log format. Use 'text' or 'jsonl'."))
        raise typer.Exit(code=1)

    use_absolute = config.log_absolute_paths if absolute_paths is None else absolute_paths

    effective_extensions = _normalize_extensions(extension)
    if not pattern and not effective_extensions:
        effective_extensions = DEFAULT_AUDIO_EXTENSIONS

    files = list(
        _discover_audio_files(
            resolved_dir,
            recursive=recursive,
            patterns=pattern,
            extensions=effective_extensions,
        )
    )
    files.sort()

    if not files:
        typer.echo(_("No audio files matched the selection."))
        return

    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    cache = LookupCache(
        enabled=config.cache_enabled,
        ttl=timedelta(hours=max(config.cache_ttl_hours, 1)),
    )

    use_metadata_fallback = (
        config.metadata_fallback_enabled if metadata_fallback is None else metadata_fallback
    )

    effective_limit = 1 if best_only else limit

    log_path = _resolve_path(log_file) if log_file else Path.cwd() / "recozik-batch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"

    success = 0
    unmatched = 0
    failures = 0

    with log_path.open(mode, encoding="utf-8") as handle:
        for file_path in files:
            if use_absolute:
                relative_display = str(file_path)
            else:
                try:
                    relative_display = str(file_path.relative_to(resolved_dir))
                except ValueError:
                    relative_display = str(file_path)

            try:
                fingerprint_result = compute_fingerprint(file_path, fpcalc_path=resolved_fpcalc)
            except FingerprintError as exc:
                _write_log_entry(
                    handle,
                    log_format_value,
                    relative_display,
                    [],
                    str(exc),
                    template_value,
                    None,
                    status="error",
                    metadata=None,
                )
                failures += 1
                continue

            matches = None
            if config.cache_enabled and not refresh:
                matches = cache.get(
                    fingerprint_result.fingerprint,
                    fingerprint_result.duration_seconds,
                )

            if matches is None:
                try:
                    matches = lookup_recordings(key, fingerprint_result)
                except AcoustIDLookupError as exc:
                    _write_log_entry(
                        handle,
                        log_format_value,
                        relative_display,
                        [],
                        str(exc),
                        template_value,
                        fingerprint_result,
                        status="error",
                        metadata=None,
                    )
                    failures += 1
                    continue
                if config.cache_enabled:
                    cache.set(
                        fingerprint_result.fingerprint,
                        fingerprint_result.duration_seconds,
                        matches,
                    )
            else:
                matches = list(matches)

            if not matches:
                metadata_payload = (
                    _extract_audio_metadata(file_path) if use_metadata_fallback else None
                )
                _write_log_entry(
                    handle,
                    log_format_value,
                    relative_display,
                    [],
                    None,
                    template_value,
                    fingerprint_result,
                    status="unmatched",
                    note=_("No match."),
                    metadata=metadata_payload,
                )
                if metadata_payload:
                    typer.echo(
                        _("No match for {path}, embedded metadata recorded in the log.").format(
                            path=relative_display
                        )
                    )
                unmatched += 1
                continue

            selected = matches[:effective_limit]
            _write_log_entry(
                handle,
                log_format_value,
                relative_display,
                selected,
                None,
                template_value,
                fingerprint_result,
                metadata=None,
            )
            success += 1

    cache.save()
    typer.echo(_("Processing complete."))
    typer.echo(
        _("Results: {identified} identified, {unmatched} unmatched, {failed} failures.").format(
            identified=success,
            unmatched=unmatched,
            failed=failures,
        )
    )
    typer.echo(_("Log: {path}").format(path=log_path))


@app.command(
    "rename-from-log",
    help=_("Rename files using a JSONL log produced by `identify-batch`."),
)
def rename_from_log(
    ctx: typer.Context,
    log_path: Path = typer.Argument(
        ...,
        help=_("JSONL log generated by `identify-batch`."),
    ),
    root: Path | None = typer.Option(
        None,
        "--root",
        help=_("Root directory containing the files to rename (defaults to the log directory)."),
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help=_("Rename template ({artist}, {title}, {album}, {score}, ...)."),
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--apply",
        help=_("Preview rename operations only (default). Use --apply to commit changes."),
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive/--no-interactive",
        help=_("Offer an interactive choice when multiple matches are available."),
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm/--no-confirm",
        help=_("Ask for confirmation before renaming each file."),
    ),
    on_conflict: str = typer.Option(
        "append",
        "--on-conflict",
        help=_("Collision handling strategy: append (default), skip, overwrite."),
    ),
    backup_dir: Path | None = typer.Option(
        None,
        "--backup-dir",
        help=_("Directory where originals are copied before renaming (optional)."),
    ),
    export_path: Path | None = typer.Option(
        None,
        "--export",
        help=_("Path to a JSON file summarising the planned renames."),
    ),
    metadata_fallback: bool | None = typer.Option(
        None,
        "--metadata-fallback/--no-metadata-fallback",
        help=_("Use embedded metadata when no proposal is available."),
    ),
    metadata_fallback_confirm: bool = typer.Option(
        True,
        "--metadata-fallback-confirm/--metadata-fallback-no-confirm",
        help=_("Confirm renames based on embedded metadata (use --metadata-fallback-no-confirm)."),
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help=_("Custom configuration file path (tests)."),
    ),
) -> None:
    """Rename files using a JSONL log generated by ``identify-batch``."""
    _apply_locale(ctx)
    resolved_log = _resolve_path(log_path)
    if not resolved_log.is_file():
        typer.echo(_("Log file not found: {path}").format(path=resolved_log))
        raise typer.Exit(code=1)

    root_path = _resolve_path(root) if root else resolved_log.parent

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _apply_locale(ctx, config=config)

    template_value = _resolve_template(template, config)
    conflict_strategy = on_conflict.lower()
    if conflict_strategy not in {"append", "skip", "overwrite"}:
        typer.echo(_("Invalid --on-conflict value. Choose append, skip, or overwrite."))
        raise typer.Exit(code=1)

    use_metadata_fallback = (
        config.metadata_fallback_enabled if metadata_fallback is None else metadata_fallback
    )

    try:
        entries = _load_jsonl_log(resolved_log)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if not entries:
        typer.echo(_("No entries found in the log."))
        return

    backup_path = _resolve_path(backup_dir) if backup_dir else None
    if backup_path:
        backup_path.mkdir(parents=True, exist_ok=True)

    planned: list[tuple[Path, Path, dict]] = []
    export_entries: list[dict] = []
    occupied: set[Path] = set()
    renamed = 0
    skipped = 0
    errors = 0
    apply_after_interrupt = False

    for entry in entries:
        raw_path = entry.get("path")
        if not raw_path:
            errors += 1
            typer.echo(_("Entry without a path: skipped."))
            continue

        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = (root_path / source_path).resolve()

        if not source_path.exists():
            errors += 1
            typer.echo(_("File not found, skipped: {path}").format(path=source_path))
            continue

        status = entry.get("status")
        error_message = entry.get("error")
        note = entry.get("note")

        matches = entry.get("matches") or []
        metadata_entry = _coerce_metadata_dict(entry.get("metadata"))

        if status == "unmatched" and not matches:
            if use_metadata_fallback and metadata_entry:
                typer.echo(
                    _("No AcoustID match for {path}, using embedded metadata.").format(
                        path=source_path
                    )
                )
                matches = [_build_metadata_match(metadata_entry)]
            else:
                skipped += 1
                context = f" ({note})" if note else ""
                typer.echo(
                    _("No proposal for: {path}{context}").format(path=source_path, context=context)
                )
                continue

        if error_message:
            if matches:
                skipped += 1
                typer.echo(
                    _("Entry with error, skipped: {path} ({error})").format(
                        path=source_path, error=error_message
                    )
                )
                continue
            if use_metadata_fallback and metadata_entry:
                typer.echo(
                    _("No AcoustID match for {path}, using embedded metadata.").format(
                        path=source_path
                    )
                )
                matches = [_build_metadata_match(metadata_entry)]
                error_message = None
            else:
                skipped += 1
                typer.echo(
                    _("Entry with error, skipped: {path} ({error})").format(
                        path=source_path, error=error_message
                    )
                )
                continue

        if not matches:
            if use_metadata_fallback and metadata_entry:
                typer.echo(
                    _("No AcoustID match for {path}, using embedded metadata.").format(
                        path=source_path
                    )
                )
                matches = [_build_metadata_match(metadata_entry)]
            else:
                skipped += 1
                typer.echo(_("No proposal for: {path}").format(path=source_path))
                continue

        selected_match_index = 0
        if interactive and len(matches) > 1:
            while True:
                try:
                    selected_match_index = _prompt_match_selection(matches, source_path)
                except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
                    decision = _prompt_interactive_interrupt_decision(bool(planned))
                    if decision == "cancel":
                        typer.echo(_("Operation cancelled; no files renamed."))
                        raise typer.Exit(code=1) from None
                    if decision == "apply":
                        apply_after_interrupt = True
                        break
                    # decision == "resume"
                    continue
                else:
                    break

            if apply_after_interrupt:
                break

            if selected_match_index is None:
                skipped += 1
                typer.echo(
                    _("No selection made for {name}; skipping.").format(name=source_path.name)
                )
                continue

        match_data = matches[selected_match_index]
        is_metadata_match = match_data.get("source") == "metadata"
        target_base = _render_log_template(match_data, template_value, source_path)
        sanitized = _sanitize_filename(target_base)
        if not sanitized:
            sanitized = source_path.stem

        ext = source_path.suffix
        new_name = sanitized
        if ext and not new_name.lower().endswith(ext.lower()):
            new_name = f"{new_name}{ext}"

        target_path = source_path.with_name(new_name)
        if target_path == source_path:
            skipped += 1
            typer.echo(_("Already named correctly: {name}").format(name=source_path.name))
            continue

        final_target = _resolve_conflict_path(
            target_path,
            source_path,
            conflict_strategy,
            occupied,
            dry_run,
        )

        if final_target is None:
            skipped += 1
            typer.echo(
                _("Unresolved collision, file skipped: {name}").format(name=source_path.name)
            )
            continue

        metadata_confirmation_done = False

        if is_metadata_match and metadata_fallback_confirm:
            question = _("Confirm rename based on embedded metadata: {source} -> {target}?").format(
                source=source_path.name, target=final_target.name
            )
            skip_current = False
            while True:
                try:
                    if not _prompt_yes_no(question, default=True):
                        skip_current = True
                        break
                    metadata_confirmation_done = True
                    break
                except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
                    decision = _prompt_interactive_interrupt_decision(bool(planned))
                    if decision == "cancel":
                        typer.echo(_("Operation cancelled; no files renamed."))
                        raise typer.Exit(code=1) from None
                    if decision == "apply":
                        apply_after_interrupt = True
                        break
                    continue

            if apply_after_interrupt:
                break

            if skip_current:
                skipped += 1
                typer.echo(
                    _("Metadata-based rename skipped for {name}.").format(name=source_path.name)
                )
                continue

        if confirm and not metadata_confirmation_done:
            question = _("Rename {source} -> {target}?").format(
                source=source_path.name,
                target=final_target.name,
            )
            skip_current = False
            while True:
                try:
                    if not _prompt_yes_no(question, default=True):
                        skip_current = True
                        break
                    break
                except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
                    decision = _prompt_interactive_interrupt_decision(bool(planned))
                    if decision == "cancel":
                        typer.echo(_("Operation cancelled; no files renamed."))
                        raise typer.Exit(code=1) from None
                    if decision == "apply":
                        apply_after_interrupt = True
                        break
                    continue

            if apply_after_interrupt:
                break

            if skip_current:
                skipped += 1
                typer.echo(_("Rename skipped for {name}").format(name=source_path.name))
                continue

        planned.append((source_path, final_target, match_data))
        occupied.add(final_target)

    if not planned:
        typer.echo(
            _("No rename performed ({skipped} skipped, {errors} errors).").format(
                skipped=skipped, errors=errors
            )
        )
        return

    if apply_after_interrupt and planned:
        typer.echo(_("Continuing with renames confirmed before the interruption."))

    index = 0
    interrupted_during_rename = False
    while index < len(planned):
        source_path, target_path, match_data = planned[index]
        action = _("DRY-RUN") if dry_run else _("RENAMED")
        typer.echo(
            _("{action}: {source} -> {target}").format(
                action=action,
                source=source_path,
                target=target_path,
            )
        )

        if dry_run:
            export_entries.append(
                {
                    "source": str(source_path),
                    "target": str(target_path),
                    "applied": False,
                    "match": match_data,
                }
            )
            index += 1
            continue

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if backup_path:
                backup_file = _compute_backup_path(source_path, root_path, backup_path)
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, backup_file)

            if target_path.exists() and conflict_strategy == "overwrite":
                target_path.unlink()

            source_path.rename(target_path)
        except KeyboardInterrupt:
            decision = _prompt_rename_interrupt_decision(len(planned) - index)
            if decision == "continue":
                typer.echo(_("Continuing renaming."))
                continue

            interrupted_during_rename = True
            typer.echo(
                _(
                    "Renaming interrupted; {completed} file(s) already renamed, "
                    "{remaining} file(s) left untouched."
                ).format(
                    completed=renamed,
                    remaining=len(planned) - index,
                )
            )
            break

        renamed += 1
        export_entries.append(
            {
                "source": str(source_path),
                "target": str(target_path),
                "applied": True,
                "match": match_data,
            }
        )
        index += 1

    if dry_run:
        typer.echo(
            _(
                "Dry-run complete: {planned} potential renames, {skipped} skipped, {errors} errors."
            ).format(planned=len(planned), skipped=skipped, errors=errors)
        )
        typer.echo(_("Use --apply to run the renames."))
    elif not interrupted_during_rename:
        typer.echo(
            _("Renaming complete: {renamed} file(s), {skipped} skipped, {errors} errors.").format(
                renamed=renamed, skipped=skipped, errors=errors
            )
        )

    if export_path and export_entries:
        resolved_export = _resolve_path(export_path)
        resolved_export.parent.mkdir(parents=True, exist_ok=True)
        resolved_export.write_text(
            json.dumps(export_entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        typer.echo(_("Summary written to {path}").format(path=resolved_export))

    if interrupted_during_rename:
        raise typer.Exit(code=1)


@completion_app.command(
    "install",
    help=_("Install the shell completion script for the current shell."),
)
def completion_install(
    ctx: typer.Context,
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help=_("Target shell (bash, zsh, fish, powershell/pwsh). Autodetected if omitted."),
    ),
    print_command: bool = typer.Option(
        False,
        "--print-command",
        help=_("Print only the command to add to your shell profile."),
    ),
    no_write: bool = typer.Option(
        False,
        "--no-write",
        help=_("Output the completion script to stdout without writing files."),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=_("Write the completion script to a specific file (absolute or relative path)."),
    ),
) -> None:
    """Install the shell completion script for the current shell."""
    _apply_locale(ctx)
    target_shell = _normalize_shell(shell)

    if sum(bool(flag) for flag in (print_command, no_write, output is not None)) > 1:
        typer.echo(_("Use only one of --print-command, --no-write, or --output."))
        raise typer.Exit(code=1)

    if no_write:
        detected_shell = _detect_shell(target_shell)
        if not detected_shell:
            typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
            raise typer.Exit(code=1)

        script = generate_completion_script(
            prog_name="recozik",
            complete_var="_RECOZIK_COMPLETE",
            shell=detected_shell,
        )
        typer.echo(script)
        return

    if output is not None:
        detected_shell = _detect_shell(target_shell)
        if not detected_shell:
            typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
            raise typer.Exit(code=1)

        script = generate_completion_script(
            prog_name="recozik",
            complete_var="_RECOZIK_COMPLETE",
            shell=detected_shell,
        )
        resolved_path = _resolve_path(output)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(script, encoding="utf-8")
        typer.echo(_("Completion script written to {path}").format(path=resolved_path))
        typer.echo(_("Add it to your shell configuration if needed."))
        return

    try:
        detected_shell, script_path = install_completion(shell=target_shell, prog_name="recozik")
    except click.exceptions.Exit as exc:
        typer.echo(_("Shell not supported for auto-completion."))
        raise typer.Exit(code=1) from exc

    command = _completion_source_command(detected_shell, script_path)

    if print_command:
        if command:
            typer.echo(command)
        else:
            typer.echo(str(script_path))
        return

    typer.echo(_("Completion installed for {shell}.").format(shell=detected_shell))
    typer.echo(_("Script: {path}").format(path=script_path))
    if command:
        typer.echo(_("Command to add: {command}").format(command=command))
    typer.echo(_completion_hint(detected_shell, script_path))


@completion_app.command(
    "show",
    help=_("Display the generated auto-completion script."),
)
def completion_show(
    ctx: typer.Context,
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help=_("Target shell (bash, zsh, fish, powershell/pwsh). Autodetected if omitted."),
    ),
) -> None:
    """Display the generated shell-completion script."""
    _apply_locale(ctx)
    detected_shell = _detect_shell(shell)
    if not detected_shell:
        typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
        raise typer.Exit(code=1)

    script = generate_completion_script(
        prog_name="recozik",
        complete_var="_RECOZIK_COMPLETE",
        shell=detected_shell,
    )
    typer.echo(script)


@completion_app.command(
    "uninstall",
    help=_("Remove the auto-completion script installed by Recozik."),
)
def completion_uninstall(
    ctx: typer.Context,
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help=_("Target shell (bash, zsh, fish, powershell/pwsh). Autodetected if omitted."),
    ),
) -> None:
    """Remove the shell-completion script installed by recozik."""
    _apply_locale(ctx)
    detected_shell = _detect_shell(shell)
    if not detected_shell:
        typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
        raise typer.Exit(code=1)

    script_path = _completion_script_path(detected_shell)
    if script_path and script_path.exists():
        script_path.unlink()
        typer.echo(_("Completion script removed: {path}").format(path=script_path))
    else:
        typer.echo(_("No completion script to remove."))

    typer.echo(_completion_uninstall_hint(detected_shell))


def _normalize_shell(shell: str | None) -> str | None:
    if shell is None:
        return None

    normalized = shell.strip().lower()
    if normalized in {"", "auto"}:
        return None
    if normalized in {"powershell", "pwsh"}:
        return "pwsh"
    return normalized


def _detect_shell(shell: str | None) -> str | None:
    normalized = _normalize_shell(shell)
    if normalized:
        return normalized

    if completion_shellingham is None:
        return None

    disable_detection = os.getenv("_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION")
    if disable_detection:
        return None

    try:
        detected_shell, _ = completion_shellingham.detect_shell()
    except Exception:  # pragma: no cover - depends on the system
        return None

    return _normalize_shell(detected_shell)


def _completion_hint(shell: str, script_path: Path) -> str:
    command = _completion_source_command(shell, script_path)
    if command:
        if shell in {"bash", "zsh"}:
            return _(
                "Run `{command}` or add this line to your profile file (e.g. ~/.bashrc, ~/.zshrc)."
            ).format(command=command)
        if shell == "fish":
            return _("Restart `fish` or run `{command}` to activate completion.").format(
                command=command
            )
        if shell in {"powershell", "pwsh"}:
            return _(
                "Add `{command}` to your `$PROFILE` (PowerShell) to load completion automatically."
            ).format(command=command)
    return _("Completion installed. Restart your terminal to use it.")


def _completion_source_command(shell: str, script_path: Path) -> str | None:
    if shell in {"bash", "zsh", "fish"}:
        return f"source {script_path}"
    if shell in {"powershell", "pwsh"}:
        return f". {script_path}"
    return None


def _completion_script_path(shell: str) -> Path | None:
    if shell == "bash":
        return Path.home() / ".bash_completions" / "recozik.sh"
    if shell == "zsh":
        return Path.home() / ".zfunc" / "_recozik"
    if shell == "fish":
        return Path.home() / ".config/fish/completions/recozik.fish"
    if shell in {"powershell", "pwsh"}:
        return _powershell_profile_path(shell)
    return None


def _powershell_profile_path(shell: str) -> Path | None:
    shell_bin = "pwsh" if shell == "pwsh" else "powershell"
    try:
        command = [shell_bin, "-NoProfile", "-Command", "echo", "$profile"]
        result = subprocess.run(  # noqa: S603 - controlled argument list
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    output = result.stdout.strip()
    if not output:
        return None
    return Path(output)


def _completion_uninstall_hint(shell: str) -> str:
    if shell == "bash":
        return _(
            "Remove the line `source ~/.bash_completions/recozik.sh` from ~/.bashrc if necessary."
        )
    if shell == "zsh":
        return _("Check ~/.zshrc and remove the line adding ~/.zfunc if you no longer use it.")
    if shell == "fish":
        return _("Restart fish to apply the removal.")
    if shell in {"powershell", "pwsh"}:
        return _("Edit your $PROFILE file to remove the completion block added by Recozik.")
    return _("Completion uninstalled.")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _resolve_template(template: str | None, config: AppConfig) -> str:
    if template:
        return template
    if config.output_template:
        return config.output_template
    return "{artist} - {title}"


def _format_match_template(match: AcoustIDMatch, template: str) -> str:
    context = _build_match_context(match)
    formatter = Formatter()
    try:
        return formatter.vformat(template, (), _SafeDict(context))
    except Exception:  # pragma: no cover - template invalide
        fallback = "{artist} - {title}"
        return formatter.vformat(fallback, (), _SafeDict(context))


def _build_match_context(match: AcoustIDMatch) -> dict[str, str]:
    album = match.release_group_title
    if not album and match.releases:
        album = match.releases[0].title

    release_id = match.release_group_id
    if not release_id and match.releases:
        release_id = match.releases[0].release_id

    return {
        "artist": match.artist or _("Unknown artist"),
        "title": match.title or _("Unknown title"),
        "album": album or "",
        "release_id": release_id or "",
        "recording_id": match.recording_id or "",
        "score": f"{match.score:.2f}",
    }


def _normalize_extensions(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        entry = value.strip().lower()
        if not entry:
            continue
        if not entry.startswith("."):
            entry = f".{entry}"
        normalized.add(entry)
    return normalized


def _discover_audio_files(
    base_dir: Path,
    *,
    recursive: bool,
    patterns: Iterable[str],
    extensions: set[str],
) -> Iterable[Path]:
    seen: set[Path] = set()

    def _should_keep(path: Path) -> bool:
        if not path.is_file():
            return False
        if not extensions:
            return True
        return path.suffix.lower() in extensions

    iterator_patterns = list(patterns)
    if iterator_patterns:
        for pattern in iterator_patterns:
            globber = base_dir.rglob(pattern) if recursive else base_dir.glob(pattern)
            for item in globber:
                resolved = item.resolve()
                if resolved in seen:
                    continue
                if _should_keep(resolved):
                    seen.add(resolved)
                    yield resolved
    else:
        globber = base_dir.rglob("*") if recursive else base_dir.glob("*")
        for item in globber:
            resolved = item.resolve()
            if resolved in seen:
                continue
            if _should_keep(resolved):
                seen.add(resolved)
                yield resolved


def _write_log_entry(
    handle,
    log_format: str,
    path_display: str,
    matches: Iterable[AcoustIDMatch],
    error: str | None,
    template: str,
    fingerprint: FingerprintResult | None,
    *,
    status: str = "ok",
    note: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    if log_format == "jsonl":
        entry = {
            "path": path_display,
            "duration_seconds": fingerprint.duration_seconds if fingerprint else None,
            "error": error,
            "status": status,
            "note": note,
            "matches": [
                {
                    "rank": idx,
                    "formatted": _format_match_template(match, template),
                    "score": match.score,
                    "recording_id": match.recording_id,
                    "artist": match.artist,
                    "title": match.title,
                    "album": match.release_group_title
                    or (match.releases[0].title if match.releases else None),
                    "release_group_id": match.release_group_id,
                    "release_id": match.releases[0].release_id if match.releases else None,
                }
                for idx, match in enumerate(matches, start=1)
            ],
            "metadata": metadata or None,
        }
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return

    handle.write(f"file: {path_display}\n")
    if fingerprint:
        handle.write(f"  duration: {fingerprint.duration_seconds:.2f}s\n")
    if status and status != "ok":
        handle.write(f"  status: {status}\n")
    if note:
        handle.write(f"  note: {note}\n")
    if metadata:
        handle.write("  metadata:\n")
        for key in ("artist", "title", "album"):
            value = metadata.get(key)
            if value:
                handle.write(f"    {key}: {value}\n")
    if error:
        handle.write(f"  error: {error}\n\n")
        return

    for idx, match in enumerate(matches, start=1):
        formatted = _format_match_template(match, template)
        handle.write(f"  {idx}. {formatted} (score {match.score:.2f})\n")
    handle.write("\n")


def _load_jsonl_log(path: Path) -> list[dict]:
    entries: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    _("The log must be JSONL (rerun `identify-batch` with --log-format jsonl).")
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    _("Invalid JSONL entry (line {number}).").format(number=line_number)
                )
            entries.append(payload)
    return entries


def _render_log_template(match: dict, template: str, source_path: Path) -> str:
    context = {
        "artist": match.get("artist") or _("Unknown artist"),
        "title": match.get("title") or _("Unknown title"),
        "album": match.get("album") or "",
        "score": _format_score(match.get("score")),
        "recording_id": match.get("recording_id") or "",
        "release_group_id": match.get("release_group_id") or "",
        "release_id": match.get("release_id") or "",
        "ext": source_path.suffix,
        "stem": source_path.stem,
    }

    formatted = match.get("formatted")
    formatter = Formatter()
    try:
        return formatter.vformat(template, (), _SafeDict(context))
    except Exception:
        if formatted:
            return formatted
        return formatter.vformat("{artist} - {title}", (), _SafeDict(context))


def _format_score(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value or "")


def _extract_audio_metadata(path: Path) -> dict[str, str] | None:
    if mutagen is None:  # pragma: no cover - depends on installed packages
        return None

    try:
        audio = mutagen.File(path, easy=True)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive safety
        return None

    if audio is None:
        return None

    tags = getattr(audio, "tags", None)
    if not tags:
        return None

    def _first_value(tag_value: Any) -> str | None:
        if tag_value is None:
            return None
        if isinstance(tag_value, str):
            candidate = tag_value.strip()
            return candidate or None
        if isinstance(tag_value, (list, tuple, set)):
            for item in tag_value:
                candidate = _first_value(item)
                if candidate:
                    return candidate
            return None
        try:
            candidate = str(tag_value).strip()
        except Exception as exc:  # pragma: no cover - defensive conversion
            _LOGGER.debug("Failed to normalize tag value %r: %s", tag_value, exc)
            return None
        return candidate or None

    metadata: dict[str, str] = {}
    for key in ("artist", "title", "album"):
        value = _first_value(tags.get(key))  # type: ignore[arg-type]
        if value:
            metadata[key] = value

    return metadata or None


def _coerce_metadata_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    result: dict[str, str] = {}
    for key in ("artist", "title", "album"):
        raw = value.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            candidate = raw.strip()
        else:
            try:
                candidate = str(raw).strip()
            except Exception as exc:  # pragma: no cover - defensive conversion
                _LOGGER.debug("Skipping metadata value %r for %s: %s", raw, key, exc)
                continue
        if candidate:
            result[key] = candidate
    return result


def _build_metadata_match(metadata: dict[str, str]) -> dict[str, object]:
    artist_value = metadata.get("artist") or _("Unknown artist")
    title_value = metadata.get("title") or _("Unknown title")
    formatted = f"{artist_value} - {title_value}"
    return {
        "score": None,
        "recording_id": None,
        "artist": metadata.get("artist"),
        "title": metadata.get("title"),
        "album": metadata.get("album"),
        "release_group_id": None,
        "release_id": None,
        "formatted": formatted,
        "source": "metadata",
    }


INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def _sanitize_filename(name: str) -> str:
    sanitized_chars: list[str] = []
    for char in name:
        if char in INVALID_FILENAME_CHARS or ord(char) < 32 or char in {"/", "\\"}:
            sanitized_chars.append("_")
        else:
            sanitized_chars.append(char)
    sanitized = "".join(sanitized_chars)
    sanitized = sanitized.strip().strip(". ")
    return sanitized


def _resolve_conflict_path(
    target_path: Path,
    source_path: Path,
    strategy: str,
    occupied: set[Path],
    dry_run: bool,
) -> Path | None:
    candidate = target_path
    directory = candidate.parent

    if strategy == "append":
        base = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while (candidate.exists() and candidate != source_path) or candidate in occupied:
            candidate = directory / f"{base}-{counter}{suffix}"
            counter += 1
        return candidate

    if strategy == "skip":
        if (candidate.exists() and candidate != source_path) or candidate in occupied:
            return None
        return candidate

    if strategy == "overwrite":
        if candidate in occupied and candidate != source_path:
            return None
        return candidate

    return None


def _compute_backup_path(source: Path, root: Path, backup_root: Path) -> Path:
    try:
        relative = source.relative_to(root)
    except ValueError:
        relative = Path(source.name)
    return backup_root / relative


def _prompt_interactive_interrupt_decision(has_planned: bool) -> str:
    typer.echo(_("Interrupt received during interactive selection."))
    typer.echo(_("  1. Cancel everything and exit."))
    typer.echo(_("  2. Stop asking questions and apply the confirmed renames."))
    typer.echo(_("  3. Resume the current question."))
    choices = {"1": "cancel", "2": "apply", "3": "resume"}
    prompt = _("Choose an option: ")

    while True:
        try:
            selection = typer.prompt(prompt, show_default=False).strip()
        except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
            typer.echo(_("Use the menu to continue."))
            continue

        if selection in choices:
            if selection == "2" and not has_planned:
                typer.echo(_("No rename has been confirmed yet, nothing to apply."))
                continue
            return choices[selection]

        typer.echo(_("Invalid option, please try again."))


def _prompt_rename_interrupt_decision(remaining: int) -> str:
    typer.echo(
        _("Renaming is in progress. {remaining} file(s) still need to be processed.").format(
            remaining=remaining
        )
    )
    typer.echo(_("  1. Stop now (remaining files will stay unchanged)."))
    typer.echo(_("  2. Continue renaming the remaining files."))
    prompt = _("Choose an option: ")
    choices = {"1": "cancel", "2": "continue"}

    while True:
        try:
            selection = typer.prompt(prompt, default="2", show_default=False).strip()
        except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
            typer.echo(_("Please confirm how you want to proceed."))
            continue

        if selection in choices:
            return choices[selection]

        typer.echo(_("Invalid option, please try again."))


def _prompt_match_selection(matches: list[dict], source_path: Path) -> int | None:
    typer.echo(_("Multiple proposals for {name}:").format(name=source_path.name))
    for idx, match in enumerate(matches, start=1):
        artist = match.get("artist") or _("Unknown artist")
        title = match.get("title") or _("Unknown title")
        score = _format_score(match.get("score"))
        typer.echo(
            _("  {index}. {artist} - {title} (score {score})").format(
                index=idx,
                artist=artist,
                title=title,
                score=score,
            )
        )

    prompt = _("Select a number (press ENTER to cancel): ")

    while True:
        choice = typer.prompt(prompt, default="", show_default=False).strip()
        if not choice:
            return None

        try:
            idx = int(choice)
        except ValueError:
            typer.echo(_("Invalid selection, please try again."))
            continue

        if 1 <= idx <= len(matches):
            return idx - 1

        typer.echo(_("Index out of range, please try again."))


def _prompt_yes_no(message: str, *, default: bool = True) -> bool:
    suffix = _("[y/N]") if not default else _("[Y/n]")
    prompt = f"{message} {suffix}"
    default_char = "y" if default else "n"

    while True:
        response = typer.prompt(prompt, default=default_char, show_default=False)
        if not response:
            return default
        normalized = response.strip().lower()
        if normalized in {"o", "oui", "y", "yes"}:
            return True
        if normalized in {"n", "non", "no"}:
            return False
        typer.echo(_("Invalid input (y/n)."))


def _prompt_api_key() -> str | None:
    key = typer.prompt(_("AcoustID API key"), show_default=False).strip()
    if not key:
        return None
    confirmation = typer.prompt(_("Confirm the key"), default=key, show_default=False).strip()
    if confirmation != key:
        typer.echo(_("The keys do not match."))
        return None
    return key


def _validate_client_key(key: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        response = requests.get(
            _VALIDATION_ENDPOINT,
            params={"client": key, "trackid": _VALIDATION_TRACK_ID, "json": 1},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, _("Unable to contact AcoustID ({error}).").format(error=exc)

    if response.status_code != 200:
        return False, _("Unexpected HTTP response ({status}).").format(status=response.status_code)

    try:
        data = response.json()
    except ValueError:
        return False, _("Invalid JSON response received from AcoustID.")

    if data.get("status") != "ok":
        error = data.get("message")
        if not error and isinstance(data.get("error"), dict):
            error = data["error"].get("message")
        return False, error or _("Key rejected by AcoustID.")

    return True, ""


def _configure_api_key_interactively(
    existing: AppConfig,
    config_path: Path | None,
    *,
    skip_validation: bool = False,
) -> str | None:
    key = _prompt_api_key()
    if not key:
        return None

    if not skip_validation:
        valid, message = _validate_client_key(key)
        if not valid:
            typer.echo(_("Key validation failed: {message}").format(message=message))
            return None

    updated = AppConfig(
        acoustid_api_key=key,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
    )

    target = write_config(updated, config_path)
    typer.echo(_("AcoustID key stored in {path}").format(path=target))
    return key


@config_app.command(
    "path",
    help=_("Display the path to the configuration file in use."),
)
def config_path(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Print the configuration file path in use."""
    _apply_locale(ctx)
    target = config_path or default_config_path()
    typer.echo(str(target))


@config_app.command(
    "show",
    help=_("Display the main configuration settings."),
)
def config_show(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Show the key configuration settings."""
    _apply_locale(ctx)
    target = config_path or default_config_path()
    try:
        config = load_config(target)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    key = config.acoustid_api_key
    if key:
        masked = key[:4] + "…" + key[-4:] if len(key) > 8 else "…" * len(key)
        typer.echo(_("AcoustID key: {masked}").format(masked=masked))
    else:
        typer.echo(_("AcoustID key: not configured"))
        typer.echo(_("Create or update your key with `recozik config set-key`."))
    cache_state = _("yes") if config.cache_enabled else _("no")
    typer.echo(
        _("Cache enabled: {state} (TTL: {hours} h)").format(
            state=cache_state,
            hours=config.cache_ttl_hours,
        )
    )
    template = config.output_template or "{artist} - {title}"
    typer.echo(_("Default template: {template}").format(template=template))
    path_mode = _("absolute") if config.log_absolute_paths else _("relative")
    typer.echo(
        _("Log format: {format} (paths {mode})").format(
            format=config.log_format,
            mode=path_mode,
        )
    )
    typer.echo(_("File: {path}").format(path=target))


@config_app.command(
    "set-key",
    help=_("Store an AcoustID API key in the configuration."),
)
def config_set_key(
    ctx: typer.Context,
    api_key_arg: str | None = typer.Argument(
        None,
        help=_("AcoustID API key to record."),
    ),
    api_key_opt: str | None = typer.Option(
        None,
        "--api-key",
        "-k",
        help=_("AcoustID API key to record (alternative to the positional argument)."),
    ),
    skip_validation: bool = typer.Option(
        False,
        "--skip-validation/--validate",
        help=_("Skip online validation (not recommended)."),
    ),
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Persist the AcoustID API key into the configuration file."""
    _apply_locale(ctx)
    target_path = config_path or default_config_path()
    try:
        existing = load_config(target_path)
    except RuntimeError:
        existing = AppConfig()

    key = (api_key_opt or api_key_arg or "").strip()

    if key:
        confirmation = typer.prompt(_("Confirm the key"), default=key)
        if confirmation.strip() != key:
            typer.echo(_("The keys do not match. Operation cancelled."))
            raise typer.Exit(code=1)
    else:
        key = _prompt_api_key()
        if not key:
            typer.echo(_("No API key provided."))
            raise typer.Exit(code=1)

    if not skip_validation:
        valid, message = _validate_client_key(key)
        if not valid:
            typer.echo(_("Key validation failed: {message}").format(message=message))
            raise typer.Exit(code=1)

    updated = AppConfig(
        acoustid_api_key=key,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
    )

    target = write_config(updated, config_path)
    typer.echo(_("AcoustID key stored in {path}").format(path=target))


if __name__ == "__main__":  # pragma: no cover
    app()

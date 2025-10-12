"""Implementation of the `identify-batch` CLI command."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import typer

from ..cli_support.deps import get_config_module
from ..cli_support.locale import apply_locale, resolve_template
from ..cli_support.logs import write_log_entry
from ..cli_support.metadata import extract_audio_metadata
from ..cli_support.paths import (
    discover_audio_files,
    normalize_extensions,
    resolve_path,
)
from ..cli_support.prompts import prompt_yes_no
from ..commands.identify import DEFAULT_AUDIO_EXTENSIONS, configure_api_key_interactively
from ..i18n import _


def identify_batch(
    ctx: typer.Context,
    directory: Path = typer.Argument(
        ...,
        help=_("Directory containing audio files to process."),
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
        help=_("Number of results to store per file."),
    ),
    best_only: bool = typer.Option(
        False,
        "--best-only",
        help=_("Store only the top proposal for each file."),
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
    apply_locale(ctx)
    config_module = get_config_module()

    from .. import cli as cli_module

    compute_fingerprint = cli_module.compute_fingerprint
    lookup_recordings = cli_module.lookup_recordings
    fingerprint_error_cls = cli_module.FingerprintError
    acoustid_lookup_error_cls = cli_module.AcoustIDLookupError
    lookup_cache_cls = cli_module.LookupCache
    metadata_extractor = getattr(cli_module, "_extract_audio_metadata", extract_audio_metadata)
    configure_key = getattr(
        cli_module, "_configure_api_key_interactively", configure_api_key_interactively
    )

    resolved_dir = resolve_path(directory)
    if not resolved_dir.is_dir():
        typer.echo(_("Directory not found: {path}").format(path=resolved_dir))
        raise typer.Exit(code=1)

    try:
        config = config_module.load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    apply_locale(ctx, config=config)

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        typer.echo(_("No AcoustID API key configured."))
        if prompt_yes_no(_("Would you like to save it now?"), default=True):
            new_key = configure_key(config, config_path)
            if not new_key:
                typer.echo(_("No key was stored. Operation cancelled."))
                raise typer.Exit(code=1)
            key = new_key
            try:
                config = config_module.load_config(config_path)
            except RuntimeError:
                config = config_module.AppConfig(acoustid_api_key=key)
            apply_locale(ctx, config=config)
        else:
            typer.echo(_("Operation cancelled."))
            raise typer.Exit(code=1)

    template_value = resolve_template(template, config)
    log_format_value = (log_format or config.log_format).lower()
    if log_format_value not in {"text", "jsonl"}:
        typer.echo(_("Invalid log format. Use 'text' or 'jsonl'."))
        raise typer.Exit(code=1)

    use_absolute = config.log_absolute_paths if absolute_paths is None else absolute_paths

    effective_extensions = normalize_extensions(extension)
    if not pattern and not effective_extensions:
        effective_extensions = DEFAULT_AUDIO_EXTENSIONS

    files = list(
        discover_audio_files(
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

    resolved_fpcalc = resolve_path(fpcalc_path) if fpcalc_path else None

    cache = lookup_cache_cls(
        enabled=config.cache_enabled,
        ttl=timedelta(hours=max(config.cache_ttl_hours, 1)),
    )

    use_metadata_fallback = (
        config.metadata_fallback_enabled if metadata_fallback is None else metadata_fallback
    )

    effective_limit = 1 if best_only else limit

    log_path = resolve_path(log_file) if log_file else Path.cwd() / "recozik-batch.log"
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
            except fingerprint_error_cls as exc:
                write_log_entry(
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
                except acoustid_lookup_error_cls as exc:
                    write_log_entry(
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
                metadata_payload = metadata_extractor(file_path) if use_metadata_fallback else None
                write_log_entry(
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
            write_log_entry(
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

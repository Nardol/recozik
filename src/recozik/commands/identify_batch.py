"""Implementation of the `identify-batch` CLI command."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import typer

from .. import audd as audd_module
from ..audd import AudDEnterpriseParams, AudDMode
from ..cli_support.audd_helpers import (
    get_audd_support,
    parse_bool_env,
    parse_float_env,
    parse_int_env,
    parse_int_list_env,
)
from ..cli_support.deps import get_config_module
from ..cli_support.locale import apply_locale, resolve_template
from ..cli_support.logs import write_log_entry
from ..cli_support.metadata import extract_audio_metadata
from ..cli_support.options import resolve_option
from ..cli_support.paths import (
    discover_audio_files,
    normalize_extensions,
    resolve_path,
)
from ..cli_support.prompts import prompt_yes_no
from ..commands.identify import DEFAULT_AUDIO_EXTENSIONS, configure_api_key_interactively
from ..fingerprint import AcoustIDMatch
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
    audd_token: str | None = typer.Option(
        None,
        "--audd-token",
        help=_("AudD API token to use as a fallback when AcoustID returns no match."),
    ),
    use_audd: bool | None = typer.Option(
        None,
        "--use-audd/--no-audd",
        help=_("Enable or disable the AudD integration for this run."),
    ),
    prefer_audd: bool | None = typer.Option(
        None,
        "--prefer-audd/--prefer-acoustid",
        help=_("Try AudD before AcoustID when the integration is enabled."),
    ),
    announce_source: bool | None = typer.Option(
        None,
        "--announce-source/--silent-source",
        help=_("Announce the identification strategy before scanning files."),
    ),
    audd_endpoint_standard: str | None = typer.Option(
        None,
        "--audd-endpoint-standard",
        help=_("Override the AudD standard endpoint URL."),
    ),
    audd_endpoint_enterprise: str | None = typer.Option(
        None,
        "--audd-endpoint-enterprise",
        help=_("Override the AudD enterprise endpoint URL."),
    ),
    audd_mode: AudDMode | None = typer.Option(
        None,
        "--audd-mode",
        help=_("Select AudD mode: standard, enterprise, or auto."),
    ),
    force_enterprise: bool | None = typer.Option(
        None,
        "--force-enterprise/--no-force-enterprise",
        help=_("Force the AudD enterprise endpoint for all lookups."),
    ),
    enterprise_fallback: bool | None = typer.Option(
        None,
        "--audd-enterprise-fallback/--no-audd-enterprise-fallback",
        help=_("Retry the enterprise endpoint when the standard lookup finds no match."),
    ),
    audd_skip: str | None = typer.Option(
        None,
        "--audd-skip",
        help=_("Enterprise: skip the specified 12-second segments (comma-separated values)."),
    ),
    audd_every: float | None = typer.Option(
        None,
        "--audd-every",
        help=_("Enterprise: distance in seconds between analysed segments."),
    ),
    audd_limit: int | None = typer.Option(
        None,
        "--audd-limit",
        help=_("Enterprise: maximum number of matches to return."),
    ),
    audd_snippet_offset: float | None = typer.Option(
        None,
        "--audd-snippet-offset",
        help=_("Seconds from the start before extracting the AudD standard snippet."),
    ),
    audd_snippet_min_level: float | None = typer.Option(
        None,
        "--audd-snippet-min-rms",
        help=_("Warn when the AudD snippet RMS falls below this value."),
    ),
    audd_skip_first: float | None = typer.Option(
        None,
        "--audd-skip-first",
        help=_("Enterprise: number of seconds to skip before analysis."),
    ),
    audd_accurate_offsets: bool | None = typer.Option(
        None,
        "--audd-accurate-offsets/--no-audd-accurate-offsets",
        help=_("Enterprise: enable second-by-second offset detection."),
    ),
    audd_use_timecode: bool | None = typer.Option(
        None,
        "--audd-use-timecode/--no-audd-use-timecode",
        help=_("Enterprise: request formatted timecodes in the response."),
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

    env_values = os.environ
    env_audd_token = env_values.get("AUDD_API_TOKEN", "")
    support = get_audd_support()

    def _parse_env(name: str, parser: Callable[[str, str | None], Any]) -> Any:
        try:
            return parser(name, env_values.get(name))
        except ValueError as exc:  # pragma: no cover - defensive parsing
            typer.echo(
                _("Invalid value for environment variable {name}: {value}").format(
                    name=name,
                    value=env_values.get(name, ""),
                )
            )
            raise typer.Exit(code=1) from exc

    env_endpoint_standard = env_values.get("AUDD_ENDPOINT_STANDARD")
    if env_endpoint_standard is not None:
        env_endpoint_standard = env_endpoint_standard.strip() or None
    env_endpoint_enterprise = env_values.get("AUDD_ENDPOINT_ENTERPRISE")
    if env_endpoint_enterprise is not None:
        env_endpoint_enterprise = env_endpoint_enterprise.strip() or None

    env_mode_value: str | None = None
    env_mode_raw = env_values.get("AUDD_MODE")
    if env_mode_raw:
        candidate = env_mode_raw.strip().lower()
        if candidate not in {mode.value for mode in AudDMode}:
            typer.echo(
                _("Invalid value for environment variable {name}: {value}").format(
                    name="AUDD_MODE",
                    value=env_mode_raw,
                )
            )
            raise typer.Exit(code=1)
        env_mode_value = candidate

    env_force_enterprise = _parse_env("AUDD_FORCE_ENTERPRISE", parse_bool_env)
    env_enterprise_fallback = _parse_env("AUDD_ENTERPRISE_FALLBACK", parse_bool_env)
    env_skip = _parse_env("AUDD_SKIP", parse_int_list_env)
    env_every = _parse_env("AUDD_EVERY", parse_float_env)
    env_limit = _parse_env("AUDD_LIMIT", parse_int_env)
    env_skip_first = _parse_env("AUDD_SKIP_FIRST_SECONDS", parse_float_env)
    env_accurate_offsets = _parse_env("AUDD_ACCURATE_OFFSETS", parse_bool_env)
    env_use_timecode = _parse_env("AUDD_USE_TIMECODE", parse_bool_env)
    env_snippet_offset = _parse_env("AUDD_SNIPPET_OFFSET", parse_float_env)
    env_snippet_min_level = _parse_env("AUDD_SNIPPET_MIN_RMS", parse_float_env)

    fallback_audd_token = (audd_token or env_audd_token or (config.audd_api_token or "")).strip()
    audd_enabled_setting = use_audd if use_audd is not None else config.identify_batch_audd_enabled
    audd_prefer_setting = (
        prefer_audd if prefer_audd is not None else config.identify_batch_audd_prefer
    )
    audd_endpoint_standard_value = resolve_option(
        ctx,
        "audd_endpoint_standard",
        audd_endpoint_standard,
        config.audd_endpoint_standard,
        env_value=env_endpoint_standard,
    )
    if isinstance(audd_endpoint_standard_value, str):
        audd_endpoint_standard_value = audd_endpoint_standard_value.strip()
    audd_endpoint_standard_value = (
        audd_endpoint_standard_value
        or config.audd_endpoint_standard
        or support.default_standard_endpoint
    )

    audd_endpoint_enterprise_value = resolve_option(
        ctx,
        "audd_endpoint_enterprise",
        audd_endpoint_enterprise,
        config.audd_endpoint_enterprise,
        env_value=env_endpoint_enterprise,
    )
    if isinstance(audd_endpoint_enterprise_value, str):
        audd_endpoint_enterprise_value = audd_endpoint_enterprise_value.strip()
    audd_endpoint_enterprise_value = (
        audd_endpoint_enterprise_value
        or config.audd_endpoint_enterprise
        or support.default_enterprise_endpoint
    )

    raw_mode_setting = resolve_option(
        ctx,
        "audd_mode",
        audd_mode,
        config.audd_mode,
        env_value=env_mode_value,
    )
    if isinstance(raw_mode_setting, AudDMode):
        mode_text = raw_mode_setting.value
    else:
        mode_text = str(raw_mode_setting).strip().lower()
    try:
        audd_mode_value = AudDMode(mode_text)
    except ValueError as exc:  # pragma: no cover - defensive
        typer.echo(_("Invalid AudD mode: {value}.").format(value=mode_text))
        raise typer.Exit(code=1) from exc

    force_enterprise_value = resolve_option(
        ctx,
        "force_enterprise",
        force_enterprise,
        config.audd_force_enterprise,
        env_value=env_force_enterprise,
    )
    enterprise_fallback_value = resolve_option(
        ctx,
        "enterprise_fallback",
        enterprise_fallback,
        config.audd_enterprise_fallback,
        env_value=env_enterprise_fallback,
    )

    def _normalize_skip(value: Any) -> tuple[int, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            parsed = parse_int_list_env("AUDD_SKIP", value) or ()
            return tuple(parsed)
        if isinstance(value, (list, tuple)):
            try:
                return tuple(int(item) for item in value)
            except (TypeError, ValueError) as exc:
                raise typer.BadParameter(_("Invalid value for --audd-skip.")) from exc
        raise typer.BadParameter(_("Invalid value for --audd-skip."))

    skip_value = resolve_option(
        ctx,
        "audd_skip",
        audd_skip,
        config.audd_skip,
        env_value=env_skip,
        transform=_normalize_skip,
    )
    if skip_value is None:
        skip_value = ()
    every_value = resolve_option(
        ctx,
        "audd_every",
        audd_every,
        config.audd_every,
        env_value=env_every,
        transform=lambda value: float(value),
    )
    limit_override_value = resolve_option(
        ctx,
        "audd_limit",
        audd_limit,
        config.audd_limit,
        env_value=env_limit,
        transform=lambda value: int(value),
    )
    skip_first_value = resolve_option(
        ctx,
        "audd_skip_first",
        audd_skip_first,
        config.audd_skip_first_seconds,
        env_value=env_skip_first,
        transform=lambda value: float(value),
    )
    accurate_offsets_value = resolve_option(
        ctx,
        "audd_accurate_offsets",
        audd_accurate_offsets,
        config.audd_accurate_offsets,
        env_value=env_accurate_offsets,
    )
    use_timecode_value = resolve_option(
        ctx,
        "audd_use_timecode",
        audd_use_timecode,
        config.audd_use_timecode,
        env_value=env_use_timecode,
    )

    enterprise_params = AudDEnterpriseParams(
        skip=tuple(skip_value),
        every=every_value,
        limit=limit_override_value,
        skip_first_seconds=skip_first_value,
        accurate_offsets=accurate_offsets_value,
        use_timecode=use_timecode_value,
    )

    def _coerce_non_negative(value: float | None, option_name: str) -> float | None:
        if value is None:
            return None
        if value < 0:
            raise typer.BadParameter(
                _("{option} must be zero or greater.").format(option=option_name)
            )
        return value

    snippet_offset_value = resolve_option(
        ctx,
        "audd_snippet_offset",
        audd_snippet_offset,
        config.audd_snippet_offset,
        env_value=env_snippet_offset,
        transform=lambda value: _coerce_non_negative(value, "--audd-snippet-offset"),
    )
    snippet_min_level_value = resolve_option(
        ctx,
        "audd_snippet_min_level",
        audd_snippet_min_level,
        config.audd_snippet_min_level,
        env_value=env_snippet_min_level,
        transform=lambda value: _coerce_non_negative(value, "--audd-snippet-min-rms"),
    )

    audd_available = bool(fallback_audd_token) and audd_enabled_setting

    limit_value = resolve_option(
        ctx,
        "limit",
        limit,
        config.identify_batch_limit,
        transform=lambda value: max(value, 1),
    )

    best_only_value = resolve_option(
        ctx,
        "best_only",
        best_only,
        config.identify_batch_best_only,
    )

    recursive_value = resolve_option(
        ctx,
        "recursive",
        recursive,
        config.identify_batch_recursive,
    )

    log_file_choice = resolve_option(
        ctx,
        "log_file",
        log_file,
        config.identify_batch_log_file,
    )
    if isinstance(log_file_choice, Path):
        log_file_option: Path | None = log_file_choice
    elif isinstance(log_file_choice, str) and log_file_choice:
        log_file_option = Path(log_file_choice)
    else:
        log_file_option = None

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

    env_audd_token = os.environ.get("AUDD_API_TOKEN", "")
    fallback_audd_token = (audd_token or env_audd_token or (config.audd_api_token or "")).strip()
    audd_enabled_setting = use_audd if use_audd is not None else config.identify_batch_audd_enabled
    audd_prefer_setting = (
        prefer_audd if prefer_audd is not None else config.identify_batch_audd_prefer
    )
    audd_available = bool(fallback_audd_token) and audd_enabled_setting
    announce_value = resolve_option(
        ctx,
        "announce_source",
        announce_source,
        config.identify_batch_announce_source,
    )
    if not audd_available:
        if fallback_audd_token:
            strategy_description = _("AcoustID only (AudD disabled).")
        else:
            strategy_description = _("AcoustID only (no AudD token).")
    elif audd_prefer_setting:
        strategy_description = _("AudD first, AcoustID fallback.")
    else:
        strategy_description = _("AcoustID first, AudD fallback.")
    if announce_value:
        typer.echo(
            _("Identification strategy: {description}").format(description=strategy_description),
            err=True,
        )
    audd_error_cls = support.error_cls
    audd_snippet_seconds = int(support.snippet_seconds)

    def determine_primary_mode_for_file(path: Path) -> AudDMode:
        if force_enterprise_value:
            return AudDMode.ENTERPRISE
        if audd_mode_value is AudDMode.AUTO:
            if (
                enterprise_params.skip
                or enterprise_params.every is not None
                or enterprise_params.limit is not None
                or enterprise_params.skip_first_seconds is not None
                or enterprise_params.accurate_offsets
                or enterprise_params.use_timecode
            ):
                return AudDMode.ENTERPRISE
            return AudDMode.STANDARD
        return audd_mode_value

    def run_audd_for_file(
        path: Path,
        display_path: str,
        *,
        will_retry_acoustid: bool,
    ) -> tuple[list[AcoustIDMatch], str | None, str | None, bool]:
        if not audd_available:
            return [], None, None, False

        snippet_announced = False
        snippet_warned = False
        last_error: str | None = None

        def handle_snippet(info: audd_module.SnippetInfo) -> None:
            nonlocal snippet_announced, snippet_warned
            if not snippet_announced:
                if info.offset_seconds > 0:
                    message = _(
                        "Preparing AudD snippet for {path} (~{seconds}s, mono 16 kHz) starting "
                        "at ~{offset}s before upload."
                    ).format(
                        path=display_path,
                        seconds=audd_snippet_seconds,
                        offset=f"{info.offset_seconds:.2f}",
                    )
                    typer.echo(message, err=True)
                else:
                    message = _(
                        "Preparing AudD snippet for {path} (~{seconds}s, mono 16 kHz) before "
                        "upload."
                    ).format(path=display_path, seconds=audd_snippet_seconds)
                    typer.echo(message, err=True)
                snippet_announced = True

            if (
                snippet_min_level_value is not None
                and info.rms < snippet_min_level_value
                and not snippet_warned
            ):
                warning = _(
                    "AudD snippet for {path} has low RMS (~{rms:.4f}); consider adjusting the "
                    "offset or using the enterprise endpoint."
                ).format(path=display_path, rms=info.rms)
                typer.echo(warning, err=True)
                snippet_warned = True

        def _execute(mode: AudDMode) -> list[AcoustIDMatch]:
            nonlocal last_error
            if mode is AudDMode.STANDARD:
                try:
                    return support.recognize_standard(
                        fallback_audd_token,
                        path,
                        endpoint=audd_endpoint_standard_value,
                        snippet_offset=snippet_offset_value or 0.0,
                        snippet_hook=handle_snippet,
                    )
                except audd_error_cls as exc:
                    last_error = str(exc)
                    message = _("AudD lookup failed for {path}: {error}.").format(
                        path=display_path,
                        error=last_error,
                    )
                    if will_retry_acoustid:
                        message = _(
                            "AudD lookup failed for {path}: {error}. Falling back to AcoustID."
                        ).format(path=display_path, error=last_error)
                    typer.echo(message)
                    return []

            try:
                return support.recognize_enterprise(
                    fallback_audd_token,
                    path,
                    endpoint=audd_endpoint_enterprise_value,
                    params=enterprise_params,
                )
            except audd_error_cls as exc:
                last_error = str(exc)
                typer.echo(
                    _("AudD lookup failed for {path}: {error}").format(
                        path=display_path,
                        error=last_error,
                    )
                )
                return []

        primary_mode = determine_primary_mode_for_file(path)
        matches = _execute(primary_mode)
        if matches:
            return matches, _("Source: AudD."), None, True
        if not enterprise_fallback_value:
            return matches, None, last_error, True
        secondary_mode = (
            AudDMode.ENTERPRISE if primary_mode is not AudDMode.ENTERPRISE else AudDMode.STANDARD
        )
        if secondary_mode is primary_mode:
            return matches, None, last_error, True
        secondary_matches = _execute(secondary_mode)
        if secondary_matches:
            return secondary_matches, _("Source: AudD."), None, True
        return secondary_matches, None, last_error, True

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
            recursive=recursive_value,
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

    effective_limit = 1 if best_only_value else limit_value

    log_path = (
        resolve_path(log_file_option) if log_file_option else Path.cwd() / "recozik-batch.log"
    )
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
            match_source = None
            if config.cache_enabled and not refresh:
                cached = cache.get(
                    fingerprint_result.fingerprint,
                    fingerprint_result.duration_seconds,
                )
                if cached is not None:
                    matches = list(cached)
                    match_source = "acoustid"

            audd_note: str | None = None
            audd_error_message: str | None = None
            audd_attempted = False

            if audd_prefer_setting and not matches:
                audd_results, audd_note_candidate, error_message, attempted = run_audd_for_file(
                    file_path,
                    relative_display,
                    will_retry_acoustid=True,
                )
                if attempted:
                    audd_attempted = True
                if audd_results:
                    matches = audd_results
                    audd_note = audd_note_candidate
                    match_source = "audd"
                    typer.echo(_("AudD identified {path}.").format(path=relative_display))
                if error_message:
                    audd_error_message = error_message

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
                if matches and match_source is None:
                    match_source = "acoustid"

            if audd_available and not matches and not audd_attempted:
                audd_results, audd_note_candidate, error_message, attempted = run_audd_for_file(
                    file_path,
                    relative_display,
                    will_retry_acoustid=False,
                )
                if attempted:
                    audd_attempted = True
                if audd_results:
                    matches = audd_results
                    audd_note = audd_note_candidate
                    match_source = "audd"
                    typer.echo(_("AudD identified {path}.").format(path=relative_display))
                if error_message:
                    audd_error_message = error_message

            if not matches:
                metadata_payload = metadata_extractor(file_path) if use_metadata_fallback else None
                note_parts = [_("No match.")]
                if audd_error_message:
                    note_parts.append(
                        _("AudD lookup failed: {error}").format(error=audd_error_message)
                    )
                note_text = " ".join(note_parts)
                write_log_entry(
                    handle,
                    log_format_value,
                    relative_display,
                    [],
                    None,
                    template_value,
                    fingerprint_result,
                    status="unmatched",
                    note=note_text,
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
            note_parts: list[str] = []
            if match_source == "audd" and audd_note:
                note_parts.append(audd_note)
            if audd_error_message and match_source != "audd":
                note_parts.append(_("AudD lookup failed: {error}").format(error=audd_error_message))
            success_note = " ".join(note_parts) if note_parts else None
            write_log_entry(
                handle,
                log_format_value,
                relative_display,
                selected,
                None,
                template_value,
                fingerprint_result,
                note=success_note,
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

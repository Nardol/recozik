"""Implementation of the `identify` CLI command and related helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

import typer

from recozik_core import secrets as secret_store
from recozik_core.audd import AudDEnterpriseParams, AudDMode
from recozik_core.fingerprint import AcoustIDMatch
from recozik_core.i18n import _
from recozik_core.secrets import SecretBackendUnavailableError, SecretStoreError

from .. import cli as cli_module
from ..cli_support.audd_helpers import (
    get_audd_support,
    parse_bool_env,
    parse_float_env,
    parse_int_env,
    parse_int_list_env,
)
from ..cli_support.deps import get_config_module, get_fingerprint_symbols, get_lookup_cache_cls
from ..cli_support.locale import apply_locale, resolve_template
from ..cli_support.logs import format_match_template
from ..cli_support.musicbrainz import (
    MusicBrainzClient,
    MusicBrainzOptions,
    enrich_matches_with_musicbrainz,
)
from ..cli_support.musicbrainz import (
    build_settings as build_musicbrainz_settings,
)
from ..cli_support.options import resolve_option
from ..cli_support.paths import resolve_path
from ..cli_support.prompts import prompt_api_key, prompt_yes_no

if TYPE_CHECKING:
    from recozik_core.audd import SnippetInfo


T = TypeVar("T")


def _cli_override(name: str, default: T) -> T:
    """Return a CLI-level override when tests monkeypatch recozik.cli."""
    cli_symbols = cast("dict[str, Any]", getattr(cli_module, "__dict__", {}))
    return cast(T, cli_symbols.get(name, default))


DEFAULT_AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".opus",
    ".wma",
}
_VALIDATION_TRACK_ID = "9ff43b6a-4f16-427c-93c2-92307ca505e0"
_VALIDATION_ENDPOINT = "https://api.acoustid.org/v2/lookup"


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
    use_musicbrainz: bool | None = typer.Option(
        None,
        "--with-musicbrainz/--without-musicbrainz",
        help=_("Enrich matches with MusicBrainz metadata when possible."),
    ),
    prefer_audd: bool | None = typer.Option(
        None,
        "--prefer-audd/--prefer-acoustid",
        help=_("Try AudD before AcoustID when the integration is enabled."),
    ),
    announce_source: bool | None = typer.Option(
        None,
        "--announce-source/--silent-source",
        help=_("Announce the identification strategy before running."),
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
    musicbrainz_missing_only: bool | None = typer.Option(
        None,
        "--musicbrainz-missing-only/--musicbrainz-always",
        help=_("Query MusicBrainz only when artist/title metadata is missing."),
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
    apply_locale(ctx)
    config_module = get_config_module()
    fingerprint_symbols = get_fingerprint_symbols()
    compute_fingerprint = _cli_override(
        "compute_fingerprint", fingerprint_symbols.compute_fingerprint
    )
    lookup_recordings = _cli_override("lookup_recordings", fingerprint_symbols.lookup_recordings)
    fingerprint_error_cls = _cli_override("FingerprintError", fingerprint_symbols.FingerprintError)
    acoustid_lookup_error_cls = _cli_override(
        "AcoustIDLookupError", fingerprint_symbols.AcoustIDLookupError
    )
    lookup_cache_cls = _cli_override("LookupCache", get_lookup_cache_cls())
    configure_key = getattr(
        cli_module, "_configure_api_key_interactively", configure_api_key_interactively
    )

    resolved_audio = resolve_path(audio_path)
    resolved_fpcalc = resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        config = config_module.load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    apply_locale(ctx, config=config)

    env_values = os.environ
    env_acoustid_key = env_values.get("ACOUSTID_API_KEY", "")
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
    audd_enabled_setting = use_audd if use_audd is not None else config.identify_audd_enabled
    audd_prefer_setting = prefer_audd if prefer_audd is not None else config.identify_audd_prefer
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
    limit_value = resolve_option(
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
        limit=limit_value,
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
    announce_value = resolve_option(
        ctx,
        "announce_source",
        announce_source,
        config.identify_announce_source,
    )

    musicbrainz_enabled_value = resolve_option(
        ctx,
        "use_musicbrainz",
        use_musicbrainz,
        config.musicbrainz_enabled,
    )
    musicbrainz_missing_only_value = resolve_option(
        ctx,
        "musicbrainz_missing_only",
        musicbrainz_missing_only,
        config.musicbrainz_enrich_missing_only,
    )

    strategy_description = None
    if not audd_available:
        if fallback_audd_token:
            strategy_description = _("AcoustID only (AudD disabled).")
        else:
            strategy_description = _("AcoustID only (no AudD token).")
    elif audd_prefer_setting:
        strategy_description = _("AudD first, AcoustID fallback.")
    else:
        strategy_description = _("AcoustID first, AudD fallback.")

    if announce_value and strategy_description:
        typer.echo(
            _("Identification strategy: {description}").format(description=strategy_description),
            err=True,
        )

    limit_value = resolve_option(
        ctx,
        "limit",
        limit,
        config.identify_default_limit,
        transform=lambda value: max(value, 1),
    )

    json_value = resolve_option(
        ctx,
        "json_output",
        json_output,
        config.identify_output_json,
    )

    refresh_value = resolve_option(
        ctx,
        "refresh",
        refresh,
        config.identify_refresh_cache,
    )

    key = (api_key or env_acoustid_key or config.acoustid_api_key or "").strip()
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

    try:
        fingerprint_result = compute_fingerprint(
            resolved_audio,
            fpcalc_path=resolved_fpcalc,
        )
    except fingerprint_error_cls as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    cache = lookup_cache_cls(
        enabled=config.cache_enabled,
        ttl=timedelta(hours=max(config.cache_ttl_hours, 1)),
    )

    musicbrainz_options = MusicBrainzOptions(
        enabled=bool(musicbrainz_enabled_value),
        enrich_missing_only=bool(musicbrainz_missing_only_value),
    )
    musicbrainz_settings = build_musicbrainz_settings(
        app_name=config.musicbrainz_user_agent_app,
        app_version=config.musicbrainz_user_agent_version,
        contact=config.musicbrainz_contact,
        rate_limit_per_second=config.musicbrainz_rate_limit_per_second,
        timeout_seconds=config.musicbrainz_timeout_seconds,
    )
    musicbrainz_client = (
        MusicBrainzClient(musicbrainz_settings) if musicbrainz_options.enabled else None
    )

    matches: list[AcoustIDMatch] | None = None
    match_source = None
    if config.cache_enabled and not refresh_value:
        cached = cache.get(fingerprint_result.fingerprint, fingerprint_result.duration_seconds)
        if cached is not None:
            matches = list(cached)
            match_source = "acoustid"

    error_cls = support.error_cls
    audd_attempted = False

    def apply_musicbrainz_enrichment() -> None:
        nonlocal matches
        if not matches or not musicbrainz_options.enabled:
            return
        enriched = enrich_matches_with_musicbrainz(
            matches,
            options=musicbrainz_options,
            settings=musicbrainz_settings,
            client=musicbrainz_client,
            echo=lambda message: typer.echo(message, err=True),
        )
        if enriched and match_source == "acoustid" and config.cache_enabled and matches is not None:
            cache.set(
                fingerprint_result.fingerprint,
                fingerprint_result.duration_seconds,
                matches,
            )
            cache.save()

    def determine_primary_mode() -> AudDMode:
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

    def run_audd(will_retry_acoustid: bool) -> list[AcoustIDMatch]:
        nonlocal audd_attempted
        audd_attempted = True
        snippet_announced = False
        snippet_warned = False

        def handle_snippet(info: SnippetInfo) -> None:
            nonlocal snippet_announced, snippet_warned
            display_seconds = int(support.snippet_seconds)
            if not snippet_announced:
                if info.offset_seconds > 0:
                    message = _(
                        "Preparing AudD snippet (~{seconds}s, mono 16 kHz) starting at "
                        "~{offset}s before upload."
                    ).format(
                        seconds=display_seconds,
                        offset=f"{info.offset_seconds:.2f}",
                    )
                    typer.echo(message, err=json_value)
                else:
                    message = _(
                        "Preparing AudD snippet (~{seconds}s, mono 16 kHz) before upload."
                    ).format(seconds=display_seconds)
                    typer.echo(message, err=json_value)
                snippet_announced = True

            if (
                snippet_min_level_value is not None
                and info.rms < snippet_min_level_value
                and not snippet_warned
            ):
                warning = _(
                    "AudD snippet RMS is low (~{rms:.4f}); consider adjusting the offset or "
                    "using the enterprise endpoint."
                ).format(rms=info.rms)
                typer.echo(warning, err=True)
                snippet_warned = True

        def _execute(mode: AudDMode) -> list:
            if mode is AudDMode.STANDARD:
                try:
                    return support.recognize_standard(
                        fallback_audd_token,
                        resolved_audio,
                        endpoint=audd_endpoint_standard_value,
                        snippet_offset=snippet_offset_value or 0.0,
                        snippet_hook=handle_snippet,
                    )
                except error_cls as exc:
                    message = _("AudD lookup failed: {error}.").format(error=exc)
                    if will_retry_acoustid:
                        message = _(
                            "AudD lookup failed: {error}. Falling back to AcoustID."
                        ).format(error=exc)
                    typer.echo(message)
                    return cast(list[AcoustIDMatch], [])

            try:
                return support.recognize_enterprise(
                    fallback_audd_token,
                    resolved_audio,
                    endpoint=audd_endpoint_enterprise_value,
                    params=enterprise_params,
                )
            except error_cls as exc:
                typer.echo(_("AudD lookup failed: {error}.").format(error=exc))
                return cast(list[AcoustIDMatch], [])

        primary_mode = determine_primary_mode()
        matches = _execute(primary_mode)
        if matches or not enterprise_fallback_value:
            return matches

        secondary_mode = (
            AudDMode.ENTERPRISE if primary_mode is not AudDMode.ENTERPRISE else AudDMode.STANDARD
        )
        if secondary_mode is primary_mode:
            return matches
        return _execute(secondary_mode)

    if audd_available and audd_prefer_setting and matches is None:
        audd_results = run_audd(will_retry_acoustid=True)
        if audd_results:
            matches = audd_results
            match_source = "audd"
        else:
            matches = None

    if matches is None:
        try:
            matches = list(lookup_recordings(key, fingerprint_result))
        except acoustid_lookup_error_cls as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        if config.cache_enabled:
            cache.set(fingerprint_result.fingerprint, fingerprint_result.duration_seconds, matches)
            cache.save()
        match_source = "acoustid" if matches else None
    elif match_source is None:
        # Matches may come from cache; assume they were produced by AcoustID.
        match_source = "acoustid"

    if audd_available and not matches and not audd_attempted:
        audd_results = run_audd(will_retry_acoustid=False)
        if audd_results:
            matches = audd_results
            match_source = "audd"

    if matches:
        apply_musicbrainz_enrichment()

    if not matches:
        typer.echo(_("No matches found."))
        cache.save()
        return

    if json_value:
        matches = matches[:limit_value]
        payload = []
        for match in matches:
            record = match.to_dict()
            record["source"] = match_source
            payload.append(record)
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        cache.save()
        return

    template_value = resolve_template(template, config)
    matches = _deduplicate_by_template(matches, template_value)
    matches = matches[:limit_value]

    for idx, match in enumerate(matches, start=1):
        typer.echo(_("Result {index}: score {score:.2f}").format(index=idx, score=match.score))
        typer.echo(f"  {format_match_template(match, template_value)}")
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


def _deduplicate_by_template(
    matches: list[AcoustIDMatch],
    template_value: str,
) -> list[AcoustIDMatch]:
    """Return matches preserving order but removing identical template outputs."""
    seen: set[str] = set()
    unique = []

    for match in matches:
        rendered = format_match_template(match, template_value)
        fingerprint = rendered.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(match)

    return unique


def configure_api_key_interactively(
    existing,
    config_path: Path | None,
    *,
    skip_validation: bool = False,
) -> str | None:
    """Prompt the user for an API key and persist it to the config."""
    config_module = get_config_module()
    key = prompt_api_key()
    if not key:
        return None

    if not skip_validation:
        valid, message = validate_client_key(key)
        if not valid:
            typer.echo(_("Key validation failed: {message}").format(message=message))
            return None

    try:
        secret_store.set_acoustid_api_key(key)
    except SecretBackendUnavailableError as exc:
        typer.echo(
            _("Unable to store the key securely: {error}").format(error=str(exc)),
            err=True,
        )
        return None
    except SecretStoreError as exc:
        typer.echo(_("Failed to store the AcoustID key: {error}").format(error=exc), err=True)
        return None

    existing.acoustid_api_key = key
    config_module.write_config(existing, config_path)
    typer.echo(_("AcoustID key stored securely."))
    return key


def validate_client_key(key: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Validate an AcoustID client key via the public API."""
    import requests

    try:
        params: dict[str, str | int] = {
            "client": key,
            "trackid": _VALIDATION_TRACK_ID,
            "json": 1,
        }
        response = requests.get(
            _VALIDATION_ENDPOINT,
            params=dict(params),
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

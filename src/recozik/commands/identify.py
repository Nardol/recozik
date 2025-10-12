"""Implementation of the `identify` CLI command and related helpers."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import typer

from ..cli_support.deps import get_config_module
from ..cli_support.locale import apply_locale, resolve_template
from ..cli_support.logs import format_match_template
from ..cli_support.paths import resolve_path
from ..cli_support.prompts import prompt_api_key, prompt_yes_no
from ..i18n import _

DEFAULT_AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus"}
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
    from .. import cli as cli_module

    compute_fingerprint = cli_module.compute_fingerprint
    lookup_recordings = cli_module.lookup_recordings
    fingerprint_error_cls = cli_module.FingerprintError
    acoustid_lookup_error_cls = cli_module.AcoustIDLookupError
    lookup_cache_cls = cli_module.LookupCache
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

    matches = None
    if config.cache_enabled and not refresh:
        matches = cache.get(fingerprint_result.fingerprint, fingerprint_result.duration_seconds)

    if matches is None:
        try:
            matches = lookup_recordings(key, fingerprint_result)
        except acoustid_lookup_error_cls as exc:
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

    template_value = resolve_template(template, config)

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

    updated = config_module.AppConfig(
        acoustid_api_key=key,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
    )

    target = config_module.write_config(updated, config_path)
    typer.echo(_("AcoustID key stored in {path}").format(path=target))
    return key


def validate_client_key(key: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Validate an AcoustID client key via the public API."""
    import requests

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

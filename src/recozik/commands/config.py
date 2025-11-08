"""Config-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from recozik_core import secrets as secret_store
from recozik_core.i18n import _
from recozik_core.secrets import SecretBackendUnavailableError, SecretStoreError

from ..cli_support.deps import get_config_module
from ..cli_support.locale import apply_locale
from ..cli_support.prompts import prompt_api_key, prompt_service_token
from .identify import validate_client_key


def config_path(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Print the configuration file path in use."""
    apply_locale(ctx)
    config_module = get_config_module()
    target = config_path or config_module.default_config_path()
    typer.echo(str(target))


def config_show(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Show the key configuration settings."""
    apply_locale(ctx)
    config_module = get_config_module()
    target = config_path or config_module.default_config_path()
    try:
        config = config_module.load_config(target)
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

    audd_token = config.audd_api_token
    if audd_token:
        masked_token = (
            audd_token[:4] + "…" + audd_token[-4:] if len(audd_token) > 8 else "…" * len(audd_token)
        )
        typer.echo(_("AudD token: {masked}").format(masked=masked_token))
    else:
        typer.echo(_("AudD token: not configured"))
        typer.echo(_("Set it with `recozik config set-audd-token` when you are ready."))

    typer.echo(
        _("AudD endpoints: standard {standard}, enterprise {enterprise}").format(
            standard=config.audd_endpoint_standard,
            enterprise=config.audd_endpoint_enterprise,
        )
    )

    force_state = _("yes") if config.audd_force_enterprise else _("no")
    fallback_state = _("yes") if config.audd_enterprise_fallback else _("no")
    typer.echo(
        _("AudD mode: {mode} (force enterprise {force}, fallback {fallback})").format(
            mode=config.audd_mode,
            force=force_state,
            fallback=fallback_state,
        )
    )

    skip_display = (
        ", ".join(str(value) for value in config.audd_skip) if config.audd_skip else _("none")
    )
    every_display = str(config.audd_every) if config.audd_every is not None else _("unset")
    limit_display = str(config.audd_limit) if config.audd_limit is not None else _("unset")
    skip_first_display = (
        str(config.audd_skip_first_seconds)
        if config.audd_skip_first_seconds is not None
        else _("unset")
    )
    accurate_offsets_state = _("yes") if config.audd_accurate_offsets else _("no")
    timecode_state = _("yes") if config.audd_use_timecode else _("no")

    message_template = _(
        "AudD enterprise options: skip {skip}, every {every}, limit {limit}, "
        "skip_first {skip_first}, accurate_offsets {accurate}, timecode {timecode}"
    )
    typer.echo(
        message_template.format(
            skip=skip_display,
            every=every_display,
            limit=limit_display,
            skip_first=skip_first_display,
            accurate=accurate_offsets_state,
            timecode=timecode_state,
        )
    )

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
    identify_audd_state = _("yes") if config.identify_audd_enabled else _("no")
    identify_prefer_state = _("yes") if config.identify_audd_prefer else _("no")
    identify_announce_state = _("yes") if config.identify_announce_source else _("no")
    typer.echo(
        _("Identify strategy: AudD {enabled}, prefer {prefer}, announce {announce}").format(
            enabled=identify_audd_state,
            prefer=identify_prefer_state,
            announce=identify_announce_state,
        )
    )
    batch_audd_state = _("yes") if config.identify_batch_audd_enabled else _("no")
    batch_prefer_state = _("yes") if config.identify_batch_audd_prefer else _("no")
    batch_announce_state = _("yes") if config.identify_batch_announce_source else _("no")
    typer.echo(
        _("Identify-batch strategy: AudD {enabled}, prefer {prefer}, announce {announce}").format(
            enabled=batch_audd_state,
            prefer=batch_prefer_state,
            announce=batch_announce_state,
        )
    )
    typer.echo(_("File: {path}").format(path=target))


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
    clear: bool = typer.Option(
        False,
        "--clear",
        help=_("Remove the stored AcoustID key."),
    ),
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Persist the AcoustID API key into the configuration file."""
    apply_locale(ctx)
    config_module = get_config_module()
    target_path = config_path or config_module.default_config_path()
    try:
        existing = config_module.load_config(target_path)
    except RuntimeError:
        existing = config_module.AppConfig()

    if clear:
        key: str | None = None
    else:
        key = (api_key_opt or api_key_arg or "").strip()

        if key:
            confirmation = typer.prompt(_("Confirm the key"), default=key)
            if confirmation.strip() != key:
                typer.echo(_("The keys do not match. Operation cancelled."))
                raise typer.Exit(code=1)
        else:
            key = prompt_api_key()
            if not key:
                typer.echo(_("No API key provided."))
                raise typer.Exit(code=1)

        if not skip_validation:
            valid, message = validate_client_key(key)
            if not valid:
                typer.echo(_("Key validation failed: {message}").format(message=message))
                raise typer.Exit(code=1)

    try:
        secret_store.set_acoustid_api_key(key)
    except SecretBackendUnavailableError as exc:
        if key is None:
            typer.echo(
                _("Unable to remove the key securely: {error}").format(error=str(exc)),
                err=True,
            )
        else:
            typer.echo(
                _("Unable to store the key securely: {error}").format(error=str(exc)),
                err=True,
            )
            typer.echo(
                _(
                    "Install a system keyring backend or export the "
                    "ACOUSTID_API_KEY environment variable."
                ),
                err=True,
            )
        raise typer.Exit(code=1) from exc
    except SecretStoreError as exc:
        if key is None:
            typer.echo(_("Failed to remove the AcoustID key: {error}").format(error=exc), err=True)
        else:
            typer.echo(_("Failed to store the AcoustID key: {error}").format(error=exc), err=True)
        raise typer.Exit(code=1) from exc

    existing.acoustid_api_key = key
    target = config_module.write_config(existing, config_path)
    if key is None:
        typer.echo(_("AcoustID key removed from {path}").format(path=target))
    else:
        typer.echo(_("AcoustID key stored securely (config: {path})").format(path=target))


def config_set_audd_token(
    ctx: typer.Context,
    token_arg: str | None = typer.Argument(
        None,
        help=_("AudD API token to record."),
    ),
    token_opt: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help=_("AudD API token to record (alternative to the positional argument)."),
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help=_("Remove the stored AudD token."),
    ),
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Persist or remove the AudD API token."""
    apply_locale(ctx)
    config_module = get_config_module()
    target_path = config_path or config_module.default_config_path()
    try:
        existing = config_module.load_config(target_path)
    except RuntimeError:
        existing = config_module.AppConfig()

    if clear:
        token: str | None = None
    else:
        token = (token_opt or token_arg or "").strip()
        if token:
            confirmation = typer.prompt(_("Confirm the token"), default=token, show_default=False)
            if confirmation.strip() != token:
                typer.echo(_("The tokens do not match. Operation cancelled."))
                raise typer.Exit(code=1)
        else:
            token = prompt_service_token(_("AudD API token"))
            if not token:
                typer.echo(_("No AudD token provided."))
                raise typer.Exit(code=1)

    try:
        secret_store.set_audd_api_token(token)
    except SecretBackendUnavailableError as exc:
        if token is None:
            typer.echo(
                _("Unable to remove the token securely: {error}").format(error=str(exc)),
                err=True,
            )
        else:
            typer.echo(
                _("Unable to store the token securely: {error}").format(error=str(exc)),
                err=True,
            )
            typer.echo(
                _(
                    "Install a system keyring backend or export the "
                    "AUDD_API_TOKEN environment variable."
                ),
                err=True,
            )
        raise typer.Exit(code=1) from exc
    except SecretStoreError as exc:
        if token is None:
            typer.echo(_("Failed to remove the AudD token: {error}").format(error=exc), err=True)
        else:
            typer.echo(_("Failed to store the AudD token: {error}").format(error=exc), err=True)
        raise typer.Exit(code=1) from exc

    existing.audd_api_token = token
    target = config_module.write_config(existing, config_path)
    if token is None:
        typer.echo(_("AudD token removed (config: {path})").format(path=target))
    else:
        typer.echo(_("AudD token stored securely (config: {path})").format(path=target))


def config_clear_secrets(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Delete all stored credentials from the keyring and config."""
    apply_locale(ctx)
    config_module = get_config_module()
    target_path = config_path or config_module.default_config_path()
    try:
        config = config_module.load_config(target_path)
    except RuntimeError:
        config = config_module.AppConfig()

    removal_failed = False
    removed_key = False
    removed_token = False

    try:
        secret_store.set_acoustid_api_key(None)
        config.acoustid_api_key = None
        removed_key = True
    except (SecretBackendUnavailableError, SecretStoreError) as exc:
        removal_failed = True
        typer.echo(_("Failed to remove the AcoustID key: {error}").format(error=exc), err=True)

    try:
        secret_store.set_audd_api_token(None)
        config.audd_api_token = None
        removed_token = True
    except (SecretBackendUnavailableError, SecretStoreError) as exc:
        removal_failed = True
        typer.echo(_("Failed to remove the AudD token: {error}").format(error=exc), err=True)

    target = config_module.write_config(config, config_path)
    if removed_key:
        typer.echo(_("AcoustID key removed from {path}").format(path=target))
    if removed_token:
        typer.echo(_("AudD token removed (config: {path})").format(path=target))

    if removal_failed:
        raise typer.Exit(code=1)

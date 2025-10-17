"""Config-related CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ..cli_support.deps import get_config_module
from ..cli_support.locale import apply_locale
from ..cli_support.prompts import prompt_api_key, prompt_service_token
from ..i18n import _
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
    apply_locale(ctx)
    config_module = get_config_module()
    target_path = config_path or config_module.default_config_path()
    try:
        existing = config_module.load_config(target_path)
    except RuntimeError:
        existing = config_module.AppConfig()

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

    updated = config_module.AppConfig(
        acoustid_api_key=key,
        audd_api_token=existing.audd_api_token,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
        metadata_fallback_enabled=existing.metadata_fallback_enabled,
        locale=existing.locale,
        rename_log_cleanup=existing.rename_log_cleanup,
    )

    target = config_module.write_config(updated, config_path)
    typer.echo(_("AcoustID key stored in {path}").format(path=target))


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

    updated = config_module.AppConfig(
        acoustid_api_key=existing.acoustid_api_key,
        audd_api_token=token,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
        metadata_fallback_enabled=existing.metadata_fallback_enabled,
        locale=existing.locale,
        rename_log_cleanup=existing.rename_log_cleanup,
    )

    target = config_module.write_config(updated, config_path)
    if token is None:
        typer.echo(_("AudD token removed from {path}").format(path=target))
    else:
        typer.echo(_("AudD token stored in {path}").format(path=target))

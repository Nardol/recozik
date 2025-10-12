"""Locale helpers for the CLI."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import typer

from ..i18n import detect_system_locale, resolve_preferred_locale, set_locale

if TYPE_CHECKING:
    from ..config import AppConfig

ENV_LOCALE_VAR = "RECOZIK_LOCALE"


def apply_locale(
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

    env_locale = os.environ.get(ENV_LOCALE_VAR)
    config_locale = config.locale if config else None

    final_locale = resolve_preferred_locale(
        override,
        ctx_locale,
        env_locale,
        config_locale,
        detect_system_locale(),
    )
    set_locale(final_locale)


def resolve_template(template: str | None, config: AppConfig) -> str:
    """Return the template chosen by the user or fall back to defaults."""
    if template:
        return template
    if config.output_template:
        return config.output_template
    return "{artist} - {title}"

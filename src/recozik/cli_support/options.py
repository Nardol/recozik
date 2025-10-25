"""Helpers for reconciling CLI options with configuration defaults."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import typer
from click.core import ParameterSource

T = TypeVar("T")
U = TypeVar("U")


def resolve_option(
    ctx: typer.Context,
    param_name: str,
    cli_value: T,
    default_value: U,
    *,
    transform: Callable[[T], U] | None = None,
) -> U:
    """Return the effective option value honoring configuration defaults."""
    source = ctx.get_parameter_source(param_name)
    if source is ParameterSource.DEFAULT:
        return default_value
    if transform is not None:
        return transform(cli_value)
    return cast(U, cli_value)


__all__ = ["resolve_option"]

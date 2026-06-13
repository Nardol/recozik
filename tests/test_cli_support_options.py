# ruff: noqa: D103
"""Tests for CLI option resolution helpers."""

from __future__ import annotations

from click.core import ParameterSource

from recozik.cli_support.options import resolve_option


class _DummyContext:
    def __init__(self, source: ParameterSource | None) -> None:
        self.source = source

    def get_parameter_source(self, _name: str) -> ParameterSource | None:
        return self.source


class _AlternateDefaultSource:
    name = "DEFAULT"


class _AlternateDefaultContext:
    def get_parameter_source(self, _name: str) -> _AlternateDefaultSource:
        return _AlternateDefaultSource()


def test_resolve_option_accepts_click_compatible_default_source() -> None:
    ctx = _AlternateDefaultContext()

    assert resolve_option(ctx, "value", False, True) is True


def test_resolve_option_treats_none_cli_value_as_absent() -> None:
    ctx = _DummyContext(ParameterSource.COMMANDLINE)

    assert resolve_option(ctx, "value", None, 3, transform=int) == 3


def test_resolve_option_treats_missing_source_as_absent() -> None:
    ctx = _DummyContext(None)

    assert resolve_option(ctx, "value", False, True) is True


def test_resolve_option_prefers_env_when_cli_value_is_absent() -> None:
    ctx = _DummyContext(ParameterSource.COMMANDLINE)

    assert resolve_option(ctx, "value", None, 3, env_value="4", transform=int) == 4

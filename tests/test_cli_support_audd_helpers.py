# ruff: noqa: D103
"""Tests for AudD helper utilities used across CLI commands."""

from __future__ import annotations

import pytest

from recozik.cli_support import audd_helpers


def test_parse_bool_env_accepts_common_aliases() -> None:
    assert audd_helpers.parse_bool_env("TEST", "1") is True
    assert audd_helpers.parse_bool_env("TEST", "false") is False
    assert audd_helpers.parse_bool_env("TEST", " yes ") is True
    assert audd_helpers.parse_bool_env("TEST", "OFF") is False


def test_parse_bool_env_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        audd_helpers.parse_bool_env("TEST", "maybe")


def test_parse_float_env_handles_whitespace() -> None:
    assert audd_helpers.parse_float_env("F", " 1.25 ") == 1.25
    assert audd_helpers.parse_float_env("F", "") is None
    assert audd_helpers.parse_float_env("F", None) is None


def test_parse_float_env_errors_on_bad_number() -> None:
    with pytest.raises(ValueError):
        audd_helpers.parse_float_env("FLOAT", "abc")


def test_parse_int_env_returns_int() -> None:
    assert audd_helpers.parse_int_env("I", " 10 ") == 10
    assert audd_helpers.parse_int_env("I", "") is None


def test_parse_int_env_errors_on_invalid_number() -> None:
    with pytest.raises(ValueError):
        audd_helpers.parse_int_env("I", "3.14")


def test_parse_int_list_env_accepts_comma_values() -> None:
    assert audd_helpers.parse_int_list_env("L", "1, 2 ,3") == (1, 2, 3)
    assert audd_helpers.parse_int_list_env("L", "") == ()
    assert audd_helpers.parse_int_list_env("L", None) is None


def test_parse_int_list_env_errors_on_non_numeric() -> None:
    with pytest.raises(ValueError):
        audd_helpers.parse_int_list_env("L", "1, X")

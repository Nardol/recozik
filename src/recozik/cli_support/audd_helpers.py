"""Lazy helpers exposing AudD integration primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from ..audd import AudDEnterpriseParams, SnippetInfo

from ..fingerprint import AcoustIDMatch

_PathLike = TypeVar("_PathLike", bound=Path)


@dataclass(frozen=True)
class AudDSupport:
    """Container holding the functions and constants required for AudD lookups."""

    standard_max_bytes: int
    enterprise_max_bytes: int
    snippet_seconds: float
    default_standard_endpoint: str
    default_enterprise_endpoint: str
    recognize_standard: Callable[
        [str, Path, str | None, float | None, float | None, Callable[[SnippetInfo], None] | None],
        list[AcoustIDMatch],
    ]
    recognize_enterprise: Callable[
        [str, Path, str | None, float | None, AudDEnterpriseParams | None], list[AcoustIDMatch]
    ]
    error_cls: type[Exception]
    enterprise_params_cls: type[AudDEnterpriseParams]


@lru_cache(maxsize=1)
def get_audd_support() -> AudDSupport:
    """Return cached AudD utilities without paying the import cost on startup."""
    from .. import audd as audd_module

    def _recognize_standard(
        token: str,
        path: Path,
        endpoint: str | None = None,
        timeout: float | None = None,
        snippet_offset: float | None = None,
        snippet_hook: Callable[[audd_module.SnippetInfo], None] | None = None,
    ) -> list[AcoustIDMatch]:
        return audd_module.recognize_with_audd(
            token,
            path,
            endpoint=endpoint or audd_module.DEFAULT_ENDPOINT,
            timeout=timeout or 20.0,
            use_enterprise=False,
            snippet_offset=snippet_offset,
            snippet_hook=snippet_hook,
        )

    def _recognize_enterprise(
        token: str,
        path: Path,
        endpoint: str | None = None,
        timeout: float | None = None,
        params: AudDEnterpriseParams | None = None,
    ) -> list[AcoustIDMatch]:
        return audd_module.recognize_with_audd(
            token,
            path,
            endpoint=endpoint or audd_module.ENTERPRISE_ENDPOINT,
            timeout=timeout or 20.0,
            use_enterprise=True,
            enterprise_params=params or audd_module.AudDEnterpriseParams(),
        )

    return AudDSupport(
        standard_max_bytes=audd_module.MAX_AUDD_BYTES,
        enterprise_max_bytes=audd_module.MAX_AUDD_ENTERPRISE_BYTES,
        snippet_seconds=audd_module.SNIPPET_DURATION_SECONDS,
        default_standard_endpoint=audd_module.DEFAULT_ENDPOINT,
        default_enterprise_endpoint=audd_module.ENTERPRISE_ENDPOINT,
        recognize_standard=_recognize_standard,
        recognize_enterprise=_recognize_enterprise,
        error_cls=audd_module.AudDLookupError,
        enterprise_params_cls=audd_module.AudDEnterpriseParams,
    )


__all__ = [
    "AudDSupport",
    "get_audd_support",
    "parse_bool_env",
    "parse_float_env",
    "parse_int_env",
    "parse_int_list_env",
]


def parse_bool_env(name: str, value: str | None) -> bool | None:
    """Convert an environment variable to a boolean."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {name}: {value}")


def parse_float_env(name: str, value: str | None) -> float | None:
    """Convert an environment variable to a float."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid number for {name}: {value}") from exc


def parse_int_env(name: str, value: str | None) -> int | None:
    """Convert an environment variable to an integer."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}: {value}") from exc


def parse_int_list_env(name: str, value: str | None) -> tuple[int, ...] | None:
    """Convert an environment variable to a tuple of integers."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return ()
    parts = [part.strip() for part in text.split(",") if part.strip()]
    parsed: list[int] = []
    for part in parts:
        try:
            parsed.append(int(part))
        except ValueError as exc:
            raise ValueError(f"Invalid integer list for {name}: {value}") from exc
    return tuple(parsed)

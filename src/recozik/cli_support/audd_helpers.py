"""Lazy helpers exposing AudD integration primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from ..fingerprint import AcoustIDMatch

_PathLike = TypeVar("_PathLike", bound=Path)


@dataclass(frozen=True)
class AudDSupport:
    """Container holding the functions and constants required for AudD lookups."""

    max_bytes: int
    snippet_seconds: float
    recognize: Callable[[str, Path], list[AcoustIDMatch]]
    needs_snippet: Callable[[Path], bool]
    error_cls: type[Exception]


@lru_cache(maxsize=1)
def get_audd_support() -> AudDSupport:
    """Return cached AudD utilities without paying the import cost on startup."""
    from .. import audd as audd_module

    return AudDSupport(
        max_bytes=audd_module.MAX_AUDD_BYTES,
        snippet_seconds=audd_module.SNIPPET_DURATION_SECONDS,
        recognize=lambda token, path: audd_module.recognize_with_audd(token, path),
        needs_snippet=lambda path: audd_module.needs_audd_snippet(path),
        error_cls=audd_module.AudDLookupError,
    )


__all__ = ["AudDSupport", "get_audd_support"]

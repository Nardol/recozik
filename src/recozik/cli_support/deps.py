"""Lazy accessors for modules and classes used by CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .metadata import MUTAGEN_AVAILABLE

__all__ = [
    "MUTAGEN_AVAILABLE",
    "FingerprintSymbols",
    "get_config_module",
    "get_fingerprint_symbols",
    "get_lookup_cache_cls",
]

_UNINITIALIZED = object()

_config_module: ModuleType | object = _UNINITIALIZED
_lookup_cache_cls: type | object = _UNINITIALIZED
_fingerprint_symbols: FingerprintSymbols | object = _UNINITIALIZED


def get_config_module():
    """Return the lazily-imported configuration module."""
    global _config_module
    if _config_module is _UNINITIALIZED:
        from .. import config as config_module

        _config_module = config_module
    return _config_module


def get_lookup_cache_cls():
    """Return the lazily-imported LookupCache class."""
    global _lookup_cache_cls
    if _lookup_cache_cls is _UNINITIALIZED:
        from ..cache import LookupCache

        _lookup_cache_cls = LookupCache
    return _lookup_cache_cls


@dataclass(frozen=True)
class FingerprintSymbols:
    """Container holding lazily-imported fingerprint helpers."""

    compute_fingerprint: Any
    lookup_recordings: Any
    FingerprintResult: type
    FingerprintError: type
    AcoustIDMatch: type
    AcoustIDLookupError: type


def get_fingerprint_symbols() -> FingerprintSymbols:
    """Return functions and classes from the fingerprint module."""
    global _fingerprint_symbols
    if _fingerprint_symbols is _UNINITIALIZED:
        from .. import fingerprint as fingerprint_module

        _fingerprint_symbols = FingerprintSymbols(
            compute_fingerprint=fingerprint_module.compute_fingerprint,
            lookup_recordings=fingerprint_module.lookup_recordings,
            FingerprintResult=fingerprint_module.FingerprintResult,
            FingerprintError=fingerprint_module.FingerprintError,
            AcoustIDMatch=fingerprint_module.AcoustIDMatch,
            AcoustIDLookupError=fingerprint_module.AcoustIDLookupError,
        )
    return _fingerprint_symbols

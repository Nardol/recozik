"""Compatibility shim exposing :mod:`recozik_core.cache`."""

from __future__ import annotations

import sys

from recozik_core import cache as _core_cache

sys.modules[__name__] = _core_cache

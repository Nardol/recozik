"""Compatibility shim exposing :mod:`recozik_core.audd`."""

from __future__ import annotations

import sys

from recozik_core import audd as _core_audd

sys.modules[__name__] = _core_audd

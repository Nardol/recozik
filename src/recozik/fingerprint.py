"""Compatibility shim exposing :mod:`recozik_core.fingerprint`."""

from __future__ import annotations

import sys

from recozik_core import fingerprint as _core_fingerprint

sys.modules[__name__] = _core_fingerprint

"""Compatibility shim exposing :mod:`recozik_core.i18n`."""

from __future__ import annotations

import sys

from recozik_core import i18n as _core_i18n

sys.modules[__name__] = _core_i18n

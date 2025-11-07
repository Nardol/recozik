"""Compatibility shim exposing :mod:`recozik_core.config`."""

from __future__ import annotations

import sys

from recozik_core import config as _core_config

sys.modules[__name__] = _core_config

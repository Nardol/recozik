"""Compatibility shim exposing :mod:`recozik_core.i18n`."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from recozik_core import i18n as _core_i18n

if TYPE_CHECKING:  # pragma: no cover - typing aid
    _: Any
    set_locale: Any

sys.modules[__name__] = _core_i18n

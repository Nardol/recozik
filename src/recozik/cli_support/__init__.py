"""Compatibility shim re-exporting service-level CLI helpers."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from recozik_services.cli_support.__init__ import *  # noqa: F403

from recozik_services.cli_support.__init__ import *  # noqa: F403

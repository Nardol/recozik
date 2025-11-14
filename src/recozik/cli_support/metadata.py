"""Re-export metadata helpers from ``recozik_services``."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from recozik_services.cli_support.metadata import *  # noqa: F403

from recozik_services.cli_support.metadata import *  # noqa: F403

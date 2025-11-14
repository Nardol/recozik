"""Re-export completion helpers from the service layer."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from recozik_services.cli_support.completion import *  # noqa: F403

from recozik_services.cli_support.completion import *  # noqa: F403

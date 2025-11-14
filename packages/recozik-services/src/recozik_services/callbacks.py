"""Common callback protocol used by service runners."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ServiceCallbacks(Protocol):
    """Minimal interface for emitting user-visible messages."""

    def info(self, message: str) -> None:
        """Display an informational message."""

    def warning(self, message: str) -> None:
        """Display a warning-level message."""

    def error(self, message: str) -> None:
        """Display an error-level message."""


@dataclass(slots=True)
class PrintCallbacks:
    """Default callbacks writing everything to stdout/stderr."""

    def info(self, message: str) -> None:  # pragma: no cover - console helper
        """Display an informational message."""
        print(message)

    def warning(self, message: str) -> None:  # pragma: no cover - console helper
        """Display a warning message."""
        print(message)

    def error(self, message: str) -> None:  # pragma: no cover - console helper
        """Display an error message."""
        print(message)


__all__ = ["PrintCallbacks", "ServiceCallbacks"]

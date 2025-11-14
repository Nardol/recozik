"""CLI callback bridge for service layer events."""

from __future__ import annotations

from dataclasses import dataclass

import typer
from recozik_services.callbacks import ServiceCallbacks


@dataclass(slots=True)
class TyperCallbacks(ServiceCallbacks):
    """Forward service messages to Typer, optionally forcing stdout."""

    use_stderr: bool = True
    warning_stderr: bool = True

    def info(self, message: str) -> None:
        typer.echo(message, err=self.use_stderr)

    def warning(self, message: str) -> None:
        typer.echo(message, err=self.warning_stderr)

    def error(self, message: str) -> None:
        typer.echo(message, err=True)


__all__ = ["TyperCallbacks"]

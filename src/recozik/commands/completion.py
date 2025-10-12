"""Shell completion related CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
import typer
from typer.completion import get_completion_script as generate_completion_script
from typer.completion import install as install_completion

from ..cli_support.completion import (
    completion_hint,
    completion_script_path,
    completion_source_command,
    completion_uninstall_hint,
    detect_shell,
    normalize_shell,
)
from ..cli_support.locale import apply_locale
from ..cli_support.paths import resolve_path
from ..i18n import _

ShellDetectorFn = Callable[[str | None], str | None]

_shellingham_helper: Any | None = None


def configure_shellingham_helper(helper: Any | None) -> None:
    """Register the optional shell detection helper exposed by Typer."""
    global _shellingham_helper
    _shellingham_helper = helper


def _resolve_detector(detector: ShellDetectorFn | None) -> ShellDetectorFn:
    helper = _shellingham_helper
    if detector is not None:
        return detector
    return lambda value: detect_shell(value, detector=helper)


def completion_install(
    ctx: typer.Context,
    *,
    shell: str | None,
    print_command: bool,
    no_write: bool,
    output: Path | None,
    detector: ShellDetectorFn | None = None,
    installer: Callable[..., tuple[str, Path]] = install_completion,
    script_generator: Callable[..., str] = generate_completion_script,
) -> None:
    """Install the shell completion script for the active shell."""
    apply_locale(ctx)
    target_shell = normalize_shell(shell)
    resolve = _resolve_detector(detector)

    if sum(bool(flag) for flag in (print_command, no_write, output is not None)) > 1:
        typer.echo(_("Use only one of --print-command, --no-write, or --output."))
        raise typer.Exit(code=1)

    if no_write:
        detected_shell = resolve(target_shell)
        if not detected_shell:
            typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
            raise typer.Exit(code=1)

        script = script_generator(
            prog_name="recozik",
            complete_var="_RECOZIK_COMPLETE",
            shell=detected_shell,
        )
        typer.echo(script)
        return

    if output is not None:
        detected_shell = resolve(target_shell)
        if not detected_shell:
            typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
            raise typer.Exit(code=1)

        script = script_generator(
            prog_name="recozik",
            complete_var="_RECOZIK_COMPLETE",
            shell=detected_shell,
        )
        resolved_path = resolve_path(output)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(script, encoding="utf-8")
        typer.echo(_("Completion script written to {path}").format(path=resolved_path))
        typer.echo(_("Add it to your shell configuration if needed."))
        return

    try:
        detected_shell, script_path = installer(shell=target_shell, prog_name="recozik")
    except click.exceptions.Exit as exc:
        typer.echo(_("Shell not supported for auto-completion."))
        raise typer.Exit(code=1) from exc

    command = completion_source_command(detected_shell, script_path)

    if print_command:
        if command:
            typer.echo(command)
        else:
            typer.echo(str(script_path))
        return

    typer.echo(_("Completion installed for {shell}.").format(shell=detected_shell))
    typer.echo(_("Script: {path}").format(path=script_path))
    if command:
        typer.echo(_("Command to add: {command}").format(command=command))
    typer.echo(completion_hint(detected_shell, script_path))


def completion_show(
    ctx: typer.Context,
    *,
    shell: str | None,
    detector: ShellDetectorFn | None = None,
    script_generator: Callable[..., str] = generate_completion_script,
) -> None:
    """Display the generated auto-completion script."""
    apply_locale(ctx)
    resolve = _resolve_detector(detector)
    detected_shell = resolve(shell)
    if not detected_shell:
        typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
        raise typer.Exit(code=1)

    script = script_generator(
        prog_name="recozik",
        complete_var="_RECOZIK_COMPLETE",
        shell=detected_shell,
    )
    typer.echo(script)


def completion_uninstall(
    ctx: typer.Context,
    *,
    shell: str | None,
    detector: ShellDetectorFn | None = None,
    script_path_getter: Callable[[str], Path | None] = completion_script_path,
    hint: Callable[[str], str] = completion_uninstall_hint,
) -> None:
    """Remove the shell-completion script installed by Recozik."""
    apply_locale(ctx)
    resolve = _resolve_detector(detector)
    detected_shell = resolve(shell)
    if not detected_shell:
        typer.echo(_("Unable to detect the shell. Provide --shell (bash/zsh/fish/pwsh)."))
        raise typer.Exit(code=1)

    script_path = script_path_getter(detected_shell)
    if script_path and script_path.exists():
        script_path.unlink()
        typer.echo(_("Completion script removed: {path}").format(path=script_path))
    else:
        typer.echo(_("No completion script to remove."))

    typer.echo(hint(detected_shell))

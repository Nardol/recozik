"""Shell completion helpers for the CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Protocol

from recozik_core.i18n import _


class ShellDetector(Protocol):
    """Protocol describing shell detection helpers."""

    def detect_shell(self) -> tuple[str, Path | None]:
        """Return the detected shell name and optional script path."""
        ...


def normalize_shell(shell: str | None) -> str | None:
    """Standardize shell identifiers."""
    if shell is None:
        return None

    normalized = shell.strip().lower()
    if normalized in {"", "auto"}:
        return None
    if normalized in {"powershell", "pwsh"}:
        return "pwsh"
    return normalized


def detect_shell(shell: str | None, *, detector: ShellDetector | None = None) -> str | None:
    """Detect the active shell, optionally using Typer's shellingham helper."""
    normalized = normalize_shell(shell)
    if normalized:
        return normalized

    if detector is None:
        return None

    disable_detection = os.getenv("_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION")
    if disable_detection:
        return None

    try:
        detected_shell, _ = detector.detect_shell()
    except Exception:  # pragma: no cover - depends on the system
        return None

    return normalize_shell(detected_shell)


def completion_hint(shell: str, script_path: Path) -> str:
    """Return a localized hint explaining how to enable completion."""
    command = completion_source_command(shell, script_path)
    if command:
        if shell in {"bash", "zsh"}:
            return _(
                "Run `{command}` or add this line to your profile file (e.g. ~/.bashrc, ~/.zshrc)."
            ).format(command=command)
        if shell == "fish":
            return _("Restart `fish` or run `{command}` to activate completion.").format(
                command=command
            )
        if shell in {"powershell", "pwsh"}:
            return _(
                "Add `{command}` to your `$PROFILE` (PowerShell) to load completion automatically."
            ).format(command=command)
    return _("Completion installed. Restart your terminal to use it.")


def completion_source_command(shell: str, script_path: Path) -> str | None:
    """Return the command that sources the completion script."""
    if shell in {"bash", "zsh", "fish"}:
        return f"source {script_path}"
    if shell in {"powershell", "pwsh"}:
        return f". {script_path}"
    return None


def completion_script_path(shell: str) -> Path | None:
    """Return the default installation path for the completion script."""
    if shell == "bash":
        return Path.home() / ".bash_completions" / "recozik.sh"
    if shell == "zsh":
        return Path.home() / ".zfunc" / "_recozik"
    if shell == "fish":
        return Path.home() / ".config/fish/completions/recozik.fish"
    if shell in {"powershell", "pwsh"}:
        return powershell_profile_path(shell)
    return None


def powershell_profile_path(shell: str) -> Path | None:
    """Return the profile path for PowerShell or pwsh shells."""
    shell_bin = "pwsh" if shell == "pwsh" else "powershell"
    try:
        command = [shell_bin, "-NoProfile", "-Command", "echo", "$profile"]
        result = subprocess.run(  # noqa: S603 - controlled argument list
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    output = result.stdout.strip()
    if not output:
        return None
    return Path(output)


def completion_uninstall_hint(shell: str) -> str:
    """Return guidance after removing a completion script."""
    if shell == "bash":
        return _(
            "Remove the line `source ~/.bash_completions/recozik.sh` from ~/.bashrc if necessary."
        )
    if shell == "zsh":
        return _("Check ~/.zshrc and remove the line adding ~/.zfunc if you no longer use it.")
    if shell == "fish":
        return _("Restart fish to apply the removal.")
    if shell in {"powershell", "pwsh"}:
        return _("Edit your $PROFILE file to remove the completion block added by Recozik.")
    return _("Completion uninstalled.")

"""Command-line interface for recozik."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from typer.completion import (
    get_completion_script as _typer_generate_completion_script,
)
from typer.completion import (
    install as _typer_install_completion,
)
from typer.completion import (
    shellingham as completion_shellingham,
)

from .cli_support.completion import (
    completion_hint,
    completion_script_path,
    completion_source_command,
    completion_uninstall_hint,
    detect_shell,
)
from .cli_support.deps import get_fingerprint_symbols, get_lookup_cache_cls
from .cli_support.metadata import extract_audio_metadata
from .commands.completion import (
    completion_install as completion_install_command,
)
from .commands.completion import (
    completion_show as completion_show_command,
)
from .commands.completion import (
    completion_uninstall as completion_uninstall_command,
)
from .commands.completion import (
    configure_shellingham_helper,
)
from .commands.config import (
    config_path as config_path_command,
)
from .commands.config import (
    config_set_key as config_set_key_command,
)
from .commands.config import (
    config_show as config_show_command,
)
from .commands.fingerprint import fingerprint as fingerprint_command
from .commands.identify import (
    DEFAULT_AUDIO_EXTENSIONS as IDENTIFY_DEFAULT_AUDIO_EXTENSIONS,
)
from .commands.identify import (
    configure_api_key_interactively,
    validate_client_key,
)
from .commands.identify import (
    identify as identify_command,
)
from .commands.identify_batch import identify_batch as identify_batch_command
from .commands.inspect import inspect as inspect_command
from .commands.rename import rename_from_log as rename_command
from .i18n import _, set_locale

generate_completion_script = _typer_generate_completion_script
install_completion = _typer_install_completion

app = typer.Typer(
    add_completion=False,
    help=_("Music recognition based on audio fingerprints."),
)
config_app = typer.Typer(
    add_completion=False,
    help=_("Manage local configuration."),
)
completion_app = typer.Typer(
    add_completion=False,
    help=_("Shell auto-completion helpers."),
)

app.add_typer(config_app, name="config")
app.add_typer(completion_app, name="completion")

configure_shellingham_helper(completion_shellingham)

_UNINITIALIZED = object()
_fingerprint_symbols: Any = _UNINITIALIZED
_lookup_cache_cls: Any = _UNINITIALIZED


def _ensure_fingerprint_symbols():
    global _fingerprint_symbols
    if _fingerprint_symbols is _UNINITIALIZED:
        _fingerprint_symbols = get_fingerprint_symbols()
    return _fingerprint_symbols


def _ensure_lookup_cache_cls():
    global _lookup_cache_cls
    if _lookup_cache_cls is _UNINITIALIZED:
        _lookup_cache_cls = get_lookup_cache_cls()
    return _lookup_cache_cls


def __getattr__(name: str) -> Any:  # pragma: no cover - compatibility helpers
    if name in {
        "compute_fingerprint",
        "lookup_recordings",
        "FingerprintResult",
        "FingerprintError",
        "AcoustIDMatch",
        "AcoustIDLookupError",
    }:
        symbols = _ensure_fingerprint_symbols()
        return getattr(symbols, name)
    if name == "LookupCache":
        return _ensure_lookup_cache_cls()
    raise AttributeError(name)


def _detect_shell(shell: str | None) -> str | None:
    return detect_shell(shell, detector=completion_shellingham)


def _completion_script_path(shell: str) -> Path | None:
    return completion_script_path(shell)


def _completion_source_command(shell: str, script_path: Path) -> str | None:
    return completion_source_command(shell, script_path)


def _completion_hint(shell: str, script_path: Path) -> str:
    return completion_hint(shell, script_path)


def _completion_uninstall_hint(shell: str) -> str:
    return completion_uninstall_hint(shell)


_extract_audio_metadata = extract_audio_metadata
_configure_api_key_interactively = configure_api_key_interactively
_validate_client_key = validate_client_key

DEFAULT_AUDIO_EXTENSIONS = IDENTIFY_DEFAULT_AUDIO_EXTENSIONS


@app.callback()
def main(
    ctx: typer.Context,
    locale_option: str | None = typer.Option(
        None,
        "--locale",
        help=_("Override the locale for this invocation (examples: en, fr, fr_FR)."),
    ),
) -> None:
    """Top-level callback for the CLI application."""
    ctx.ensure_object(dict)
    ctx.obj["cli_locale"] = locale_option
    if locale_option:
        set_locale(locale_option)


app.command(help=_("Display basic metadata extracted from an audio file."))(inspect_command)
app.command(help=_("Generate the Chromaprint fingerprint of an audio file."))(fingerprint_command)
app.command(help=_("Identify a track using the AcoustID API."))(identify_command)
app.command(
    "identify-batch",
    help=_("Identify audio files in a directory and persist the results."),
)(identify_batch_command)
app.command(
    "rename-from-log",
    help=_("Rename files using a JSONL log produced by `identify-batch`."),
)(rename_command)


@config_app.command(
    "path",
    help=_("Display the path to the configuration file in use."),
)
def config_path(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Delegate to the config command implementation."""
    config_path_command(ctx, config_path=config_path)


@config_app.command(
    "show",
    help=_("Display the main configuration settings."),
)
def config_show(
    ctx: typer.Context,
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Display configuration details using the shared handler."""
    config_show_command(ctx, config_path=config_path)


@config_app.command(
    "set-key",
    help=_("Store an AcoustID API key in the configuration."),
)
def config_set_key(
    ctx: typer.Context,
    api_key_arg: str | None = typer.Argument(
        None,
        help=_("AcoustID API key to record."),
    ),
    api_key_opt: str | None = typer.Option(
        None,
        "--api-key",
        "-k",
        help=_("AcoustID API key to record (alternative to the positional argument)."),
    ),
    skip_validation: bool = typer.Option(
        False,
        "--skip-validation/--validate",
        help=_("Skip online validation (not recommended)."),
    ),
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Persist an API key via the shared config handler."""
    config_set_key_command(
        ctx,
        api_key_arg=api_key_arg,
        api_key_opt=api_key_opt,
        skip_validation=skip_validation,
        config_path=config_path,
    )


@completion_app.command(
    "install",
    help=_("Install the shell completion script for the current shell."),
)
def completion_install(
    ctx: typer.Context,
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help=_("Target shell (bash, zsh, fish, powershell/pwsh). Autodetected if omitted."),
    ),
    print_command: bool = typer.Option(
        False,
        "--print-command",
        help=_("Print only the command to add to your shell profile."),
    ),
    no_write: bool = typer.Option(
        False,
        "--no-write",
        help=_("Output the completion script to stdout without writing files."),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=_("Write the completion script to a specific file (absolute or relative path)."),
    ),
) -> None:
    """Install the shell completion script for the active shell."""
    completion_install_command(
        ctx,
        shell=shell,
        print_command=print_command,
        no_write=no_write,
        output=output,
        detector=_detect_shell,
        installer=install_completion,
        script_generator=generate_completion_script,
    )


@completion_app.command(
    "show",
    help=_("Display the generated auto-completion script."),
)
def completion_show(
    ctx: typer.Context,
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help=_("Target shell (bash, zsh, fish, powershell/pwsh). Autodetected if omitted."),
    ),
) -> None:
    """Print the generated completion script for the detected shell."""
    completion_show_command(
        ctx,
        shell=shell,
        detector=_detect_shell,
        script_generator=generate_completion_script,
    )


@completion_app.command(
    "uninstall",
    help=_("Remove the auto-completion script installed by Recozik."),
)
def completion_uninstall(
    ctx: typer.Context,
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help=_("Target shell (bash, zsh, fish, powershell/pwsh). Autodetected if omitted."),
    ),
) -> None:
    """Remove the installed completion script if present."""
    completion_uninstall_command(
        ctx,
        shell=shell,
        detector=_detect_shell,
        script_path_getter=_completion_script_path,
        hint=_completion_uninstall_hint,
    )


if __name__ == "__main__":  # pragma: no cover
    app()

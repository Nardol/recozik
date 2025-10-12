"""Implementation of the `inspect` CLI command."""

from __future__ import annotations

from pathlib import Path

import typer

from ..cli_support.locale import apply_locale
from ..cli_support.metadata import MUTAGEN_AVAILABLE, extract_audio_metadata
from ..cli_support.paths import resolve_path
from ..i18n import _


def inspect(
    ctx: typer.Context,
    audio_path: Path = typer.Argument(
        ...,
        help=_("Path to the audio file to analyse."),
    ),
) -> None:
    """Display basic metadata for the provided audio file."""
    apply_locale(ctx)
    resolved = resolve_path(audio_path)
    if not resolved.is_file():
        typer.echo(_("File not found: {path}").format(path=resolved))
        raise typer.Exit(code=1)

    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - depends on the runtime environment
        typer.echo(
            _("The soundfile library is missing; run `uv sync` to install project dependencies.")
        )
        raise typer.Exit(code=1) from exc

    try:
        info = sf.info(str(resolved))
    except RuntimeError as exc:
        typer.echo(_("Unable to read the audio file: {error}").format(error=exc))
        raise typer.Exit(code=1) from exc

    typer.echo(_("File: {path}").format(path=resolved))
    typer.echo(_("Format: {format}, {subtype}").format(format=info.format, subtype=info.subtype))
    typer.echo(_("Channels: {channels}").format(channels=info.channels))
    typer.echo(_("Sample rate: {samplerate} Hz").format(samplerate=info.samplerate))
    typer.echo(_("Frame count: {frames}").format(frames=info.frames))
    typer.echo(_("Estimated duration: {duration:.2f} s").format(duration=info.duration))

    from .. import cli as cli_module

    extractor = getattr(cli_module, "_extract_audio_metadata", extract_audio_metadata)

    metadata = extractor(resolved)
    if metadata:
        typer.echo(_("Embedded metadata:"))
        if artist := metadata.get("artist"):
            typer.echo(_("  Artist: {value}").format(value=artist))
        if title := metadata.get("title"):
            typer.echo(_("  Title: {value}").format(value=title))
        if album := metadata.get("album"):
            typer.echo(_("  Album: {value}").format(value=album))
    elif not MUTAGEN_AVAILABLE:  # pragma: no cover - depends on installations
        typer.echo(_("No metadata available (mutagen library missing)."))

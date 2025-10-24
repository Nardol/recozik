"""Implementation of the `inspect` CLI command."""

from __future__ import annotations

import shutil
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
        fallback = _probe_with_ffmpeg(resolved)
        if fallback is None:
            typer.echo(_("Unable to read the audio file: {error}").format(error=exc))
            raise typer.Exit(code=1) from exc
        info = fallback

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


class _AudioInfo:
    """Lightweight container mirroring soundfile.SoundFile.info fields."""

    def __init__(
        self,
        *,
        format_name: str,
        subtype: str,
        channels: int,
        samplerate: int,
        frames: int,
        duration: float,
    ) -> None:
        self.format = format_name
        self.subtype = subtype
        self.channels = channels
        self.samplerate = samplerate
        self.frames = frames
        self.duration = duration


def _probe_with_ffmpeg(path: Path) -> _AudioInfo | None:
    """Return basic audio info using ffprobe when soundfile cannot decode the file."""
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None

    try:  # pragma: no cover - optional dependency
        import ffmpeg  # type: ignore
    except Exception:
        return None

    try:
        metadata = ffmpeg.probe(str(path), cmd=ffprobe_path)  # type: ignore[call-arg]
    except ffmpeg.Error:  # type: ignore[attr-defined]
        return None

    streams = metadata.get("streams", []) if isinstance(metadata, dict) else []
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not isinstance(audio_stream, dict):
        return None

    format_section = metadata.get("format", {}) if isinstance(metadata, dict) else {}

    format_name = (
        format_section.get("format_long_name") or format_section.get("format_name") or "unknown"
    )
    subtype = audio_stream.get("codec_long_name") or audio_stream.get("codec_name") or "unknown"

    def _parse_int(value: object) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _parse_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    samplerate = _parse_int(audio_stream.get("sample_rate"))
    channels = _parse_int(audio_stream.get("channels"))
    frames = _parse_int(audio_stream.get("nb_frames") or audio_stream.get("nb_samples"))
    duration = _parse_float(audio_stream.get("duration") or format_section.get("duration"))

    if frames == 0 and samplerate and duration:
        frames = int(duration * samplerate)

    return _AudioInfo(
        format_name=format_name,
        subtype=subtype,
        channels=channels,
        samplerate=samplerate,
        frames=frames,
        duration=duration,
    )

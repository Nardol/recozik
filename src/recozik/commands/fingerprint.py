"""Implementation of the `fingerprint` CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ..cli_support.locale import apply_locale
from ..cli_support.paths import resolve_path
from ..i18n import _


def fingerprint(
    ctx: typer.Context,
    audio_path: Path = typer.Argument(
        ...,
        help=_("Path to the audio file to fingerprint."),
    ),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help=_("Explicit path to the fpcalc executable when Chromaprint is not on PATH."),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=_("File where the fingerprint should be written in JSON format."),
    ),
    show_fingerprint: bool = typer.Option(
        False,
        "--show-fingerprint",
        help=_("Show full fingerprint in console (long and less convenient for screen readers)."),
    ),
) -> None:
    """Generate a Chromaprint fingerprint for an audio file."""
    apply_locale(ctx)
    from .. import cli as cli_module

    compute_fingerprint = cli_module.compute_fingerprint
    fingerprint_error_cls = cli_module.FingerprintError

    resolved_audio = resolve_path(audio_path)
    resolved_fpcalc = resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        result = compute_fingerprint(resolved_audio, fpcalc_path=resolved_fpcalc)
    except fingerprint_error_cls as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(_("Estimated duration: {duration:.2f} s").format(duration=result.duration_seconds))

    if output is not None:
        resolved_output = resolve_path(output)
        payload = {
            "audio_path": str(resolved_audio),
            "duration_seconds": result.duration_seconds,
            "fingerprint": result.fingerprint,
            "fpcalc_path": str(resolved_fpcalc) if resolved_fpcalc else None,
        }
        resolved_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        typer.echo(_("Fingerprint saved to {path}").format(path=resolved_output))

    if show_fingerprint:
        typer.echo(_("Chromaprint fingerprint:"))
        typer.echo(result.fingerprint)

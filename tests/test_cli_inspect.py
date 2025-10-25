"""Tests for the inspect command."""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from recozik import cli
from recozik.commands import inspect as inspect_cmd


class _FakeInfo:
    format = "WAV"
    subtype = "PCM_16"
    channels = 2
    samplerate = 44100
    frames = 44100
    duration = 1.0


class _FakeSoundFileModule:
    @staticmethod
    def info(path: str) -> _FakeInfo:  # pragma: no cover - simple stub
        assert Path(path).exists()
        return _FakeInfo()


def test_inspect_displays_metadata(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Print tags extracted from embedded metadata when available."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"data")

    monkeypatch.setitem(sys.modules, "soundfile", _FakeSoundFileModule())
    monkeypatch.setattr(
        cli,
        "_extract_audio_metadata",
        lambda _path: {"artist": "Tagged Artist", "title": "Tagged Title", "album": "Tagged Album"},
    )

    result = cli_runner.invoke(cli.app, ["inspect", str(audio_path)])

    assert result.exit_code == 0
    assert "Artist: Tagged Artist" in result.stdout
    assert "Title: Tagged Title" in result.stdout
    assert "Album: Tagged Album" in result.stdout


def test_inspect_uses_ffmpeg_fallback(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Probe file metadata with ffprobe when soundfile cannot open the file."""
    audio_path = tmp_path / "sample.wma"
    audio_path.write_bytes(b"data")

    class _FailingSoundFileModule:
        @staticmethod
        def info(_path: str):
            raise RuntimeError("unsupported format")

    fallback_info = inspect_cmd._AudioInfo(
        format_name="WMA",
        subtype="Windows Media Audio",
        channels=2,
        samplerate=44100,
        frames=44100,
        duration=1.0,
    )

    monkeypatch.setitem(sys.modules, "soundfile", _FailingSoundFileModule())
    monkeypatch.setattr(inspect_cmd, "_probe_with_ffmpeg", lambda _path: fallback_info)
    monkeypatch.setattr(
        cli,
        "_extract_audio_metadata",
        lambda _path: {},
    )

    result = cli_runner.invoke(cli.app, ["inspect", str(audio_path)])

    assert result.exit_code == 0
    assert "Format: WMA" in result.stdout

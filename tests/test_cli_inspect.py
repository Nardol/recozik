"""Tests for the inspect command."""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from recozik import cli

runner = CliRunner()


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


def test_inspect_displays_metadata(monkeypatch, tmp_path: Path) -> None:
    """Print tags extracted from embedded metadata when available."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"data")

    monkeypatch.setitem(sys.modules, "soundfile", _FakeSoundFileModule())
    monkeypatch.setattr(
        cli,
        "_extract_audio_metadata",
        lambda _path: {"artist": "Tagged Artist", "title": "Tagged Title", "album": "Tagged Album"},
    )

    result = runner.invoke(cli.app, ["inspect", str(audio_path)])

    assert result.exit_code == 0
    assert "Artiste: Tagged Artist" in result.stdout
    assert "Titre: Tagged Title" in result.stdout
    assert "Album: Tagged Album" in result.stdout

"""Tests for AudD integration helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import requests
import soundfile

from recozik import audd


def test_needs_audd_snippet_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Flag files larger than the configured AudD limit."""
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"0" * 512)
    monkeypatch.setattr(audd, "MAX_AUDD_BYTES", 256)

    assert audd.needs_audd_snippet(audio_path) is True

    monkeypatch.setattr(audd, "MAX_AUDD_BYTES", 1024)
    assert audd.needs_audd_snippet(audio_path) is False


def test_recognize_with_audd_uses_snippet_when_large(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Downsample and trim audio before sending it to AudD."""
    audio_path = tmp_path / "tone.wav"
    duration = 2.0
    sample_rate = 44_100
    time_axis = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    stereo = np.stack(
        [np.sin(2 * np.pi * 440 * time_axis), np.sin(2 * np.pi * 330 * time_axis)],
        axis=1,
    ).astype("float32")
    soundfile.write(audio_path, stereo, sample_rate)

    monkeypatch.setattr(audd, "MAX_AUDD_BYTES", 2048)

    captured: dict[str, object] = {}

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "status": "success",
                "result": {
                    "artist": "Snippet Artist",
                    "title": "Snippet Track",
                    "album": "Snippet Album",
                },
            }

    def fake_post(url, data, files, timeout):
        file_tuple = files["file"]
        payload = file_tuple[1].read()
        captured["size"] = len(payload)
        captured["name"] = file_tuple[0]
        return DummyResponse()

    monkeypatch.setattr(audd.requests, "post", fake_post)

    matches = audd.recognize_with_audd("token", audio_path)
    assert matches, "AudD should return at least one match"
    assert captured["size"] <= audd.MAX_AUDD_BYTES
    assert captured["name"] == audio_path.name
    assert matches[0].artist == "Snippet Artist"
    assert matches[0].title == "Snippet Track"


def test_recognize_with_audd_redacts_token_in_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure failure messages replace the AudD token with a placeholder."""
    audio_path = tmp_path / "tone.wav"
    duration = 0.1
    sample_rate = 8000
    tone = np.zeros(int(sample_rate * duration), dtype="float32")
    soundfile.write(audio_path, tone, sample_rate)

    def fake_post(url, data, files, timeout):
        raise requests.RequestException(f"error sending {data}")

    monkeypatch.setattr(audd.requests, "post", fake_post)

    token = "super-secret-token"  # noqa: S105 - test fixture value
    with pytest.raises(audd.AudDLookupError) as excinfo:
        audd.recognize_with_audd(token, audio_path)

    message = str(excinfo.value)
    assert token not in message
    assert "***redacted***" in message

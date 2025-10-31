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


def test_render_snippet_falls_back_to_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Use the FFmpeg path when libsndfile/librosa cannot decode the source."""
    audio_path = tmp_path / "track.wma"
    audio_path.write_bytes(b"dummy")
    destination = tmp_path / "snippet.wav"

    def fail_soundfile(*_args, **_kwargs) -> None:
        raise RuntimeError("unsupported format")

    fallback_called: dict[str, bool] = {"value": False}

    def fake_ffmpeg(*_args, **_kwargs) -> None:
        fallback_called["value"] = True
        samples = np.zeros(16_000, dtype="float32")
        soundfile.write(destination, samples, 16_000)

    monkeypatch.setattr(audd, "_ffmpeg_support_ready", lambda: True)
    monkeypatch.setattr(audd, "_should_prefer_ffmpeg", lambda _path: True)
    monkeypatch.setattr(audd, "_render_snippet_with_soundfile", fail_soundfile)
    monkeypatch.setattr(audd, "_render_snippet_with_ffmpeg", fake_ffmpeg)

    audd._render_snippet(audio_path, destination)

    assert fallback_called["value"] is True
    assert destination.exists()


def test_render_snippet_reports_ffmpeg_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Aggregate failures from both decoding strategies in the final error message."""
    audio_path = tmp_path / "clip.wma"
    audio_path.write_bytes(b"data")
    destination = tmp_path / "snippet.wav"

    def fail_soundfile(*_args, **_kwargs) -> None:
        raise RuntimeError("libsndfile does not support this format")

    def fail_ffmpeg(*_args, **_kwargs) -> None:
        raise audd.AudDLookupError("ffmpeg pipeline unavailable")

    monkeypatch.setattr(audd, "_ffmpeg_support_ready", lambda: True)
    monkeypatch.setattr(audd, "_should_prefer_ffmpeg", lambda _path: False)
    monkeypatch.setattr(audd, "_render_snippet_with_soundfile", fail_soundfile)
    monkeypatch.setattr(audd, "_render_snippet_with_ffmpeg", fail_ffmpeg)

    with pytest.raises(audd.AudDLookupError) as excinfo:
        audd._render_snippet(audio_path, destination)

    message = str(excinfo.value)
    assert "libsndfile" in message
    assert "ffmpeg pipeline unavailable" in message


def test_render_snippet_supports_offset(tmp_path: Path) -> None:
    """Apply the configured offset when preparing the AudD snippet."""
    audio_path = tmp_path / "tone.wav"
    duration = 2.0
    sample_rate = 16_000
    time_axis = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    mono = np.sin(2 * np.pi * 440 * time_axis).astype("float32")
    soundfile.write(audio_path, mono, sample_rate)

    destination = tmp_path / "snippet.wav"
    info = audd._render_snippet(  # type: ignore[attr-defined]
        audio_path,
        destination,
        snippet_seconds=1.0,
        target_sample_rate=16_000,
        snippet_offset=0.5,
    )

    assert destination.exists()
    assert pytest.approx(info.offset_seconds, rel=1e-6) == 0.5
    assert 0.9 <= info.duration_seconds <= 1.01
    assert info.rms > 0


def test_render_snippet_rejects_offset_beyond_duration(tmp_path: Path) -> None:
    """Raise an error when the requested offset exceeds the audio duration."""
    audio_path = tmp_path / "tone.wav"
    mono = np.zeros(4000, dtype="float32")
    soundfile.write(audio_path, mono, 16_000)

    destination = tmp_path / "snippet.wav"

    with pytest.raises(audd.AudDLookupError):
        audd._render_snippet(  # type: ignore[attr-defined]
            audio_path,
            destination,
            snippet_seconds=1.0,
            target_sample_rate=16_000,
            snippet_offset=5.0,
        )

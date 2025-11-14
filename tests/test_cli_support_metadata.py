"""Tests for metadata helper utilities."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from recozik_services.cli_support import metadata as service_metadata

from recozik.cli_support import metadata


def test_build_metadata_match_fills_defaults() -> None:  # noqa: D103
    match = metadata.build_metadata_match({"artist": "Artist"})
    assert match["formatted"].startswith("Artist")
    assert match["source"] == "metadata"
    assert match["recording_id"] is None


def test_coerce_metadata_dict_normalizes_strings() -> None:  # noqa: D103
    raw = {"artist": "  Alice  ", "title": 42, "album": None}
    result = metadata.coerce_metadata_dict(raw)
    assert result == {"artist": "Alice", "title": "42"}


def test_coerce_metadata_dict_invalid_input() -> None:  # noqa: D103
    assert metadata.coerce_metadata_dict(123) == {}


def test_extract_audio_metadata_without_mutagen(monkeypatch, tmp_path: Path) -> None:  # noqa: D103
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake")
    monkeypatch.setattr(service_metadata, "mutagen", None)
    assert metadata.extract_audio_metadata(audio_path) is None


def test_extract_audio_metadata_reads_tags(monkeypatch, tmp_path: Path) -> None:  # noqa: D103
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake")

    tags = {
        "artist": [" Artist ", "Other"],
        "title": ("Title",),
        "album": [{"name": "Album"}],
    }

    class DummyAudio:
        def __init__(self) -> None:
            self.tags = tags

    def fake_file(path, easy=True):
        assert path == audio_path
        assert easy is True
        return DummyAudio()

    monkeypatch.setattr(service_metadata, "mutagen", SimpleNamespace(File=fake_file))
    result = metadata.extract_audio_metadata(audio_path)
    assert result == {"artist": "Artist", "title": "Title", "album": "{'name': 'Album'}"}

"""Tests for the batch identification workflow."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from recozik import cli
from recozik.fingerprint import AcoustIDMatch, FingerprintResult

runner = CliRunner()


class DummyCache:
    """In-memory stub of the lookup cache used in batch tests."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise the fake cache with optional enabled flag."""
        self.enabled = kwargs.get("enabled", True)
        self.data: dict[tuple[str, int], list[AcoustIDMatch]] = {}

    def _key(self, fingerprint: str, duration: float) -> tuple[str, int]:
        return (fingerprint, round(duration))

    def get(self, fingerprint: str, duration: float):
        """Return cached matches when caching is enabled."""
        if not self.enabled:
            return None
        return self.data.get(self._key(fingerprint, duration))

    def set(self, fingerprint: str, duration: float, matches):
        """Store matches in the fake cache when caching is enabled."""
        if not self.enabled:
            return
        self.data[self._key(fingerprint, duration)] = list(matches)

    def save(self):
        """Avoid writing anything to disk for the fake cache."""
        pass


def _write_config(
    tmp_path: Path,
    template: str | None = None,
    log_format: str = "text",
    metadata_fallback: bool = True,
) -> Path:
    """Create a reusable configuration file tailored for batch tests."""
    config_path = tmp_path / "config.toml"
    sections = [
        "[acoustid]",
        'api_key = "token"',
        "",
        "[cache]",
        "enabled = true",
        "ttl_hours = 24",
        "",
    ]
    sections += ["[output]"]
    if template:
        sections.append(f'template = "{template}"')
    sections.append("")
    sections += ["[logging]", f'format = "{log_format}"', "absolute_paths = false", ""]
    config_path.write_text("\n".join(sections), encoding="utf-8")
    return config_path


def test_identify_batch_text_log(monkeypatch, tmp_path: Path) -> None:
    """Log formatted text entries for multiple audio files."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    file_a = audio_dir / "track_a.mp3"
    file_b = audio_dir / "track_b.flac"
    file_a.write_bytes(b"a")
    file_b.write_bytes(b"b")

    config_path = _write_config(tmp_path)
    log_path = tmp_path / "result.log"

    monkeypatch.setattr(cli, "LookupCache", DummyCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda path, fpcalc_path=None: FingerprintResult(
            fingerprint=path.stem.upper(), duration_seconds=120.0
        ),
    )

    def fake_lookup(api_key, fingerprint_result, meta=None, timeout=None):
        name = fingerprint_result.fingerprint.lower()
        return [
            AcoustIDMatch(
                score=0.9,
                recording_id=f"id-{name}",
                title=name.title(),
                artist="Artist",
            )
        ]

    monkeypatch.setattr(cli, "lookup_recordings", fake_lookup)

    result = runner.invoke(
        cli.app,
        [
            "identify-batch",
            str(audio_dir),
            "--config-path",
            str(config_path),
            "--log-file",
            str(log_path),
            "--template",
            "{artist} - {title}",
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    contents = log_path.read_text(encoding="utf-8")
    assert "file: track_a.mp3" in contents
    assert "Artist - Track_A" in contents
    assert "file: track_b.flac" in contents


def test_identify_batch_json_log(monkeypatch, tmp_path: Path) -> None:
    """Emit JSONL records when log format is jsonl."""

    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    file_a = audio_dir / "song.mp3"
    file_a.write_bytes(b"a")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "result.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda path, fpcalc_path=None: FingerprintResult(
            fingerprint="JSON", duration_seconds=180.0
        ),
    )
    monkeypatch.setattr(
        cli,
        "lookup_recordings",
        lambda *_args, **_kwargs: [
            AcoustIDMatch(
                score=0.8,
                recording_id="id-json",
                title="Song",
                artist="Artist",
            )
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "identify-batch",
            str(audio_dir),
            "--config-path",
            str(config_path),
            "--log-file",
            str(log_path),
            "--log-format",
            "jsonl",
            "--best-only",
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["path"] == "song.mp3"
    assert payload["matches"][0]["formatted"].startswith("Artist -")


def test_identify_batch_metadata_fallback(monkeypatch, tmp_path: Path) -> None:
    """Record embedded metadata when AcoustID returns no matches."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    file_a = audio_dir / "unmatched.flac"
    file_a.write_bytes(b"a")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "fallback.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="MISS", duration_seconds=200.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        cli,
        "_extract_audio_metadata",
        lambda _path: {"title": "Tag Title", "artist": "Tag Artist"},
    )

    result = runner.invoke(
        cli.app,
        [
            "identify-batch",
            str(audio_dir),
            "--config-path",
            str(config_path),
            "--log-file",
            str(log_path),
            "--log-format",
            "jsonl",
        ],
    )

    assert result.exit_code == 0
    assert "métadonnées locales enregistrées" in result.stdout

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["metadata"]["artist"] == "Tag Artist"
    assert payload["metadata"]["title"] == "Tag Title"


def test_identify_batch_extension_filter(monkeypatch, tmp_path: Path) -> None:
    """Skip files without supported audio extensions."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    keep_file = audio_dir / "keep.wav"
    skip_file = audio_dir / "skip.txt"
    keep_file.write_bytes(b"a")
    skip_file.write_text("ignore", encoding="utf-8")

    config_path = _write_config(tmp_path)
    log_path = tmp_path / "filter.log"

    monkeypatch.setattr(cli, "LookupCache", DummyCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda path, fpcalc_path=None: FingerprintResult(fingerprint="KEEP", duration_seconds=60.0),
    )
    monkeypatch.setattr(
        cli,
        "lookup_recordings",
        lambda *_args, **_kwargs: [
            AcoustIDMatch(
                score=0.7,
                recording_id="id-keep",
                title="Keep",
                artist="Artist",
            )
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "identify-batch",
            str(audio_dir),
            "--config-path",
            str(config_path),
            "--log-file",
            str(log_path),
            "--ext",
            "wav",
        ],
    )

    assert result.exit_code == 0

    contents = log_path.read_text(encoding="utf-8")
    assert "keep.wav" in contents
    assert "skip.txt" not in contents

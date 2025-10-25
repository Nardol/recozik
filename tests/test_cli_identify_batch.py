"""Tests for the batch identification workflow."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from recozik import audd, cli
from recozik.fingerprint import AcoustIDMatch, FingerprintResult

from .helpers.identify import DummyLookupCache, make_config


def _write_config(
    tmp_path: Path,
    template: str | None = None,
    log_format: str = "text",
) -> Path:
    """Create a reusable configuration file tailored for batch tests."""
    sections: list[str] = [
        "[audd]",
        '# api_token = "token"',
        "",
        "[cache]",
        "enabled = true",
        "ttl_hours = 24",
        "",
        "[output]",
    ]
    if template:
        sections.append(f'template = "{template}"')
    sections.append("")
    sections += ["[logging]", f'format = "{log_format}"', "absolute_paths = false", ""]
    return make_config(tmp_path, extra_lines=sections)


def test_identify_batch_text_log(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Log formatted text entries for multiple audio files."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    file_a = audio_dir / "track_a.mp3"
    file_b = audio_dir / "track_b.flac"
    file_a.write_bytes(b"a")
    file_b.write_bytes(b"b")

    config_path = _write_config(tmp_path)
    log_path = tmp_path / "result.log"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
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

    result = cli_runner.invoke(
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


def test_identify_batch_json_log(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Emit JSONL records when log format is jsonl."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    file_a = audio_dir / "song.mp3"
    file_a.write_bytes(b"a")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "result.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
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

    result = cli_runner.invoke(
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


def test_identify_batch_metadata_fallback(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Record embedded metadata when AcoustID returns no matches."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    file_a = audio_dir / "unmatched.flac"
    file_a.write_bytes(b"a")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "fallback.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
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

    result = cli_runner.invoke(
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
    assert "embedded metadata recorded" in result.stdout

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["metadata"]["artist"] == "Tag Artist"
    assert payload["metadata"]["title"] == "Tag Title"


def test_identify_batch_respects_config_defaults(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Pick up limit, best-only, recursion and log destination from the configuration."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    nested = audio_dir / "nested"
    nested.mkdir()
    target_file = nested / "track.mp3"
    target_file.write_bytes(b"data")

    config_log = tmp_path / "config-log.jsonl"
    config_path = _write_config(tmp_path, log_format="jsonl")
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                "[identify_batch]",
                "limit = 2",
                "best_only = true",
                "recursive = true",
                f'log_file = "{config_log}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda path, fpcalc_path=None: FingerprintResult(
            fingerprint=path.stem.upper(),
            duration_seconds=150.0,
        ),
    )

    def fake_lookup(api_key, fingerprint_result, meta=None, timeout=None):
        name = fingerprint_result.fingerprint.lower()
        return [
            AcoustIDMatch(
                score=0.95,
                recording_id=f"id-{name}-1",
                title=f"{name}-1",
                artist="Artist",
            ),
            AcoustIDMatch(
                score=0.85,
                recording_id=f"id-{name}-2",
                title=f"{name}-2",
                artist="Artist",
            ),
        ]

    monkeypatch.setattr(cli, "lookup_recordings", fake_lookup)

    result = cli_runner.invoke(
        cli.app,
        [
            "identify-batch",
            str(audio_dir),
            "--config-path",
            str(config_path),
            "--log-format",
            "jsonl",
        ],
    )

    assert result.exit_code == 0
    assert config_log.exists()
    lines = [line for line in config_log.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["path"].endswith("nested/track.mp3")
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["recording_id"].endswith("-1")


def test_identify_batch_extension_filter(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Skip files without supported audio extensions."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    keep_file = audio_dir / "keep.wav"
    skip_file = audio_dir / "skip.txt"
    keep_file.write_bytes(b"a")
    skip_file.write_text("ignore", encoding="utf-8")

    config_path = _write_config(tmp_path)
    log_path = tmp_path / "filter.log"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
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

    result = cli_runner.invoke(
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


def test_identify_batch_uses_audd_fallback(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Use AudD as a fallback provider when AcoustID has no result."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    sample = audio_dir / "needs-fallback.mp3"
    sample.write_bytes(b"sample")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "fallback.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="MISS", duration_seconds=180.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])

    fake_match = AcoustIDMatch(
        score=0.92,
        recording_id="audd-batch",
        title="Recovered",
        artist="Fallback Artist",
    )

    class DummyAudDError(Exception):
        pass

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "recognize_with_audd", lambda *_args, **_kwargs: [fake_match])

    result = cli_runner.invoke(
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
            "--audd-token",
            "secret",
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["note"] == "Powered by AudD Music (fallback)."
    assert payload["matches"][0]["recording_id"] == "audd-batch"
    assert "AudD fallback identified needs-fallback.mp3. Powered by AudD Music." in result.stdout


def test_identify_batch_can_disable_audd(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Skip AudD when the user opts out."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    sample = audio_dir / "needs-fallback.mp3"
    sample.write_bytes(b"sample")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "no_audd.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="MISS", duration_seconds=180.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])

    def _unexpected_audd(*_args, **_kwargs):
        raise AssertionError("AudD should not be called when --no-audd is set.")

    monkeypatch.setattr(audd, "AudDLookupError", RuntimeError)
    monkeypatch.setattr(audd, "recognize_with_audd", _unexpected_audd)

    result = cli_runner.invoke(
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
            "--audd-token",
            "secret",
            "--no-audd",
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["note"] == "No match."
    assert "AudD fallback identified" not in result.stdout


def test_identify_batch_prefer_audd(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Prioritise AudD when requested."""
    audio_dir = tmp_path / "music"
    audio_dir.mkdir()
    sample = audio_dir / "priority.mp3"
    sample.write_bytes(b"sample")

    config_path = _write_config(tmp_path, log_format="jsonl")
    log_path = tmp_path / "priority.jsonl"

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="MISS", duration_seconds=180.0),
    )

    def _unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("AcoustID should not be called when AudD already succeeded.")

    monkeypatch.setattr(cli, "lookup_recordings", _unexpected_lookup)

    fake_match = AcoustIDMatch(
        score=0.9,
        recording_id="audd-priority",
        title="Priority Batch Song",
        artist="AudD Artist",
    )

    class DummyAudDError(Exception):
        pass

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "recognize_with_audd", lambda *_args, **_kwargs: [fake_match])

    result = cli_runner.invoke(
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
            "--audd-token",
            "secret",
            "--prefer-audd",
        ],
    )

    assert result.exit_code == 0
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["note"] == "Powered by AudD Music (fallback)."
    assert payload["matches"][0]["recording_id"] == "audd-priority"

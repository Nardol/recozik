"""CLI-facing tests that ensure commands delegate to the service layer."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from recozik_services.batch import BatchSummary
from recozik_services.identify import IdentifyResponse
from recozik_services.rename import RenameSummary
from typer.testing import CliRunner

from recozik import cli
from recozik_core.fingerprint import AcoustIDMatch, FingerprintResult, ReleaseInfo

from .helpers.identify import make_config
from .helpers.rename import build_rename_command, invoke_rename, make_entry, write_jsonl_log


def test_cli_identify_uses_service_layer(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Ensure the CLI command builds a service request and renders service results."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake-audio")
    config_path = make_config(tmp_path)

    captured_request = {}

    def fake_identify(request, **kwargs):
        captured_request["request"] = request
        return IdentifyResponse(
            fingerprint=FingerprintResult(fingerprint="fp", duration_seconds=123.0),
            matches=[
                AcoustIDMatch(
                    score=0.95,
                    recording_id="rec-1",
                    title="Example",
                    artist="Artist",
                    releases=[
                        ReleaseInfo(title="Album", release_id="rel-1", date=None, country=None)
                    ],
                )
            ],
            match_source="acoustid",
            metadata=None,
            audd_note=None,
            audd_error=None,
        )

    monkeypatch.setattr("recozik.commands.identify.identify_track", fake_identify)

    result = cli_runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["recording_id"] == "rec-1"
    assert captured_request["request"].audio_path == audio_path


def test_cli_identify_batch_uses_service_layer(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Ensure batch CLI hands off to the service runner and writes logs."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    files = []
    for name in ("a.wav", "b.wav"):
        path = music_dir / name
        path.write_bytes(b"sound")
        files.append(path)

    log_path = tmp_path / "out.log"
    captured_request = {}

    def fake_run_batch(request, *, callbacks, log_consumer, path_formatter, **kwargs):
        captured_request["request"] = request
        entry = SimpleNamespace(
            display_path=path_formatter(next(iter(request.files))),
            fingerprint=FingerprintResult(fingerprint="fp", duration_seconds=12.0),
            matches=[
                AcoustIDMatch(
                    score=0.8,
                    recording_id="rec",
                    title="Track",
                    artist="Artist",
                    releases=[],
                )
            ],
            error=None,
            status="ok",
            note=None,
            metadata=None,
        )
        log_consumer(entry)
        return BatchSummary(success=1, unmatched=0, failures=0)

    monkeypatch.setattr("recozik.commands.identify_batch.run_batch_identify", fake_run_batch)

    result = cli_runner.invoke(
        cli.app,
        [
            "identify-batch",
            str(music_dir),
            "--log-file",
            str(log_path),
            "--config-path",
            str(make_config(tmp_path)),
        ],
    )

    assert result.exit_code == 0
    assert log_path.exists()
    log_contents = log_path.read_text(encoding="utf-8")
    assert "Track" in log_contents
    assert Path(next(iter(captured_request["request"].files))).name in {"a.wav", "b.wav"}


def test_cli_rename_uses_service_layer(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Ensure rename CLI forwards options to the service runner."""
    root = tmp_path / "music"
    root.mkdir()
    log_path = write_jsonl_log(tmp_path / "log.jsonl", [make_entry("track.flac")])

    captured_request = {}

    def fake_rename_service(request, **kwargs):
        captured_request["request"] = request
        return RenameSummary(
            planned=1,
            applied=1,
            skipped=0,
            errors=0,
            interrupted=False,
            dry_run=False,
            export_path=None,
            plan_entries=None,
        )

    monkeypatch.setattr("recozik.commands.rename.rename_service", fake_rename_service)

    command = build_rename_command(
        log_path,
        root,
        template="{artist} - {title}",
        extra_args=["--config-path", str(make_config(tmp_path)), "--log-cleanup", "never"],
        apply=True,
    )
    result = invoke_rename(cli_runner, command)

    assert result.exit_code == 0
    assert captured_request["request"].template == "{artist} - {title}"
    assert captured_request["request"].dry_run is False

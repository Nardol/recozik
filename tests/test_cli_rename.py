"""Tests for the rename-from-log command."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from recozik import cli

runner = CliRunner()


def _write_jsonl_log(path: Path, entries: list[dict]) -> None:
    """Write JSONL entries to the provided path."""
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def test_rename_from_log_apply(tmp_path: Path) -> None:
    """Apply rename operations when --apply is provided."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "original.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "original.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Title",
                        "score": 0.95,
                        "recording_id": "id-1",
                        "artist": "Artist",
                        "title": "Title",
                        "album": "Album",
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Title.mp3").exists()


def test_rename_from_log_dry_run(tmp_path: Path) -> None:
    """Preview rename operations without touching files."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "track.wav"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "track.wav",
                "matches": [
                    {
                        "formatted": "Artist - Track",
                        "score": 0.9,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Track",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "DRY-RUN" in result.stdout
    assert "Apply the planned renames now?" in result.stdout
    assert "Use --apply to run the renames." in result.stdout


def test_rename_from_log_dry_run_then_apply(tmp_path: Path) -> None:
    """Offer to apply the renames after a dry-run."""
    root = tmp_path / "music-apply"
    root.mkdir()
    src = root / "demo.flac"
    src.write_bytes(b"data")

    log_path = tmp_path / "apply.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "demo.flac",
                "matches": [
                    {
                        "formatted": "Artist - Demo",
                        "score": 0.93,
                        "recording_id": "apply-1",
                        "artist": "Artist",
                        "title": "Demo",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Demo.flac").exists()
    assert "DRY-RUN" in result.stdout
    assert "RENAMED" in result.stdout


def test_rename_from_log_conflict_append(tmp_path: Path) -> None:
    """Append a numeric suffix when the target filename already exists."""
    root = tmp_path / "music"
    root.mkdir()
    (root / "song1.mp3").write_bytes(b"a")
    (root / "song2.mp3").write_bytes(b"b")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "song1.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Same",
                        "score": 0.9,
                        "recording_id": "id1",
                        "artist": "Artist",
                        "title": "Same",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            },
            {
                "path": "song2.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Same",
                        "score": 0.85,
                        "recording_id": "id2",
                        "artist": "Artist",
                        "title": "Same",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            },
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    files = {p.name for p in root.glob("*.mp3")}
    assert files == {"Artist - Same.mp3", "Artist - Same-1.mp3"}


def test_rename_from_log_invalid_format(tmp_path: Path) -> None:
    """Abort when the provided log file is not JSONL."""
    log_path = tmp_path / "plain.log"
    log_path.write_text("file: track.mp3\n", encoding="utf-8")

    result = runner.invoke(cli.app, ["rename-from-log", str(log_path)])

    assert result.exit_code == 1
    assert "JSONL" in result.stdout


def test_rename_from_log_interactive(monkeypatch, tmp_path: Path) -> None:
    """Let the user choose a match interactively before renaming."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "interactive.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "interactive.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Option1",
                        "score": 0.9,
                        "recording_id": "id1",
                        "artist": "Artist",
                        "title": "Option1",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    },
                    {
                        "formatted": "Artist - Option2",
                        "score": 0.8,
                        "recording_id": "id2",
                        "artist": "Artist",
                        "title": "Option2",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    },
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
        input="2\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Option2.mp3").exists()


def test_rename_from_log_interactive_reprompt(tmp_path: Path) -> None:
    """Retry selection until a valid input is provided."""
    root = tmp_path / "retry"
    root.mkdir()
    src = root / "retry.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "retry.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "retry.mp3",
                "matches": [
                    {
                        "formatted": "Artist - First",
                        "score": 0.9,
                        "recording_id": "id1",
                        "artist": "Artist",
                        "title": "First",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    },
                    {
                        "formatted": "Artist - Second",
                        "score": 0.85,
                        "recording_id": "id2",
                        "artist": "Artist",
                        "title": "Second",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    },
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
        input="0\nabc\n2\n",
    )

    assert result.exit_code == 0
    assert "Index out of range" in result.stdout
    assert "Invalid selection" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Second.mp3").exists()


def test_rename_from_log_interactive_interrupt_cancel(monkeypatch, tmp_path: Path) -> None:
    """Cancel the command after Ctrl+C during selection."""
    root = tmp_path / "interrupt-cancel"
    root.mkdir()
    src = root / "track.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "track.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Pick Me",
                        "score": 0.9,
                        "recording_id": "1",
                        "artist": "Artist",
                        "title": "Pick Me",
                    },
                    {
                        "formatted": "Artist - Other Option",
                        "score": 0.8,
                        "recording_id": "2",
                        "artist": "Artist",
                        "title": "Other Option",
                    },
                ],
            }
        ],
    )

    responses: list[object] = [typer.Abort(), "1"]

    def fake_prompt(*args, **kwargs):
        if not responses:
            raise AssertionError("Unexpected prompt call")
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
    )

    assert result.exit_code == 1
    assert "Operation cancelled; no files renamed." in result.stdout
    assert src.exists()


def test_rename_from_log_interactive_interrupt_apply(monkeypatch, tmp_path: Path) -> None:
    """Apply partial renames after Ctrl+C."""
    root = tmp_path / "interrupt-apply"
    root.mkdir()
    first = root / "first.mp3"
    second = root / "second.mp3"
    first.write_bytes(b"data")
    second.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "first.mp3",
                "matches": [
                    {
                        "formatted": "Artist - A",
                        "score": 0.9,
                        "recording_id": "1",
                        "artist": "Artist",
                        "title": "A",
                    },
                    {
                        "formatted": "Artist - B",
                        "score": 0.8,
                        "recording_id": "2",
                        "artist": "Artist",
                        "title": "B",
                    },
                ],
            },
            {
                "path": "second.mp3",
                "matches": [
                    {
                        "formatted": "Artist - C",
                        "score": 0.95,
                        "recording_id": "3",
                        "artist": "Artist",
                        "title": "C",
                    },
                    {
                        "formatted": "Artist - D",
                        "score": 0.6,
                        "recording_id": "4",
                        "artist": "Artist",
                        "title": "D",
                    },
                ],
            },
        ],
    )

    responses: list[object] = ["1", typer.Abort(), "2"]

    def fake_prompt(*args, **kwargs):
        if not responses:
            raise AssertionError("Unexpected prompt call")
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "Continuing with renames confirmed before the interruption." in result.stdout
    assert not first.exists()
    assert (root / "Artist - A.mp3").exists()
    assert second.exists()


def test_rename_from_log_interactive_interrupt_resume(monkeypatch, tmp_path: Path) -> None:
    """Resume questioning after Ctrl+C."""
    root = tmp_path / "interrupt-resume"
    root.mkdir()
    src = root / "song.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "song.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Option1",
                        "score": 0.9,
                        "recording_id": "1",
                        "artist": "Artist",
                        "title": "Option1",
                    },
                    {
                        "formatted": "Artist - Option2",
                        "score": 0.8,
                        "recording_id": "2",
                        "artist": "Artist",
                        "title": "Option2",
                    },
                ],
            }
        ],
    )

    responses: list[object] = [typer.Abort(), "3", "2"]

    def fake_prompt(*args, **kwargs):
        if not responses:
            raise AssertionError("Unexpected prompt call")
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "Resume the current question" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Option2.mp3").exists()


def test_rename_from_log_rename_interrupt_continue(monkeypatch, tmp_path: Path) -> None:
    """Confirm continuation after Ctrl+C during the renaming stage."""
    root = tmp_path / "rename-continue"
    root.mkdir()
    src = root / "continue.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "continue.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Keep",
                        "score": 0.9,
                        "recording_id": "1",
                        "artist": "Artist",
                        "title": "Keep",
                    },
                    {
                        "formatted": "Artist - Skip",
                        "score": 0.1,
                        "recording_id": "2",
                        "artist": "Artist",
                        "title": "Skip",
                    },
                ],
            }
        ],
    )

    responses: list[object] = ["1", "2"]

    def fake_prompt(*args, **kwargs):
        if not responses:
            raise AssertionError("Unexpected prompt call")
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    original_rename = Path.rename
    call_count = {"value": 0}

    def fake_rename(self: Path, target: Path) -> None:  # type: ignore[override]
        if self.name != "continue.mp3":
            return original_rename(self, target)
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise KeyboardInterrupt()
        return original_rename(self, target)

    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)
    monkeypatch.setattr(Path, "rename", fake_rename)

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert call_count["value"] >= 2
    assert not src.exists()
    assert (root / "Artist - Keep.mp3").exists()
    assert "Continuing renaming." in result.stdout


def test_rename_from_log_rename_interrupt_cancel(monkeypatch, tmp_path: Path) -> None:
    """Allow the user to abort during the renaming stage."""
    root = tmp_path / "rename-cancel"
    root.mkdir()
    src = root / "cancel.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "cancel.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Stop",
                        "score": 0.9,
                        "recording_id": "1",
                        "artist": "Artist",
                        "title": "Stop",
                    },
                    {
                        "formatted": "Artist - Other",
                        "score": 0.8,
                        "recording_id": "2",
                        "artist": "Artist",
                        "title": "Other",
                    },
                ],
            }
        ],
    )

    responses: list[object] = ["1", "1"]

    def fake_prompt(*args, **kwargs):
        if not responses:
            raise AssertionError("Unexpected prompt call")
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    original_rename = Path.rename
    call_count = {"value": 0}

    def fake_rename(self: Path, target: Path) -> None:  # type: ignore[override]
        if self.name != "cancel.mp3":
            return original_rename(self, target)
        call_count["value"] += 1
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)
    monkeypatch.setattr(Path, "rename", fake_rename)

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
        ],
    )

    assert result.exit_code == 1
    assert call_count["value"] == 1
    assert src.exists()
    assert "Renaming interrupted" in result.stdout


def test_rename_from_log_metadata_fallback(tmp_path: Path) -> None:
    """Rename using metadata when no matches are provided."""
    root = tmp_path / "metadata"
    root.mkdir()
    src = root / "meta.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "meta.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "meta.mp3",
                "matches": [],
                "metadata": {
                    "artist": "Tagged Artist",
                    "title": "Tagged Title",
                    "album": "Tagged Album",
                },
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--metadata-fallback",
            "--apply",
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert "using embedded metadata" in result.stdout
    assert "Confirm rename based on embedded metadata" in result.stdout
    assert not src.exists()
    assert (root / "Tagged Artist - Tagged Title.mp3").exists()


def test_rename_from_log_metadata_fallback_auto_confirm(tmp_path: Path) -> None:
    """Allow automation by disabling the metadata confirmation prompt."""
    root = tmp_path / "auto"
    root.mkdir()
    src = root / "auto.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "auto.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "auto.mp3",
                "matches": [],
                "metadata": {
                    "artist": "Auto Artist",
                    "title": "Auto Title",
                },
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--metadata-fallback",
            "--metadata-fallback-no-confirm",
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "using embedded metadata" in result.stdout
    assert "Confirm rename based on embedded metadata" not in result.stdout
    assert not src.exists()
    assert (root / "Auto Artist - Auto Title.mp3").exists()


def test_rename_from_log_metadata_fallback_reject(tmp_path: Path) -> None:
    """Skip renaming when the user refuses the metadata fallback."""
    root = tmp_path / "reject"
    root.mkdir()
    src = root / "reject.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "reject.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "reject.mp3",
                "matches": [],
                "metadata": {
                    "artist": "Reject Artist",
                    "title": "Reject Title",
                },
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--metadata-fallback",
            "--apply",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "Metadata-based rename skipped" in result.stdout
    assert src.exists()


def test_rename_from_log_confirm_yes(tmp_path: Path) -> None:
    """Proceed with renaming when confirmation is accepted."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "confirm.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "confirm.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Confirm",
                        "score": 0.95,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Confirm",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--confirm",
            "--apply",
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Confirm.mp3").exists()


def test_rename_from_log_confirm_no(tmp_path: Path) -> None:
    """Cancel renaming when the user declines confirmation."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "skip.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "skip.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Skip",
                        "score": 0.9,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Skip",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            }
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--confirm",
            "--apply",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "Rename skipped" in result.stdout


def test_rename_from_log_export(tmp_path: Path) -> None:
    """Export the rename plan to JSON while applying changes."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "export.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    _write_jsonl_log(
        log_path,
        [
            {
                "path": "export.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Export",
                        "score": 0.88,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Export",
                        "album": None,
                        "release_group_id": None,
                        "release_id": None,
                    }
                ],
            }
        ],
    )

    export_file = tmp_path / "renames.json"

    result = runner.invoke(
        cli.app,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
            "--export",
            str(export_file),
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert export_file.exists()
    payload = json.loads(export_file.read_text(encoding="utf-8"))
    assert payload[0]["applied"] is True
    assert payload[0]["target"].endswith("Artist - Export.mp3")

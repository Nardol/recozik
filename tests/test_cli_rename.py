"""Tests for the rename-from-log command."""

from __future__ import annotations

import json
from pathlib import Path

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
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "DRY-RUN" in result.stdout


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
    assert "Indice hors plage" in result.stdout
    assert "Sélection invalide" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Second.mp3").exists()



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
    )

    assert result.exit_code == 0
    assert "utilisation des métadonnées" in result.stdout
    assert not src.exists()
    assert (root / "Tagged Artist - Tagged Title.mp3").exists()


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
    assert "Renommage ignoré" in result.stdout


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

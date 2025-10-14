"""Apply-mode tests for the rename-from-log command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from .helpers.rename import invoke_rename, write_jsonl_log


def test_rename_from_log_apply(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Apply rename operations when --apply is provided."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "original.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
            "--log-cleanup",
            "never",
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Title.mp3").exists()
    assert log_path.exists()


def test_rename_from_log_log_cleanup_prompt_delete(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Delete the log after confirmation in default prompt mode."""
    root = tmp_path / "cleanup-prompt"
    root.mkdir()
    src = root / "track.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "cleanup.jsonl"
    write_jsonl_log(
        log_path,
        [
            {
                "path": "track.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Track",
                        "score": 0.9,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Track",
                    }
                ],
            }
        ],
    )

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert not log_path.exists()
    assert "Delete the log file" in result.stdout
    assert "Log file deleted" in result.stdout


def test_rename_from_log_log_cleanup_always_option(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Always delete the log when the option is provided."""
    root = tmp_path / "cleanup-option"
    root.mkdir()
    src = root / "track.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "cleanup.jsonl"
    write_jsonl_log(
        log_path,
        [
            {
                "path": "track.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Track",
                        "score": 0.9,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Track",
                    }
                ],
            }
        ],
    )

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
            "--log-cleanup",
            "always",
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert not log_path.exists()
    assert "Log file deleted" in result.stdout
    assert "Delete the log file" not in result.stdout


def test_rename_from_log_log_cleanup_from_config(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Obey the log cleanup strategy provided by the configuration file."""
    root = tmp_path / "cleanup-config"
    root.mkdir()
    src = root / "track.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "cleanup.jsonl"
    write_jsonl_log(
        log_path,
        [
            {
                "path": "track.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Track",
                        "score": 0.9,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Track",
                    }
                ],
            }
        ],
    )

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[rename]",
                'log_cleanup = "always"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert not log_path.exists()
    assert "Log file deleted" in result.stdout


def test_rename_from_log_conflict_append(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Append a numeric suffix when the target filename already exists."""
    root = tmp_path / "music"
    root.mkdir()
    (root / "song1.mp3").write_bytes(b"a")
    (root / "song2.mp3").write_bytes(b"b")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
            "--log-cleanup",
            "never",
        ],
    )

    assert result.exit_code == 0
    files = {p.name for p in root.glob("*.mp3")}
    assert files == {"Artist - Same.mp3", "Artist - Same-1.mp3"}


def test_rename_from_log_invalid_format(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Abort when the provided log file is not JSONL."""
    log_path = tmp_path / "plain.log"
    log_path.write_text("file: track.mp3\n", encoding="utf-8")

    result = invoke_rename(
        cli_runner,
        ["rename-from-log", str(log_path)],
    )

    assert result.exit_code == 1
    assert "JSONL" in result.stdout


def test_rename_from_log_export(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Export the rename plan to JSON while applying changes."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "export.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--apply",
            "--log-cleanup",
            "never",
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

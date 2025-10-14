"""Interactive selection tests for rename-from-log."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from .helpers.rename import invoke_rename, write_jsonl_log


def test_rename_from_log_interactive(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Let the user choose a match interactively before renaming."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "interactive.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input="2\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Option2.mp3").exists()


def test_rename_from_log_interactive_reprompt(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Retry selection until a valid input is provided."""
    root = tmp_path / "retry"
    root.mkdir()
    src = root / "retry.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "retry.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--template",
            "{artist} - {title}",
            "--interactive",
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input="0\nabc\n2\n",
    )

    assert result.exit_code == 0
    assert "Index out of range" in result.stdout
    assert "Invalid selection" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Second.mp3").exists()

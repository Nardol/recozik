"""Metadata fallback and confirmation tests for rename-from-log."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from .helpers.rename import invoke_rename, write_jsonl_log


def test_rename_from_log_metadata_fallback(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Rename using metadata when no matches are provided."""
    root = tmp_path / "metadata"
    root.mkdir()
    src = root / "meta.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "meta.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Tagged Artist - Tagged Title.mp3").exists()


def test_rename_from_log_metadata_fallback_auto_confirm(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Skip confirmation when metadata fallback auto-confirmation is active."""
    root = tmp_path / "metadata-auto"
    root.mkdir()
    src = root / "meta.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "meta.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--apply",
            "--metadata-fallback-no-confirm",
            "--log-cleanup",
            "never",
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Tagged Artist - Tagged Title.mp3").exists()


def test_rename_from_log_metadata_fallback_reject(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Skip metadata fallback when the user declines."""
    root = tmp_path / "metadata-reject"
    root.mkdir()
    src = root / "meta.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "meta.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
        [
            "rename-from-log",
            str(log_path),
            "--root",
            str(root),
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "Metadata-based rename skipped" in result.stdout


def test_rename_from_log_confirm_yes(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Proceed when the user confirms the rename."""
    root = tmp_path / "confirm"
    root.mkdir()
    src = root / "confirm.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "confirm.jsonl"
    write_jsonl_log(
        log_path,
        [
            {
                "path": "confirm.mp3",
                "matches": [
                    {
                        "formatted": "Artist - Confirm",
                        "score": 0.9,
                        "recording_id": "id",
                        "artist": "Artist",
                        "title": "Confirm",
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
            "--confirm",
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Confirm.mp3").exists()


def test_rename_from_log_confirm_no(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Cancel renaming when the user declines confirmation."""
    root = tmp_path / "confirm"
    root.mkdir()
    src = root / "skip.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "confirm.jsonl"
    write_jsonl_log(
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
            "--confirm",
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input="n\n",
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "Rename skipped" in result.stdout

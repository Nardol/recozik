"""Dry-run behavior tests for rename-from-log."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from .helpers.rename import invoke_rename, write_jsonl_log


def test_rename_from_log_dry_run(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Preview rename operations without touching files."""
    root = tmp_path / "music"
    root.mkdir()
    src = root / "track.wav"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
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


def test_rename_from_log_dry_run_then_apply(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Offer to apply the renames after a dry-run."""
    root = tmp_path / "music-apply"
    root.mkdir()
    src = root / "demo.flac"
    src.write_bytes(b"data")

    log_path = tmp_path / "apply.jsonl"
    write_jsonl_log(
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

    result = invoke_rename(
        cli_runner,
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

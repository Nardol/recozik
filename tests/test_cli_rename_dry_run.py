"""Dry-run behavior tests for rename-from-log."""

from __future__ import annotations

from typer.testing import CliRunner

from .conftest import RenameTestEnv
from .helpers.rename import build_rename_command, invoke_rename, make_entry, make_match


def test_rename_from_log_dry_run(cli_runner: CliRunner, rename_env: RenameTestEnv) -> None:
    """Preview rename operations without touching files."""
    root = rename_env.make_root("music")
    src = rename_env.create_source(root, "track.wav")

    log_path = rename_env.write_log(
        "dry-run.jsonl",
        [
            make_entry(
                "track.wav",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Track",
                        score=0.9,
                        recording_id="id",
                    )
                ],
            )
        ],
    )

    result = invoke_rename(
        cli_runner,
        build_rename_command(log_path, root),
        input="n\n",
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "DRY-RUN" in result.stdout
    assert "Apply the planned renames now?" in result.stdout
    assert "Use --apply to run the renames." in result.stdout


def test_rename_from_log_dry_run_then_apply(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Offer to apply the renames after a dry-run."""
    root = rename_env.make_root("music-apply")
    src = rename_env.create_source(root, "demo.flac")

    log_path = rename_env.write_log(
        "dry-run-apply.jsonl",
        [
            make_entry(
                "demo.flac",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Demo",
                        score=0.93,
                        recording_id="apply-1",
                    )
                ],
            )
        ],
    )

    result = invoke_rename(
        cli_runner,
        build_rename_command(log_path, root),
        input="o\n",
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Demo.flac").exists()
    assert "DRY-RUN" in result.stdout
    assert "RENAMED" in result.stdout

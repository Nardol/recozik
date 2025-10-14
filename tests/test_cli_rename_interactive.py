"""Interactive selection tests for rename-from-log."""

from __future__ import annotations

from typer.testing import CliRunner

from .conftest import RenameTestEnv
from .helpers.rename import invoke_rename, make_entry, make_match


def test_rename_from_log_interactive(cli_runner: CliRunner, rename_env: RenameTestEnv) -> None:
    """Let the user choose a match interactively before renaming."""
    root = rename_env.make_root("music")
    src = rename_env.create_source(root, "interactive.mp3")

    log_path = rename_env.write_log(
        "interactive.jsonl",
        [
            make_entry(
                "interactive.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Option1",
                        score=0.9,
                        recording_id="id1",
                    ),
                    make_match(
                        artist="Artist",
                        title="Option2",
                        score=0.8,
                        recording_id="id2",
                    ),
                ],
            )
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


def test_rename_from_log_interactive_reprompt(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Retry selection until a valid input is provided."""
    root = rename_env.make_root("retry")
    src = rename_env.create_source(root, "retry.mp3")

    log_path = rename_env.write_log(
        "retry.jsonl",
        [
            make_entry(
                "retry.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="First",
                        score=0.9,
                        recording_id="id1",
                    ),
                    make_match(
                        artist="Artist",
                        title="Second",
                        score=0.85,
                        recording_id="id2",
                    ),
                ],
            )
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

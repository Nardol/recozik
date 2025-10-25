"""Interrupt handling tests for rename-from-log."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from recozik import cli

from .conftest import RenameTestEnv
from .helpers.rename import build_matches, build_rename_command, invoke_rename, make_entry


def test_rename_from_log_interactive_interrupt_cancel(
    monkeypatch, cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Cancel the command after Ctrl+C during selection."""
    root = rename_env.make_root("interrupt-cancel")
    src = rename_env.create_source(root, "track.mp3")

    log_path = rename_env.write_log(
        "interrupt-cancel.jsonl",
        [
            make_entry(
                "track.mp3",
                matches=build_matches(
                    [
                        ("Pick Me", 0.9, "1"),
                        ("Other Option", 0.8, "2"),
                    ]
                ),
            )
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

    result = invoke_rename(
        cli_runner,
        build_rename_command(
            log_path,
            root,
            interactive=True,
            apply=True,
            log_cleanup="never",
        ),
    )

    assert result.exit_code == 1
    assert "Operation cancelled; no files renamed." in result.stdout
    assert src.exists()


def test_rename_from_log_interactive_interrupt_apply(
    monkeypatch, cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Apply partial renames after Ctrl+C."""
    root = rename_env.make_root("interrupt-apply")
    first = rename_env.create_source(root, "first.mp3")
    second = rename_env.create_source(root, "second.mp3")

    log_path = rename_env.write_log(
        "interrupt-apply.jsonl",
        [
            make_entry(
                "first.mp3",
                matches=build_matches(
                    [
                        ("A", 0.9, "1"),
                        ("B", 0.8, "2"),
                    ]
                ),
            ),
            make_entry(
                "second.mp3",
                matches=build_matches(
                    [
                        ("C", 0.95, "3"),
                        ("D", 0.6, "4"),
                    ]
                ),
            ),
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

    result = invoke_rename(
        cli_runner,
        build_rename_command(
            log_path,
            root,
            interactive=True,
            apply=True,
            log_cleanup="never",
        ),
    )

    assert result.exit_code == 0
    assert "Continuing with renames confirmed before the interruption." in result.stdout
    assert not first.exists()
    assert (root / "Artist - A.mp3").exists()
    assert second.exists()


def test_rename_from_log_interactive_interrupt_resume(
    monkeypatch, cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Resume questioning after the user requests it."""
    root = rename_env.make_root("interrupt-resume")
    src = rename_env.create_source(root, "resume.mp3")

    log_path = rename_env.write_log(
        "interrupt-resume.jsonl",
        [
            make_entry(
                "resume.mp3",
                matches=build_matches(
                    [
                        ("Resume", 0.9, "1"),
                        ("Continue", 0.8, "2"),
                    ]
                ),
            )
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

    result = invoke_rename(
        cli_runner,
        build_rename_command(
            log_path,
            root,
            interactive=True,
            apply=True,
            log_cleanup="never",
        ),
    )

    assert result.exit_code == 0
    assert "Resume the current question" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Continue.mp3").exists()


@pytest.mark.parametrize(
    (
        "case_name",
        "responses",
        "matches",
        "persistent_interrupt",
        "expected_exit",
        "expected_message",
        "expect_target",
        "target_title",
        "expected_call_count",
    ),
    [
        (
            "rename-continue",
            ["1", "2"],
            [("Keep", 0.9, "1"), ("Skip", 0.1, "2")],
            False,
            0,
            "Continuing renaming.",
            True,
            "Keep",
            2,
        ),
        (
            "rename-cancel",
            ["1", "1"],
            [("Stop", 0.9, "1"), ("Other", 0.8, "2")],
            True,
            1,
            "Renaming interrupted",
            False,
            "Stop",
            1,
        ),
    ],
)
def test_rename_from_log_rename_interrupt_behaviour(
    monkeypatch,
    cli_runner: CliRunner,
    rename_env: RenameTestEnv,
    case_name: str,
    responses: list[str],
    matches: list[tuple[str, float, str]],
    persistent_interrupt: bool,
    expected_exit: int,
    expected_message: str,
    expect_target: bool,
    target_title: str,
    expected_call_count: int,
) -> None:
    """Cover continue and cancel flows during the rename stage."""
    filename = f"{case_name}.mp3"
    root = rename_env.make_root(case_name)
    src = rename_env.create_source(root, filename)

    log_path = rename_env.write_log(
        f"{case_name}.jsonl",
        [
            make_entry(
                filename,
                matches=build_matches(matches),
            )
        ],
    )

    response_queue: list[object] = list(responses)

    def fake_prompt(*args, **kwargs):
        if not response_queue:
            raise AssertionError("Unexpected prompt call")
        value = response_queue.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    original_prompt = cli.typer.prompt
    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)

    original_rename = Path.rename
    call_count = {"value": 0}

    def fake_rename(self: Path, target: Path) -> None:  # type: ignore[override]
        if self.name != filename:
            return original_rename(self, target)
        call_count["value"] += 1
        if persistent_interrupt or call_count["value"] == 1:
            raise KeyboardInterrupt()
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", fake_rename)

    result = invoke_rename(
        cli_runner,
        build_rename_command(
            log_path,
            root,
            interactive=True,
            apply=True,
            log_cleanup="never",
        ),
    )

    monkeypatch.setattr(cli.typer, "prompt", original_prompt)

    assert result.exit_code == expected_exit
    assert expected_message in result.stdout
    assert call_count["value"] >= expected_call_count

    target = root / f"Artist - {target_title}.mp3"
    if expect_target:
        assert not src.exists()
        assert target.exists()
    else:
        assert src.exists()
        assert not target.exists()

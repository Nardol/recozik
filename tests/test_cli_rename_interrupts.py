"""Interrupt handling tests for rename-from-log."""

from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner

from recozik import cli

from .helpers.rename import invoke_rename, make_entry, make_match, write_jsonl_log


def test_rename_from_log_interactive_interrupt_cancel(
    monkeypatch, cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Cancel the command after Ctrl+C during selection."""
    root = tmp_path / "interrupt-cancel"
    root.mkdir()
    src = root / "track.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                "track.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Pick Me",
                        score=0.9,
                        recording_id="1",
                    ),
                    make_match(
                        artist="Artist",
                        title="Other Option",
                        score=0.8,
                        recording_id="2",
                    ),
                ],
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
    )

    assert result.exit_code == 1
    assert "Operation cancelled; no files renamed." in result.stdout
    assert src.exists()


def test_rename_from_log_interactive_interrupt_apply(
    monkeypatch, cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Apply partial renames after Ctrl+C."""
    root = tmp_path / "interrupt-apply"
    root.mkdir()
    first = root / "first.mp3"
    second = root / "second.mp3"
    first.write_bytes(b"data")
    second.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                "first.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="A",
                        score=0.9,
                        recording_id="1",
                    ),
                    make_match(
                        artist="Artist",
                        title="B",
                        score=0.8,
                        recording_id="2",
                    ),
                ],
            ),
            make_entry(
                "second.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="C",
                        score=0.95,
                        recording_id="3",
                    ),
                    make_match(
                        artist="Artist",
                        title="D",
                        score=0.6,
                        recording_id="4",
                    ),
                ],
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
    )

    assert result.exit_code == 0
    assert "Continuing with renames confirmed before the interruption." in result.stdout
    assert not first.exists()
    assert (root / "Artist - A.mp3").exists()
    assert second.exists()


def test_rename_from_log_interactive_interrupt_resume(
    monkeypatch, cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Resume questioning after the user requests it."""
    root = tmp_path / "interrupt-resume"
    root.mkdir()
    src = root / "resume.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                "resume.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Resume",
                        score=0.9,
                        recording_id="1",
                    ),
                    make_match(
                        artist="Artist",
                        title="Continue",
                        score=0.8,
                        recording_id="2",
                    ),
                ],
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
    )

    assert result.exit_code == 0
    assert "Resume the current question" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Continue.mp3").exists()


def test_rename_from_log_rename_interrupt_continue(
    monkeypatch, cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Continue renaming after an interrupt during the apply stage."""
    root = tmp_path / "rename-continue"
    root.mkdir()
    src = root / "continue.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                "continue.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Keep",
                        score=0.9,
                        recording_id="1",
                    ),
                    make_match(
                        artist="Artist",
                        title="Skip",
                        score=0.1,
                        recording_id="2",
                    ),
                ],
            )
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

    original_prompt = cli.typer.prompt
    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)
    monkeypatch.setattr(Path, "rename", fake_rename)

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
    )

    monkeypatch.setattr(cli.typer, "prompt", original_prompt)

    assert result.exit_code == 0
    assert call_count["value"] >= 2
    assert not src.exists()
    assert (root / "Artist - Keep.mp3").exists()
    assert "Continuing renaming." in result.stdout


def test_rename_from_log_rename_interrupt_cancel(
    monkeypatch, cli_runner: CliRunner, tmp_path: Path
) -> None:
    """Cancel renaming after an interrupt during the apply stage."""
    root = tmp_path / "rename-cancel"
    root.mkdir()
    src = root / "cancel.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / "batch.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                "cancel.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Stop",
                        score=0.9,
                        recording_id="1",
                    ),
                    make_match(
                        artist="Artist",
                        title="Other",
                        score=0.8,
                        recording_id="2",
                    ),
                ],
            )
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
    )

    assert result.exit_code == 1
    assert call_count["value"] == 1
    assert src.exists()
    assert "Renaming interrupted" in result.stdout

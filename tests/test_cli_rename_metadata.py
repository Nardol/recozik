"""Metadata fallback and confirmation tests for rename-from-log."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from .helpers.rename import (
    invoke_rename,
    make_entry,
    make_match,
    make_metadata,
    write_jsonl_log,
)


@pytest.mark.parametrize(
    (
        "case_name",
        "extra_args",
        "input_text",
        "expect_renamed",
        "expected_message",
    ),
    [
        ("metadata", [], "o\n", True, None),
        ("metadata-auto", ["--metadata-fallback-no-confirm"], None, True, None),
        ("metadata-reject", [], "n\n", False, "Metadata-based rename skipped"),
    ],
)
def test_rename_from_log_metadata_fallback_modes(
    cli_runner: CliRunner,
    tmp_path: Path,
    case_name: str,
    extra_args: list[str],
    input_text: str | None,
    expect_renamed: bool,
    expected_message: str | None,
) -> None:
    """Cover metadata fallback confirmation flows with a single parametrized test."""
    root = tmp_path / case_name
    root.mkdir()
    src = root / "meta.mp3"
    src.write_bytes(b"data")

    log_path = tmp_path / f"{case_name}.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                "meta.mp3",
                matches=[],
                metadata=make_metadata(
                    artist="Tagged Artist",
                    title="Tagged Title",
                    album="Tagged Album",
                ),
            )
        ],
    )

    args = [
        "rename-from-log",
        str(log_path),
        "--root",
        str(root),
        "--apply",
        "--log-cleanup",
        "never",
        *extra_args,
    ]

    result = invoke_rename(cli_runner, args, input=input_text)

    assert result.exit_code == 0
    new_path = root / "Tagged Artist - Tagged Title.mp3"
    if expect_renamed:
        assert not src.exists()
        assert new_path.exists()
    else:
        assert src.exists()
        assert not new_path.exists()

    if expected_message:
        assert expected_message in result.stdout


@pytest.mark.parametrize(
    ("case_name", "input_text", "expect_renamed", "expected_message"),
    [
        ("confirm", "o\n", True, None),
        ("confirm", "n\n", False, "Rename skipped"),
    ],
)
def test_rename_from_log_confirm_prompt(
    cli_runner: CliRunner,
    tmp_path: Path,
    case_name: str,
    input_text: str,
    expect_renamed: bool,
    expected_message: str | None,
) -> None:
    """Exercise confirm/decline flows with metadata-derived matches."""
    root = tmp_path / case_name
    root.mkdir()
    src_name = "confirm.mp3" if expect_renamed else "skip.mp3"
    src = root / src_name
    src.write_bytes(b"data")

    log_path = tmp_path / f"{case_name}.jsonl"
    write_jsonl_log(
        log_path,
        [
            make_entry(
                src_name,
                matches=[
                    make_match(
                        artist="Artist",
                        title="Confirm",
                        score=0.9,
                        recording_id="id",
                    )
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
            "--confirm",
            "--apply",
            "--log-cleanup",
            "never",
        ],
        input=input_text,
    )

    assert result.exit_code == 0
    target = root / "Artist - Confirm.mp3"
    if expect_renamed:
        assert not src.exists()
        assert target.exists()
    else:
        assert src.exists()
        assert not target.exists()
        if expected_message:
            assert expected_message in result.stdout

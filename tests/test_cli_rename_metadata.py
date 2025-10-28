"""Metadata fallback and confirmation tests for rename-from-log."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from .conftest import RenameTestEnv
from .helpers.rename import (
    build_rename_command,
    invoke_rename,
    make_entry,
    make_match,
    make_metadata,
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
    rename_env: RenameTestEnv,
    case_name: str,
    extra_args: list[str],
    input_text: str | None,
    expect_renamed: bool,
    expected_message: str | None,
) -> None:
    """Cover metadata fallback confirmation flows with a single parametrized test."""
    root = rename_env.make_root(case_name)
    src = rename_env.create_source(root, "meta.mp3")

    log_path = rename_env.write_log(
        f"{case_name}.jsonl",
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

    command = build_rename_command(
        log_path,
        root,
        template="{artist} - {title}",
        apply=True,
        log_cleanup="never",
        extra_args=extra_args,
    )

    result = invoke_rename(cli_runner, command, input=input_text)

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
    rename_env: RenameTestEnv,
    case_name: str,
    input_text: str,
    expect_renamed: bool,
    expected_message: str | None,
) -> None:
    """Exercise confirm/decline flows with metadata-derived matches."""
    root = rename_env.make_root(case_name)
    src_name = "confirm.mp3" if expect_renamed else "skip.mp3"
    src = rename_env.create_source(root, src_name)

    log_path = rename_env.write_log(
        f"{case_name}.jsonl",
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
        build_rename_command(
            log_path,
            root,
            template="{artist} - {title}",
            apply=True,
            log_cleanup="never",
            extra_args=["--confirm"],
        ),
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


def test_rename_from_log_metadata_missing_required_fields(
    cli_runner: CliRunner,
    rename_env: RenameTestEnv,
) -> None:
    """Ensure metadata fallback entries missing template fields are skipped gracefully."""
    root = rename_env.make_root("metadata-missing")
    src = rename_env.create_source(root, "missing.mp3")

    log_path = rename_env.write_log(
        "metadata-missing.jsonl",
        [
            make_entry(
                "missing.mp3",
                matches=[],
                metadata={"title": "Only Title"},
                status="unmatched",
                note="Aucune correspondance.",
            )
        ],
    )

    result = invoke_rename(
        cli_runner,
        build_rename_command(
            log_path,
            root,
            template="{artist} - {title}",
            apply=True,
            log_cleanup="never",
            extra_args=["--require-template-fields"],
        ),
    )

    assert result.exit_code == 0
    assert src.exists()
    assert "Match skipped for missing.mp3" in result.stdout
    assert "No proposal for: " in result.stdout

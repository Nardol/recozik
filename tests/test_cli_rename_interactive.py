"""Interactive selection tests for rename-from-log."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from .conftest import RenameTestEnv
from .helpers.rename import build_matches, invoke_rename, make_entry


@pytest.mark.parametrize(
    (
        "case_name",
        "filename",
        "matches",
        "input_sequence",
        "expected_title",
        "expected_messages",
    ),
    [
        (
            "interactive",
            "interactive.mp3",
            [
                ("Option1", 0.9, "id1"),
                ("Option2", 0.8, "id2"),
            ],
            ["2\n"],
            "Option2",
            [],
        ),
        (
            "interactive-reprompt",
            "interactive-reprompt.mp3",
            [
                ("First", 0.9, "id1"),
                ("Second", 0.85, "id2"),
            ],
            ["0\n", "abc\n", "2\n"],
            "Second",
            ["Index out of range", "Invalid selection"],
        ),
    ],
)
def test_rename_from_log_interactive_selection(
    cli_runner: CliRunner,
    rename_env: RenameTestEnv,
    case_name: str,
    filename: str,
    matches: list[tuple[str, float, str]],
    input_sequence: list[str],
    expected_title: str,
    expected_messages: list[str],
) -> None:
    """Cover normal selection and retry flows with one parametrized test."""
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
        input="".join(input_sequence),
    )

    assert result.exit_code == 0
    for expected in expected_messages:
        assert expected in result.stdout
    assert not src.exists()
    assert (root / f"Artist - {expected_title}.mp3").exists()


def test_rename_from_log_interactive_via_config(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Trigger interactive selection without the CLI flag when config enables it."""
    root = rename_env.make_root("config-interactive")
    src = rename_env.create_source(root, "pick.wav")

    log_path = rename_env.write_log(
        "config-interactive.jsonl",
        [
            make_entry(
                "pick.wav",
                matches=build_matches(
                    [
                        ("First", 0.92, "id1"),
                        ("Second", 0.85, "id2"),
                    ]
                ),
            )
        ],
    )

    config_path = rename_env.base / "config-interactive.toml"
    config_path.write_text(
        "\n".join(
            [
                "[rename]",
                "interactive = true",
            ]
        )
        + "\n",
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
            "--log-cleanup",
            "never",
            "--config-path",
            str(config_path),
        ],
        input="2\n",
    )

    assert result.exit_code == 0
    assert "Multiple proposals for pick.wav" in result.stdout
    assert not src.exists()
    assert (root / "Artist - Second.wav").exists()

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


def test_rename_interactive_deduplicates_template(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Collapse duplicate proposals that render to the same target filename."""
    root = rename_env.make_root("interactive-deduplicate")
    src = rename_env.create_source(root, "dedupe.mp3")

    log_path = rename_env.write_log(
        "interactive-deduplicate.jsonl",
        [
            make_entry(
                "dedupe.mp3",
                matches=build_matches(
                    [
                        ("Duplicate", 0.92, "dup-1"),
                        ("Duplicate", 0.90, "dup-2"),
                        ("Different", 0.88, "diff-1"),
                    ]
                ),
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
    assert "  3." not in result.stdout
    assert not src.exists()
    assert (root / "Artist - Different.mp3").exists()


def test_rename_interactive_can_keep_template_duplicates(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Allow users to opt-out of template-based deduplication."""
    root = rename_env.make_root("interactive-keep-duplicates")
    src = rename_env.create_source(root, "keep.mp3")

    log_path = rename_env.write_log(
        "interactive-keep-duplicates.jsonl",
        [
            make_entry(
                "keep.mp3",
                matches=build_matches(
                    [
                        ("Duplicate", 0.94, "dup-1"),
                        ("Duplicate", 0.89, "dup-2"),
                        ("Different", 0.87, "diff-1"),
                    ]
                ),
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
            "--keep-template-duplicates",
        ],
        input="3\n",
    )

    assert result.exit_code == 0
    assert "  3." in result.stdout
    assert not src.exists()
    assert (root / "Artist - Different.mp3").exists()


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


def test_rename_interactive_config_disables_deduplication(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Honor configuration when disabling template-based deduplication."""
    root = rename_env.make_root("config-keep-duplicates")
    src = rename_env.create_source(root, "config.mp3")

    log_path = rename_env.write_log(
        "config-keep-duplicates.jsonl",
        [
            make_entry(
                "config.mp3",
                matches=build_matches(
                    [
                        ("Duplicate", 0.91, "dup-1"),
                        ("Duplicate", 0.88, "dup-2"),
                        ("Different", 0.85, "diff-1"),
                    ]
                ),
            )
        ],
    )

    config_path = rename_env.base / "config-keep-duplicates.toml"
    config_path.write_text(
        "\n".join(
            [
                "[rename]",
                "interactive = true",
                "deduplicate_template = false",
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
        input="3\n",
    )

    assert result.exit_code == 0
    assert "  3." in result.stdout
    assert not src.exists()
    assert (root / "Artist - Different.mp3").exists()

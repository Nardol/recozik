"""Apply-mode tests for the rename-from-log command."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from .conftest import RenameTestEnv
from .helpers.rename import build_rename_command, invoke_rename, make_entry, make_match


def test_rename_from_log_apply(cli_runner: CliRunner, rename_env: RenameTestEnv) -> None:
    """Apply rename operations when --apply is provided."""
    root = rename_env.make_root("music")
    src = rename_env.create_source(root, "original.mp3")

    log_path = rename_env.write_log(
        "apply.jsonl",
        [
            make_entry(
                "original.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Title",
                        score=0.95,
                        recording_id="id-1",
                        album="Album",
                    )
                ],
            )
        ],
    )

    result = invoke_rename(
        cli_runner,
        [*build_rename_command(log_path, root), "--apply", "--log-cleanup", "never"],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Artist - Title.mp3").exists()
    assert log_path.exists()


def test_rename_missing_template_values_allowed_by_default(
    cli_runner: CliRunner, rename_env: RenameTestEnv
) -> None:
    """Keep the legacy behaviour when template fields are optional."""
    root = rename_env.make_root("allow-missing")
    src = rename_env.create_source(root, "source.mp3")

    log_path = rename_env.write_log(
        "allow-missing.jsonl",
        [
            make_entry(
                "source.mp3",
                matches=[
                    make_match(
                        artist="",
                        title="Demo",
                        score=0.82,
                        recording_id="missing-artist",
                    )
                ],
            )
        ],
    )

    result = invoke_rename(
        cli_runner,
        [*build_rename_command(log_path, root), "--apply", "--log-cleanup", "never"],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert (root / "Unknown artist - Demo.mp3").exists()


@pytest.mark.parametrize(
    ("extra_args", "input_text", "config_cleanup", "expect_deleted", "expect_prompt"),
    [
        ([], "o\n", None, True, True),
        (["--log-cleanup", "always"], None, None, True, False),
        ([], None, "always", True, False),
    ],
)
def test_rename_from_log_log_cleanup_modes(
    cli_runner: CliRunner,
    rename_env: RenameTestEnv,
    extra_args: list[str],
    input_text: str | None,
    config_cleanup: str | None,
    expect_deleted: bool,
    expect_prompt: bool,
) -> None:
    """Exercise the different log cleanup strategies."""
    root = rename_env.make_root("cleanup")
    src = rename_env.create_source(root, "track.mp3")

    log_path = rename_env.write_log(
        "cleanup.jsonl",
        [
            make_entry(
                "track.mp3",
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

    args = [
        *build_rename_command(log_path, root),
        "--apply",
        *extra_args,
    ]

    if config_cleanup:
        config_path = rename_env.base / "config.toml"
        config_path.write_text(
            "\n".join(["[rename]", f'log_cleanup = "{config_cleanup}"', ""]),
            encoding="utf-8",
        )
        args.extend(["--config-path", str(config_path)])

    result = invoke_rename(cli_runner, args, input=input_text)

    assert result.exit_code == 0
    assert not src.exists()

    if expect_deleted:
        assert not log_path.exists()
        assert "Log file deleted" in result.stdout
    else:
        assert log_path.exists()

    prompt_present = "Delete the log file" in result.stdout
    assert prompt_present is expect_prompt


def test_rename_from_log_conflict_append(cli_runner: CliRunner, rename_env: RenameTestEnv) -> None:
    """Append a numeric suffix when the target filename already exists."""
    root = rename_env.make_root("music")
    rename_env.create_source(root, "song1.mp3", data=b"a")
    rename_env.create_source(root, "song2.mp3", data=b"b")

    log_path = rename_env.write_log(
        "conflict.jsonl",
        [
            make_entry(
                "song1.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Same",
                        score=0.9,
                        recording_id="id1",
                    )
                ],
            ),
            make_entry(
                "song2.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Same",
                        score=0.85,
                        recording_id="id2",
                    )
                ],
            ),
        ],
    )

    result = invoke_rename(
        cli_runner,
        [*build_rename_command(log_path, root), "--apply", "--log-cleanup", "never"],
    )

    assert result.exit_code == 0
    files = {p.name for p in root.glob("*.mp3")}
    assert files == {"Artist - Same.mp3", "Artist - Same-1.mp3"}


def test_rename_from_log_invalid_format(cli_runner: CliRunner, rename_env: RenameTestEnv) -> None:
    """Abort when the provided log file is not JSONL."""
    log_path = rename_env.base / "plain.log"
    log_path.write_text("file: track.mp3\n", encoding="utf-8")

    result = invoke_rename(
        cli_runner,
        ["rename-from-log", str(log_path)],
    )

    assert result.exit_code == 1
    assert "JSONL" in result.stdout


def test_rename_from_log_export(cli_runner: CliRunner, rename_env: RenameTestEnv) -> None:
    """Export the rename plan to JSON while applying changes."""
    root = rename_env.make_root("export")
    src = rename_env.create_source(root, "export.mp3")

    log_path = rename_env.write_log(
        "export.jsonl",
        [
            make_entry(
                "export.mp3",
                matches=[
                    make_match(
                        artist="Artist",
                        title="Export",
                        score=0.88,
                        recording_id="id",
                    )
                ],
            )
        ],
    )

    export_file = rename_env.base / "renames.json"

    result = invoke_rename(
        cli_runner,
        [
            *build_rename_command(log_path, root),
            "--apply",
            "--log-cleanup",
            "never",
            "--export",
            str(export_file),
        ],
    )

    assert result.exit_code == 0
    assert not src.exists()
    assert export_file.exists()
    payload = json.loads(export_file.read_text(encoding="utf-8"))
    assert payload[0]["applied"] is True
    assert payload[0]["target"].endswith("Artist - Export.mp3")

"""Utilities to streamline rename-from-log CLI tests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from typer.testing import CliRunner


def write_jsonl_log(path: Path, entries: Sequence[dict]) -> Path:
    """Write entries to ``path`` in JSONL format and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def invoke_rename(
    runner: CliRunner,
    command: Sequence[object],
    *,
    input: str | None = None,
):
    """Invoke the CLI with the provided ``command`` sequence."""
    from recozik import cli

    command_args = [str(arg) for arg in command]
    return runner.invoke(cli.app, command_args, input=input)


__all__ = ["invoke_rename", "write_jsonl_log"]

"""Utilities to streamline rename-from-log CLI tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from typer.testing import CliRunner


def write_jsonl_log(path: Path, entries: Sequence[Mapping[str, Any]]) -> Path:
    """Write entries to ``path`` in JSONL format and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def make_match(
    *,
    artist: str,
    title: str,
    score: float = 0.9,
    recording_id: str = "id",
    album: str | None = None,
    release_group_id: str | None = None,
    release_id: str | None = None,
    formatted: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Return a match dictionary with sensible defaults."""
    display = formatted or f"{artist} - {title}"
    data: dict[str, Any] = {
        "formatted": display,
        "score": score,
        "recording_id": recording_id,
        "artist": artist,
        "title": title,
        "album": album,
        "release_group_id": release_group_id,
        "release_id": release_id,
    }
    if source is not None:
        data["source"] = source
    return data


def make_metadata(*, artist: str, title: str, album: str | None = None) -> dict[str, Any]:
    """Return metadata suitable for fallback scenarios."""
    data: dict[str, Any] = {
        "artist": artist,
        "title": title,
    }
    if album is not None:
        data["album"] = album
    return data


def make_entry(
    path: str,
    *,
    matches: Sequence[Mapping[str, Any]] | None = None,
    metadata: Mapping[str, Any] | None = None,
    status: str | None = None,
    error: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Return a JSONL log entry with optional fields."""
    entry: dict[str, Any] = {"path": path}
    if matches is not None:
        entry["matches"] = list(matches)
    if metadata is not None:
        entry["metadata"] = dict(metadata)
    if status is not None:
        entry["status"] = status
    if error is not None:
        entry["error"] = error
    if note is not None:
        entry["note"] = note
    return entry


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


__all__ = [
    "invoke_rename",
    "make_entry",
    "make_match",
    "make_metadata",
    "write_jsonl_log",
]

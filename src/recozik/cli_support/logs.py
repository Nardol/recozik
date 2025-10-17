"""Logging helpers shared by multiple CLI commands."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from string import Formatter
from typing import TYPE_CHECKING

from ..i18n import _

if TYPE_CHECKING:
    from ..fingerprint import AcoustIDMatch, FingerprintResult


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def extract_template_fields(template: str) -> set[str]:
    """Return the placeholder field names used by ``template``."""
    formatter = Formatter()
    fields: set[str] = set()
    for _literal, field_name, _format_spec, _conversion in formatter.parse(template):
        if not field_name:
            continue
        normalized = field_name.split(".", 1)[0]
        normalized = normalized.split("[", 1)[0]
        if normalized:
            fields.add(normalized)
    return fields


def format_match_template(match: AcoustIDMatch, template: str) -> str:
    """Render the template with the match context."""
    context = _build_match_context(match)
    formatter = Formatter()
    try:
        return formatter.vformat(template, (), _SafeDict(context))
    except Exception:  # pragma: no cover - defensive fallback
        fallback = "{artist} - {title}"
        return formatter.vformat(fallback, (), _SafeDict(context))


def _build_match_context(match: AcoustIDMatch) -> dict[str, str]:
    album = match.release_group_title
    if not album and match.releases:
        album = match.releases[0].title

    release_id = match.release_group_id
    if not release_id and match.releases:
        release_id = match.releases[0].release_id

    return {
        "artist": match.artist or _("Unknown artist"),
        "title": match.title or _("Unknown title"),
        "album": album or "",
        "release_id": release_id or "",
        "recording_id": match.recording_id or "",
        "score": f"{match.score:.2f}",
    }


def format_score(value: object) -> str:
    """Return a human-friendly score."""
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value or "")


def write_log_entry(
    handle,
    log_format: str,
    path_display: str,
    matches: Iterable[AcoustIDMatch],
    error: str | None,
    template: str,
    fingerprint: FingerprintResult | None,
    *,
    status: str = "ok",
    note: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Write a log entry in text or JSONL format."""
    if log_format == "jsonl":
        entry = {
            "path": path_display,
            "duration_seconds": fingerprint.duration_seconds if fingerprint else None,
            "error": error,
            "status": status,
            "note": note,
            "matches": [
                {
                    "rank": idx,
                    "formatted": format_match_template(match, template),
                    "score": match.score,
                    "recording_id": match.recording_id,
                    "artist": match.artist,
                    "title": match.title,
                    "album": match.release_group_title
                    or (match.releases[0].title if match.releases else None),
                    "release_group_id": match.release_group_id,
                    "release_id": match.releases[0].release_id if match.releases else None,
                }
                for idx, match in enumerate(matches, start=1)
            ],
            "metadata": metadata or None,
        }
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return

    handle.write(f"file: {path_display}\n")
    if fingerprint:
        handle.write(f"  duration: {fingerprint.duration_seconds:.2f}s\n")
    if status and status != "ok":
        handle.write(f"  status: {status}\n")
    if note:
        handle.write(f"  note: {note}\n")
    if metadata:
        handle.write("  metadata:\n")
        for key in ("artist", "title", "album"):
            value = metadata.get(key)
            if value:
                handle.write(f"    {key}: {value}\n")
    if error:
        handle.write(f"  error: {error}\n\n")
        return

    for idx, match in enumerate(matches, start=1):
        formatted = format_match_template(match, template)
        handle.write(f"  {idx}. {formatted} (score {match.score:.2f})\n")
    handle.write("\n")


def load_jsonl_log(path: Path) -> list[dict]:
    """Load a JSONL log written by identify-batch."""
    entries: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    _("The log must be JSONL (rerun `identify-batch` with --log-format jsonl).")
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    _("Invalid JSONL entry (line {number}).").format(number=line_number)
                )
            entries.append(payload)
    return entries


def render_log_template(match: dict, template: str, source_path: Path) -> str:
    """Render the log template for rename operations."""
    context = {
        "artist": match.get("artist") or _("Unknown artist"),
        "title": match.get("title") or _("Unknown title"),
        "album": match.get("album") or "",
        "score": format_score(match.get("score")),
        "recording_id": match.get("recording_id") or "",
        "release_group_id": match.get("release_group_id") or "",
        "release_id": match.get("release_id") or "",
        "ext": source_path.suffix,
        "stem": source_path.stem,
    }

    formatted = match.get("formatted")
    formatter = Formatter()
    try:
        return formatter.vformat(template, (), _SafeDict(context))
    except Exception:
        if formatted:
            return formatted
        return formatter.vformat("{artist} - {title}", (), _SafeDict(context))

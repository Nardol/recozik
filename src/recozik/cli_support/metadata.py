"""Metadata utilities shared by CLI commands."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from recozik_core.i18n import _

try:  # pragma: no cover - depends on optional dependency
    import mutagen  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on environment
    mutagen = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)
MUTAGEN_AVAILABLE = mutagen is not None


def extract_audio_metadata(path: Path) -> dict[str, str] | None:
    """Read basic tags from audio files when mutagen is available."""
    if mutagen is None:  # pragma: no cover - depends on installed packages
        return None

    try:
        audio = mutagen.File(path, easy=True)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive safety
        return None

    if audio is None:
        return None

    tags = getattr(audio, "tags", None)
    if not tags:
        return None

    def first_value(tag_value: Any) -> str | None:
        if tag_value is None:
            return None
        if isinstance(tag_value, str):
            candidate = tag_value.strip()
            return candidate or None
        if isinstance(tag_value, (list, tuple, set)):
            for item in tag_value:
                candidate = first_value(item)
                if candidate:
                    return candidate
            return None
        try:
            candidate = str(tag_value).strip()
        except Exception as exc:  # pragma: no cover - defensive conversion
            _LOGGER.debug("Failed to normalize tag value %r: %s", tag_value, exc)
            return None
        return candidate or None

    metadata: dict[str, str] = {}
    for key in ("artist", "title", "album"):
        value = first_value(tags.get(key))  # type: ignore[arg-type]
        if value:
            metadata[key] = value

    return metadata or None


def coerce_metadata_dict(value: object) -> dict[str, str]:
    """Normalize metadata payloads coming from JSON logs."""
    if not isinstance(value, dict):
        return {}

    result: dict[str, str] = {}
    for key in ("artist", "title", "album"):
        raw = value.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            candidate = raw.strip()
        else:
            try:
                candidate = str(raw).strip()
            except Exception as exc:  # pragma: no cover - defensive conversion
                _LOGGER.debug("Skipping metadata value %r for %s: %s", raw, key, exc)
                continue
        if candidate:
            result[key] = candidate
    return result


def build_metadata_match(metadata: dict[str, str]) -> dict[str, object]:
    """Create a pseudo-match entry sourced from embedded metadata."""
    artist_value = metadata.get("artist") or _("Unknown artist")
    title_value = metadata.get("title") or _("Unknown title")
    formatted = f"{artist_value} - {title_value}"
    return {
        "score": None,
        "recording_id": None,
        "artist": metadata.get("artist"),
        "title": metadata.get("title"),
        "album": metadata.get("album"),
        "release_group_id": None,
        "release_id": None,
        "formatted": formatted,
        "source": "metadata",
    }

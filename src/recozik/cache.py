"""Local cache helpers for AcoustID lookup responses."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import platformdirs

from .fingerprint import AcoustIDMatch

CACHE_FILENAME = "lookup-cache.json"


def default_cache_path() -> Path:
    """Return the default cache file location under the user cache directory."""
    cache_dir = Path(platformdirs.user_cache_dir("recozik", appauthor=False))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / CACHE_FILENAME


@dataclass(slots=True)
class CacheEntry:
    fingerprint: str
    duration_seconds: float
    timestamp: float
    matches: list[AcoustIDMatch]

    def to_dict(self) -> dict:
        """Serialize the cache entry into a JSON-friendly payload."""
        return {
            "fingerprint": self.fingerprint,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "matches": [match.to_dict() for match in self.matches],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> CacheEntry:
        """Build a cache entry instance from a serialized payload."""
        matches = [AcoustIDMatch.from_dict(item) for item in payload.get("matches", [])]
        return cls(
            fingerprint=payload["fingerprint"],
            duration_seconds=float(payload["duration_seconds"]),
            timestamp=float(payload["timestamp"]),
            matches=matches,
        )


class LookupCache:
    """Lightweight JSON-backed cache for AcoustID lookups."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        enabled: bool = True,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
        """Initialize the cache with desired file location and time-to-live."""
        self.path = path or default_cache_path()
        self.enabled = enabled
        self.ttl = ttl
        self._loaded = False
        self._data: dict[str, CacheEntry] = {}
        self._dirty = False

    def _ensure_loaded(self) -> None:
        if self._loaded or not self.enabled:
            return
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            for key, entry in payload.items():
                try:
                    self._data[key] = CacheEntry.from_dict(entry)
                except (KeyError, ValueError, TypeError):
                    continue
        self._loaded = True

    @staticmethod
    def _key(fingerprint: str, duration_seconds: float) -> str:
        rounded: int = round(duration_seconds)
        return f"{fingerprint}:{rounded}"

    def get(self, fingerprint: str, duration_seconds: float) -> list[AcoustIDMatch] | None:
        """Return cached matches matching the fingerprint and duration if fresh."""
        if not self.enabled:
            return None
        self._ensure_loaded()
        key = self._key(fingerprint, duration_seconds)
        entry = self._data.get(key)
        if not entry:
            return None
        now = time.time()
        if now - entry.timestamp > self.ttl.total_seconds():
            return None
        return entry.matches

    def set(
        self,
        fingerprint: str,
        duration_seconds: float,
        matches: Iterable[AcoustIDMatch],
    ) -> None:
        """Store new matches for the given fingerprint and duration."""
        if not self.enabled:
            return
        self._ensure_loaded()
        key = self._key(fingerprint, duration_seconds)
        self._data[key] = CacheEntry(
            fingerprint=fingerprint,
            duration_seconds=duration_seconds,
            timestamp=time.time(),
            matches=list(matches),
        )
        self._dirty = True

    def clear(self) -> None:
        """Remove all cached entries and delete the cache file if present."""
        self._data.clear()
        self._dirty = True
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass

    def save(self) -> None:
        """Persist the in-memory cache to disk when it has been modified."""
        if not self.enabled or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: entry.to_dict() for key, entry in self._data.items()}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._dirty = False


__all__ = ["LookupCache", "default_cache_path"]

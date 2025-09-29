"""Gestion d'un cache local pour les réponses AcoustID."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Iterable, Optional

import platformdirs

from .fingerprint import AcoustIDMatch

CACHE_FILENAME = "lookup-cache.json"


def default_cache_path() -> Path:
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
        return {
            "fingerprint": self.fingerprint,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "matches": [match.to_dict() for match in self.matches],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "CacheEntry":
        matches = [AcoustIDMatch.from_dict(item) for item in payload.get("matches", [])]
        return cls(
            fingerprint=payload["fingerprint"],
            duration_seconds=float(payload["duration_seconds"]),
            timestamp=float(payload["timestamp"]),
            matches=matches,
        )


class LookupCache:
    """Cache simple basé sur un fichier JSON."""

    def __init__(
        self,
        path: Optional[Path] = None,
        *,
        enabled: bool = True,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
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
        rounded = int(round(duration_seconds))
        return f"{fingerprint}:{rounded}"

    def get(self, fingerprint: str, duration_seconds: float) -> Optional[list[AcoustIDMatch]]:
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
        self._data.clear()
        self._dirty = True
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass

    def save(self) -> None:
        if not self.enabled or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: entry.to_dict() for key, entry in self._data.items()}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._dirty = False


__all__ = ["LookupCache", "default_cache_path"]

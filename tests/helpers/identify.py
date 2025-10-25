"""Shared utilities for identify-related CLI tests."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from recozik.fingerprint import AcoustIDMatch


class DummyLookupCache:
    """In-memory stub of the lookup cache API used in tests."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise the fake cache with an optional enabled flag."""
        self.enabled = kwargs.get("enabled", True)
        self._store: dict[tuple[str, int], list[AcoustIDMatch]] = {}

    def _key(self, fingerprint: str, duration: float) -> tuple[str, int]:
        return (fingerprint, round(duration))

    def get(self, fingerprint: str, duration: float):
        """Return cached matches when caching is enabled."""
        if not self.enabled:
            return None
        return self._store.get(self._key(fingerprint, duration))

    def set(self, fingerprint: str, duration: float, matches) -> None:
        """Persist matches in the fake cache when caching is enabled."""
        if not self.enabled:
            return
        self._store[self._key(fingerprint, duration)] = list(matches)

    def save(self) -> None:
        """Pretend to persist the cache contents (no-op)."""
        return None


def make_config(
    tmp_path: Path,
    *,
    api_key: str = "token",
    extra_lines: Iterable[str] = (),
) -> Path:
    """Write a configuration file with optional extra sections."""
    config_path = tmp_path / "config.toml"
    lines = [
        "[acoustid]",
        f'api_key = "{api_key}"',
        "",
    ]
    lines.extend(extra_lines)
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


__all__ = ["DummyLookupCache", "make_config"]

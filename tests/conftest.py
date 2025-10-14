"""Shared pytest configuration for recozik tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from .helpers.rename import write_jsonl_log


@pytest.fixture(autouse=True)
def force_english_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force tests to use the English locale unless explicitly overridden."""
    monkeypatch.setenv("RECOZIK_LOCALE", "en")
    try:
        from recozik.i18n import set_locale
    except ModuleNotFoundError:  # pragma: no cover - during initial imports
        return
    set_locale("en")


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Return a new CLI runner for each test."""
    return CliRunner()


@dataclass(slots=True)
class RenameTestEnv:
    """Utility wrapper that streamlines fixture setup for rename CLI tests."""

    base: Path

    def make_root(self, name: str) -> Path:
        """Create and return a root directory rooted in the temp base."""
        root = self.base / name
        root.mkdir()
        return root

    def create_source(self, root: Path, filename: str, data: bytes = b"data") -> Path:
        """Create a source file within ``root`` containing ``data``."""
        src = root / filename
        src.write_bytes(data)
        return src

    def write_log(self, filename: str, entries: list[dict[str, Any]]) -> Path:
        """Write a JSONL log file under the temporary base directory."""
        log_path = self.base / filename
        write_jsonl_log(log_path, entries)
        return log_path


@pytest.fixture()
def rename_env(tmp_path: Path) -> RenameTestEnv:
    """Provide helpers to create rename roots, sources, and logs."""
    return RenameTestEnv(base=tmp_path)

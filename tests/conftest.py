"""Shared pytest configuration for recozik tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def force_english_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force tests to use the English locale unless explicitly overridden."""
    monkeypatch.setenv("RECOZIK_LOCALE", "en")
    try:
        from recozik.i18n import set_locale
    except ModuleNotFoundError:  # pragma: no cover - during initial imports
        return
    set_locale("en")

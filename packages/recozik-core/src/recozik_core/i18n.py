"""Localization utilities for Recozik."""

from __future__ import annotations

import gettext as _gettext_module
import importlib
import locale as _locale
import sys
from collections.abc import Iterable
from pathlib import Path

_DOMAIN = "recozik"
_LOCALE_DIR = Path(__file__).resolve().parent / "locales"

_current_locale: str | None = None
_translator: _gettext_module.NullTranslations = _gettext_module.NullTranslations()


def _normalize_locale(value: str | None) -> str | None:
    """Normalize locale strings (e.g. ``fr-FR`` -> ``fr_FR``)."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    candidate = candidate.replace("-", "_")
    parts = candidate.split("_", maxsplit=1)
    language = parts[0].lower()
    if len(parts) == 1:
        return language
    region = parts[1].upper()
    return f"{language}_{region}"


def detect_system_locale() -> str | None:
    """Best-effort locale detection, returning ``None`` if undetectable."""
    for getter_name in ("getlocale", "getdefaultlocale"):
        getter = getattr(_locale, getter_name, None)
        if getter is None:
            continue
        try:
            detected = getter()
        except ValueError:
            continue
        if isinstance(detected, tuple):
            language = detected[0]
        else:
            language = detected
        normalized = _normalize_locale(language)
        if normalized:
            return normalized
    return None


def _candidate_languages(locale_value: str | None) -> list[str]:
    normalized = _normalize_locale(locale_value)
    if not normalized:
        return []
    candidates = [normalized]
    base = normalized.split("_", maxsplit=1)[0]
    if base and base not in candidates:
        candidates.append(base)
    return candidates


def set_locale(locale_value: str | None) -> str | None:
    """Install translations for the provided locale and return the value used."""
    global _translator, _current_locale

    languages = _candidate_languages(locale_value)
    if not languages:
        system_locale = detect_system_locale()
        languages = _candidate_languages(system_locale)

    translator = _gettext_module.translation(
        _DOMAIN,
        localedir=_LOCALE_DIR,
        languages=languages or None,
        fallback=True,
    )
    _translator = translator  # type: ignore[assignment]
    translator.install()

    for module_name in [
        "click.core",
        "click.termui",
        "click.exceptions",
        "click.decorators",
        "click.formatting",
        "typer.builtin_display",
    ]:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:  # pragma: no cover - optional deps
            continue
        if hasattr(module, "_"):
            module._ = translator.gettext  # type: ignore[attr-defined]
        if hasattr(module, "ngettext"):
            module.ngettext = translator.ngettext  # type: ignore[attr-defined]

    rich_utils = sys.modules.get("typer.rich_utils")
    if rich_utils is not None:
        if hasattr(rich_utils, "ARGUMENTS_PANEL_TITLE"):
            rich_utils.ARGUMENTS_PANEL_TITLE = translator.gettext("Arguments")  # type: ignore[attr-defined]
        if hasattr(rich_utils, "OPTIONS_PANEL_TITLE"):
            rich_utils.OPTIONS_PANEL_TITLE = translator.gettext("Options")  # type: ignore[attr-defined]
        if hasattr(rich_utils, "COMMANDS_PANEL_TITLE"):
            rich_utils.COMMANDS_PANEL_TITLE = translator.gettext("Commands")  # type: ignore[attr-defined]
        if hasattr(rich_utils, "ERRORS_PANEL_TITLE"):
            rich_utils.ERRORS_PANEL_TITLE = translator.gettext("Error")  # type: ignore[attr-defined]
        if hasattr(rich_utils, "RICH_HELP"):
            rich_utils.RICH_HELP = translator.gettext(  # type: ignore[attr-defined]
                "Try [blue]'{command_path} {help_option}'[/] for help."
            )

    _current_locale = languages[0] if languages else None
    return _current_locale


def get_current_locale() -> str | None:
    """Return the locale currently in use."""
    return _current_locale


def reset_locale() -> None:
    """Reset translations to the system locale."""
    set_locale(None)


def gettext_(message: str) -> str:
    """Translate a simple message."""
    return _translator.gettext(message)


def ngettext_(singular: str, plural: str, count: int) -> str:
    """Translate a plural-aware message."""
    return _translator.ngettext(singular, plural, count)


def available_locales() -> list[str]:
    """Return locales with compiled catalogs available."""
    locales: set[str] = set()
    if _LOCALE_DIR.is_dir():
        for entry in _LOCALE_DIR.iterdir():
            if not entry.is_dir():
                continue
            if (entry / "LC_MESSAGES" / f"{_DOMAIN}.mo").exists():
                locales.add(entry.name)
    return sorted(locales)


def resolve_preferred_locale(*candidates: Iterable[str | None] | str | None) -> str | None:
    """Return the first non-empty locale among the provided candidates."""
    flattened: list[str | None] = []
    for candidate in candidates:
        if isinstance(candidate, Iterable) and not isinstance(candidate, (str, bytes)):
            for item in candidate:
                flattened.append(item)
        else:
            flattened.append(candidate)  # type: ignore[arg-type]

    for value in flattened:
        normalized = _normalize_locale(value)
        if normalized:
            return normalized
    return None


# Install default (system) translations on import.
set_locale(None)

# Convenience aliases matching gettext conventions.
_ = gettext_
gettext = gettext_
ngettext = ngettext_

__all__ = [
    "_",
    "available_locales",
    "detect_system_locale",
    "get_current_locale",
    "gettext",
    "ngettext",
    "reset_locale",
    "resolve_preferred_locale",
    "set_locale",
]

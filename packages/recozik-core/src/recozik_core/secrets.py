"""Secure storage helpers for API keys and tokens."""

from __future__ import annotations

from typing import Protocol

try:  # pragma: no cover - optional dependency
    import keyring
    from keyring.errors import KeyringError
except Exception:  # pragma: no cover - when keyring is absent
    keyring = None  # type: ignore[assignment]
    KeyringError = Exception  # type: ignore[misc,assignment]

SERVICE_NAME = "recozik"
_ACOUSTID_ENTRY = "acoustid_api_key"
_AUDD_ENTRY = "audd_api_token"


class SecretBackend(Protocol):
    """Minimal protocol implemented by keyring backends."""

    def get_password(self, service: str, username: str) -> str | None:
        """Return the stored secret for ``username``."""

    def set_password(self, service: str, username: str, password: str) -> None:
        """Persist ``password`` for ``username``."""

    def delete_password(self, service: str, username: str) -> None:
        """Delete the stored secret for ``username``."""


class SecretStoreError(RuntimeError):
    """Raised when secrets cannot be stored or retrieved."""


class SecretBackendUnavailableError(SecretStoreError):
    """Raised when no secure backend is available on the current system."""


_backend_override: SecretBackend | None = None


def configure_secret_backend(backend: SecretBackend | None) -> None:
    """Override the backend (used in tests)."""
    global _backend_override
    _backend_override = backend


def _get_backend() -> SecretBackend:
    if _backend_override is not None:
        return _backend_override
    if keyring is None:
        raise SecretBackendUnavailableError(
            "The `keyring` package is unavailable; install it to store secrets securely."
        )
    return keyring  # type: ignore[return-value]


def _get_secret(entry: str) -> str | None:
    try:
        backend = _get_backend()
    except SecretBackendUnavailableError:
        return None
    try:
        return backend.get_password(SERVICE_NAME, entry)
    except KeyringError as exc:  # pragma: no cover - backend specific failures
        raise SecretStoreError(str(exc)) from exc


def _set_secret(entry: str, value: str | None) -> None:
    backend = _get_backend()
    try:
        if value:
            backend.set_password(SERVICE_NAME, entry, value)
        else:
            backend.delete_password(SERVICE_NAME, entry)
    except KeyringError as exc:  # pragma: no cover - backend specific failures
        raise SecretStoreError(str(exc)) from exc


def get_acoustid_api_key() -> str | None:
    """Return the stored AcoustID API key, if any."""
    return _get_secret(_ACOUSTID_ENTRY)


def has_acoustid_api_key() -> bool:
    """Return True when an AcoustID API key is stored."""
    return bool(get_acoustid_api_key())


def set_acoustid_api_key(value: str | None) -> None:
    """Store or remove the AcoustID API key."""
    _set_secret(_ACOUSTID_ENTRY, value)


def get_audd_api_token() -> str | None:
    """Return the stored AudD API token."""
    return _get_secret(_AUDD_ENTRY)


def has_audd_api_token() -> bool:
    """Return True when an AudD token is stored."""
    return bool(get_audd_api_token())


def set_audd_api_token(value: str | None) -> None:
    """Store or remove the AudD API token."""
    _set_secret(_AUDD_ENTRY, value)


__all__ = [
    "SecretBackend",
    "SecretBackendUnavailableError",
    "SecretStoreError",
    "configure_secret_backend",
    "get_acoustid_api_key",
    "get_audd_api_token",
    "has_acoustid_api_key",
    "has_audd_api_token",
    "set_acoustid_api_key",
    "set_audd_api_token",
]

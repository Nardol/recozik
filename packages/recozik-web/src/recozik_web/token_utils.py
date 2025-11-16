"""Utilities for hashing and validating API tokens."""

from __future__ import annotations

import hashlib
import hmac

TOKEN_HASH_PREFIX = "sha256$"  # noqa: S105 - constant prefix, not a secret


def _sha256_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_token_for_storage(token: str) -> str:
    """Return the canonical storage representation for the provided token."""
    hint = token[-4:] if len(token) >= 4 else token
    digest = _sha256_digest(token)
    return f"{TOKEN_HASH_PREFIX}{digest}:{hint}"


def compare_token(candidate: str, stored: str) -> bool:
    """Return True when ``candidate`` matches the stored token representation."""
    if stored.startswith(TOKEN_HASH_PREFIX):
        digest = stored[len(TOKEN_HASH_PREFIX) :].split(":", 1)[0]
        candidate_digest = _sha256_digest(candidate)
        return hmac.compare_digest(digest, candidate_digest)
    # Legacy plaintext token, fall back to direct comparison.
    return hmac.compare_digest(candidate, stored)


def token_hint_from_stored(stored: str) -> str:
    """Return the short hint (usually last 4 chars) for display purposes."""
    if stored.startswith(TOKEN_HASH_PREFIX):
        _, _, hint = stored.partition(":")
        return hint or "????"
    return stored[-4:] if stored else "????"


def format_token_hint(hint: str) -> str:
    """Return a user-friendly hint string."""
    if not hint:
        return "****"
    masked_length = max(len(hint), 4)
    return f"{'*' * (masked_length if masked_length <= 8 else 4)}{hint}"


def hint_from_raw(token: str) -> str:
    """Return the last characters of the raw token for future reference."""
    return token[-4:] if token else ""

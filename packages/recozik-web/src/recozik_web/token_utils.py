"""Utilities for hashing and validating API tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Final

TOKEN_HASH_PREFIX: Final = "pbkdf2-sha256$"  # noqa: S105 - identifier prefix
PBKDF2_ITERATIONS: Final = 200_000
PBKDF2_SALT_BYTES: Final = 16


def _pbkdf2_digest(token: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, iterations)


def _encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_token_for_storage(token: str) -> str:
    """Return the canonical storage representation for the provided token."""
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    digest = _pbkdf2_digest(token, salt, PBKDF2_ITERATIONS)
    salt_b64 = _encode_bytes(salt)
    digest_b64 = _encode_bytes(digest)
    hint = hint_from_raw(token)
    body = f"{TOKEN_HASH_PREFIX}{PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"
    return f"{body}:{hint}"


def compare_token(candidate: str, stored: str) -> bool:
    """Return True when ``candidate`` matches the stored token representation."""
    if stored.startswith(TOKEN_HASH_PREFIX):
        body, _, _hint = stored.partition(":")
        try:
            _prefix, iterations, salt_b64, digest_b64 = body.split("$", 3)
        except ValueError:
            return False
        try:
            iterations_value = int(iterations)
        except ValueError:
            return False
        salt = _decode_bytes(salt_b64)
        expected_digest = _decode_bytes(digest_b64)
        candidate_pbkdf2 = _pbkdf2_digest(candidate, salt, iterations_value)
        return hmac.compare_digest(expected_digest, candidate_pbkdf2)
    # Legacy plaintext token, fall back to direct comparison.
    return hmac.compare_digest(candidate, stored)


def token_hint_from_stored(stored: str) -> str:
    """Return the short hint (usually last 4 chars) for display purposes."""
    _, _, hint = stored.partition(":")
    if hint:
        return hint
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

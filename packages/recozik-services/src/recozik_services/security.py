"""Shared auth/authorization primitives reused by every Recozik frontend."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ServiceFeature(Enum):
    """Enumerate service-level capabilities gated by access policies."""

    IDENTIFY = "identify"
    IDENTIFY_BATCH = "identify_batch"
    RENAME = "rename"
    AUDD = "audd"
    MUSICBRAINZ_ENRICH = "musicbrainz_enrich"


class QuotaScope(Enum):
    """Logical buckets enforced by quota policies."""

    ACOUSTID_LOOKUP = "acoustid_lookup"
    AUDD_STANDARD_LOOKUP = "audd_standard_lookup"
    AUDD_ENTERPRISE_LOOKUP = "audd_enterprise_lookup"
    MUSICBRAINZ_ENRICH = "musicbrainz_enrich"


@dataclass(slots=True)
class ServiceUser:
    """Lightweight description of the actor invoking a service."""

    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    roles: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def anonymous(cls) -> ServiceUser:
        """Return a sentinel user representing an anonymous caller."""
        return cls(user_id=None, roles=("anonymous",))

    def has_role(self, role: str) -> bool:
        """Return True if the user claims the provided role."""
        return role in self.roles


class AccessPolicyError(RuntimeError):
    """Base exception for access control violations."""


class AccessDeniedError(AccessPolicyError):
    """Raised when a user cannot invoke a requested feature."""


class QuotaPolicyError(RuntimeError):
    """Base exception for quota/rate limiting issues."""


class QuotaExceededError(QuotaPolicyError):
    """Raised when a caller exceeds their configured budget."""


class AccessPolicy(Protocol):
    """Policy interface used by services to validate feature access."""

    def ensure_feature(
        self,
        user: ServiceUser,
        feature: ServiceFeature,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Raise AccessPolicyError when the user cannot use the requested feature."""


class QuotaPolicy(Protocol):
    """Policy interface used by services to enforce budgets."""

    def consume(
        self,
        user: ServiceUser,
        scope: QuotaScope,
        *,
        cost: int = 1,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Raise QuotaPolicyError when the caller exceeds the allowed budget."""


class AllowAllAccessPolicy:
    """Default policy granting every feature."""

    def ensure_feature(
        self,
        user: ServiceUser,
        feature: ServiceFeature,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """No-op implementation that never denies access."""
        del user, feature, context
        return None


class UnlimitedQuotaPolicy:
    """Default policy that never throttles requests."""

    def consume(
        self,
        user: ServiceUser,
        scope: QuotaScope,
        *,
        cost: int = 1,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """No-op implementation that never records or rejects usage."""
        del user, scope, cost, context
        return None


__all__ = [
    "AccessDeniedError",
    "AccessPolicy",
    "AccessPolicyError",
    "AllowAllAccessPolicy",
    "QuotaExceededError",
    "QuotaPolicy",
    "QuotaPolicyError",
    "QuotaScope",
    "ServiceFeature",
    "ServiceUser",
    "UnlimitedQuotaPolicy",
]

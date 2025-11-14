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
        """Sentinel ServiceUser representing an unauthenticated (anonymous) caller.

        Returns:
            ServiceUser: A ServiceUser with user_id set to None and roles set to ("anonymous",).

        """
        return cls(user_id=None, roles=("anonymous",))

    def has_role(self, role: str) -> bool:
        """Check whether the user has the specified role.

        Returns:
            `true` if the user's roles include `role`, `false` otherwise.

        """
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
        """Validate that the given user is permitted to invoke the specified service feature.

        Parameters
        ----------
            context (Mapping[str, Any] | None): Optional additional information (for example request metadata or resource identifiers)
                that the policy may use when deciding access. May be None.

        Raises
        ------
            AccessPolicyError: If the user is not allowed to use the requested feature.

        """


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
        """Permit a quota consumption request without enforcing any limits.

        This implementation is a no-op: it does not track usage and will not raise quota-related errors.

        Parameters
        ----------
            user (ServiceUser): The actor consuming the quota.
            scope (QuotaScope): The quota scope to consume from.
            cost (int): The consumption cost to apply (default 1).
            context (Mapping[str, Any] | None): Optional additional context.

        """


class AllowAllAccessPolicy:
    """Default policy granting every feature."""

    def ensure_feature(
        self,
        user: ServiceUser,
        feature: ServiceFeature,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Allow access to the specified service feature for any user.

        Parameters
        ----------
            user: The actor invoking the feature.
            feature: The service-level capability being requested.
            context: Optional additional information about the request that policies may inspect.

        """
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
        """Permit the call to proceed without enforcing or recording any quota usage.

        Parameters
        ----------
            user (ServiceUser): The actor invoking the operation (ignored).
            scope (QuotaScope): The quota scope for the attempted operation (ignored).
            cost (int): Logical cost of the operation; default is 1 (ignored).
            context (Mapping[str, Any] | None): Optional metadata relevant to quota checks; may be None and is ignored.

        """
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

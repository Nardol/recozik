"""Lightweight auth + quota helpers for the web backend."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from recozik_services.security import (
    AccessDeniedError,
    AccessPolicy,
    QuotaExceededError,
    QuotaPolicy,
    QuotaScope,
    ServiceFeature,
    ServiceUser,
)

from .auth_store import TokenRecord, ensure_seed_tokens, get_token_repository
from .config import WebSettings, get_settings
from .persistent_quota import get_persistent_quota_policy
from .rate_limit import get_auth_rate_limiter

API_TOKEN_HEADER = "X-API-Token"  # noqa: S105 - header name, not credential

logger = logging.getLogger("recozik.web.auth")


@dataclass(frozen=True)
class TokenRule:
    """Describe what a static token may do within the service."""

    token: str
    user_id: str
    display_name: str
    roles: tuple[str, ...]
    allowed_features: tuple[ServiceFeature, ...]
    quota_limits: Mapping[QuotaScope, int | None]


class TokenAccessPolicy(AccessPolicy):
    """Authorize features based on attributes stored on the ServiceUser."""

    def ensure_feature(
        self,
        user: ServiceUser,
        feature: ServiceFeature,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Raise AccessDeniedError when the token is not allowed to use the feature."""
        allowed = user.attributes.get("allowed_features")
        if allowed and feature not in allowed:
            raise AccessDeniedError(f"{feature.value} not permitted for this token")


class InMemoryQuotaPolicy(QuotaPolicy):
    """Track quota usage in-process for each ServiceUser."""

    def __init__(self) -> None:
        """Initialize in-memory counters keyed by user ID."""
        self._counts: dict[str, Counter[QuotaScope]] = defaultdict(Counter)

    def consume(
        self,
        user: ServiceUser,
        scope: QuotaScope,
        *,
        cost: int = 1,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Increment usage for the provided scope and enforce limits."""
        limits: Mapping[QuotaScope, int | None] = user.attributes.get("quota_limits", {})
        limit = limits.get(scope)
        if limit is None:
            return
        user_key = user.user_id or "anonymous"
        current = self._counts[user_key][scope]
        if current + cost > limit:
            raise QuotaExceededError(
                f"Quota exceeded for {scope.value}: {current + cost} > {limit}"
            )
        self._counts[user_key][scope] = current + cost


_ACCESS_POLICY = TokenAccessPolicy()
# Note: _QUOTA_POLICY is created lazily in get_request_context to access settings


@dataclass
class RequestContext:
    """Aggregate the resolved user and shared policies for a request."""

    user: ServiceUser
    access_policy: AccessPolicy
    quota_policy: QuotaPolicy


def _build_token_rules(settings: WebSettings) -> dict[str, TokenRule]:
    """Return the static token map enforced by the access/quota policies."""
    features_all = {
        ServiceFeature.IDENTIFY,
        ServiceFeature.IDENTIFY_BATCH,
        ServiceFeature.RENAME,
    }
    if settings.musicbrainz_enabled:
        features_all.add(ServiceFeature.MUSICBRAINZ_ENRICH)
    if settings.audd_token:
        features_all.add(ServiceFeature.AUDD)

    rules: dict[str, TokenRule] = {}
    rules[settings.admin_token] = TokenRule(
        token=settings.admin_token,
        user_id="admin",
        display_name="Administrator",
        roles=("admin",),
        allowed_features=tuple(sorted(features_all, key=lambda item: item.value)),
        quota_limits={},
    )

    if settings.readonly_token:
        allowed_features = {ServiceFeature.IDENTIFY}
        if settings.musicbrainz_enabled:
            allowed_features.add(ServiceFeature.MUSICBRAINZ_ENRICH)
        quota_limits: dict[QuotaScope, int] = {}
        if settings.readonly_quota_acoustid is not None:
            quota_limits[QuotaScope.ACOUSTID_LOOKUP] = settings.readonly_quota_acoustid
        if settings.readonly_quota_musicbrainz is not None:
            quota_limits[QuotaScope.MUSICBRAINZ_ENRICH] = settings.readonly_quota_musicbrainz
        if settings.readonly_quota_audd_standard is not None:
            quota_limits[QuotaScope.AUDD_STANDARD_LOOKUP] = settings.readonly_quota_audd_standard
            allowed_features.add(ServiceFeature.AUDD)
        rules[settings.readonly_token] = TokenRule(
            token=settings.readonly_token,
            user_id="readonly",
            display_name="Readonly",
            roles=("readonly",),
            allowed_features=tuple(sorted(allowed_features, key=lambda item: item.value)),
            quota_limits=quota_limits,
        )

    return rules


def _seed_defaults(settings: WebSettings) -> list[TokenRecord]:
    defaults: list[TokenRecord] = []

    def _features_for(settings: WebSettings, readonly: bool) -> list[str]:
        feats = [ServiceFeature.IDENTIFY.value]
        if settings.musicbrainz_enabled:
            feats.append(ServiceFeature.MUSICBRAINZ_ENRICH.value)
        if not readonly:
            feats.extend([ServiceFeature.RENAME.value, ServiceFeature.IDENTIFY_BATCH.value])
        return feats

    defaults.append(
        TokenRecord(
            token=settings.admin_token,
            user_id="admin",
            display_name="Administrator",
            roles=["admin"],
            allowed_features=_features_for(settings, readonly=False),
            quota_limits={},
        )
    )
    if settings.readonly_token:
        quota_limits: dict[str, int | None] = {}
        if settings.readonly_quota_acoustid is not None:
            quota_limits[QuotaScope.ACOUSTID_LOOKUP.value] = settings.readonly_quota_acoustid
        if settings.readonly_quota_musicbrainz is not None:
            quota_limits[QuotaScope.MUSICBRAINZ_ENRICH.value] = settings.readonly_quota_musicbrainz
        if settings.readonly_quota_audd_standard is not None:
            quota_limits[QuotaScope.AUDD_STANDARD_LOOKUP.value] = (
                settings.readonly_quota_audd_standard
            )

        defaults.append(
            TokenRecord(
                token=settings.readonly_token,
                user_id="readonly",
                display_name="Readonly",
                roles=["readonly"],
                allowed_features=_features_for(settings, readonly=True),
                quota_limits=quota_limits,
            )
        )

    return defaults


def resolve_user_from_token(
    token: str, settings: WebSettings, *, request: Request | None = None
) -> ServiceUser:
    """Return the ServiceUser matching the provided API token.

    Args:
        token: API token to validate
        settings: Application settings
        request: Optional request object for logging

    Returns:
        ServiceUser instance if token is valid

    Raises:
        HTTPException: 401 if token is invalid

    """
    repo = get_token_repository(settings.auth_database_url_resolved)
    ensure_seed_tokens(repo, defaults=_seed_defaults(settings))
    record = repo.get(token)

    if not record:
        # Log failed authentication attempt
        client_ip = "unknown"
        if request and request.client:
            client_ip = request.client.host
        logger.warning(
            "Failed authentication attempt with invalid token from IP %s (token: %s...)",
            client_ip,
            token[:8] if len(token) >= 8 else "***",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")

    # Log successful authentication
    if request and request.client:
        logger.info(
            "Successful authentication for user '%s' from IP %s",
            record.user_id,
            request.client.host,
        )

    attributes = {
        "allowed_features": frozenset(record.allowed_features),
        "quota_limits": record.quota_limits,
    }
    return ServiceUser(
        user_id=record.user_id,
        email=None,
        display_name=record.display_name,
        roles=tuple(record.roles),
        attributes=attributes,
    )


def get_request_context(
    request: Request,
    api_token: str = Header(..., alias=API_TOKEN_HEADER),
    settings: WebSettings = Depends(get_settings),
) -> RequestContext:
    """FastAPI dependency injecting ServiceUser + policies.

    Args:
        request: FastAPI Request object
        api_token: API token from header
        settings: Application settings

    Returns:
        RequestContext with user and policies

    Raises:
        HTTPException: 429 if rate limit exceeded, 401 if auth fails

    """
    # Apply rate limiting if enabled
    if settings.rate_limit_enabled:
        auth_limiter = get_auth_rate_limiter(
            max_requests=settings.rate_limit_per_minute, window_seconds=60
        )
        try:
            auth_limiter.check_auth_attempt(request)
        except HTTPException:
            client_ip = request.client.host if request.client else "unknown"
            logger.warning("Rate limit exceeded for IP %s", client_ip)
            raise

    # Resolve user from token
    try:
        user = resolve_user_from_token(api_token, settings, request=request)
    except HTTPException:
        # Record failed attempt if rate limiting is enabled
        if settings.rate_limit_enabled:
            auth_limiter = get_auth_rate_limiter(
                max_requests=settings.rate_limit_per_minute, window_seconds=60
            )
            auth_limiter.record_failed_auth(request)
        raise

    # Record successful auth if rate limiting is enabled
    if settings.rate_limit_enabled:
        auth_limiter = get_auth_rate_limiter(
            max_requests=settings.rate_limit_per_minute, window_seconds=60
        )
        auth_limiter.record_successful_auth(request)

    # Use persistent quota policy
    quota_policy = get_persistent_quota_policy(
        database_url=settings.auth_database_url_resolved, window_hours=24
    )

    return RequestContext(user=user, access_policy=_ACCESS_POLICY, quota_policy=quota_policy)

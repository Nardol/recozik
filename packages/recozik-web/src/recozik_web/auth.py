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

from .auth_store import SeedToken, TokenRecord, ensure_seed_tokens, get_token_repository
from .config import WebSettings, get_settings
from .persistent_quota import get_persistent_quota_policy
from .rate_limit import get_auth_rate_limiter
from .token_utils import TOKEN_HASH_PREFIX, compare_token, hash_token_for_storage

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


def _convert_allowed_features(values: list[str]) -> frozenset[ServiceFeature]:
    """Return a frozenset of ServiceFeature enums, ignoring unknown entries."""
    converted: set[ServiceFeature] = set()
    for value in values:
        try:
            converted.add(ServiceFeature(value))
        except ValueError:
            logger.warning("Ignoring unknown feature on token: %s", value)
    return frozenset(converted)


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


def _features_for(settings: WebSettings, readonly: bool) -> list[str]:
    feats = [ServiceFeature.IDENTIFY.value]
    if settings.musicbrainz_enabled:
        feats.append(ServiceFeature.MUSICBRAINZ_ENRICH.value)
    audd_allowed = bool(settings.audd_token) and (
        not readonly or settings.readonly_quota_audd_standard is not None
    )
    if audd_allowed:
        feats.append(ServiceFeature.AUDD.value)
    if not readonly:
        feats.extend([ServiceFeature.RENAME.value, ServiceFeature.IDENTIFY_BATCH.value])
    return feats


def _seed_defaults(settings: WebSettings) -> list[SeedToken]:
    defaults: list[SeedToken] = []

    defaults.append(
        SeedToken(
            raw_value=settings.admin_token,
            record=TokenRecord(
                token=hash_token_for_storage(settings.admin_token),
                user_id="admin",
                display_name="Administrator",
                roles=["admin"],
                allowed_features=_features_for(settings, readonly=False),
                quota_limits={},
            ),
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
            SeedToken(
                raw_value=settings.readonly_token,
                record=TokenRecord(
                    token=hash_token_for_storage(settings.readonly_token),
                    user_id="readonly",
                    display_name="Readonly",
                    roles=["readonly"],
                    allowed_features=_features_for(settings, readonly=True),
                    quota_limits=quota_limits,
                ),
            )
        )

    return defaults


def resolve_user_from_token(
    token: str, settings: WebSettings, *, request: Request | None = None
) -> ServiceUser:
    """Return the ServiceUser matching the provided API token."""
    repo = get_token_repository(settings.auth_database_url_resolved)
    ensure_seed_tokens(repo, defaults=_seed_defaults(settings))
    record = repo.find_by_token_value(token)

    if record is None or not compare_token(token, record.token):
        client_ip = "unknown"
        if request and request.client:
            client_ip = request.client.host
        logger.warning(
            "Failed authentication attempt with invalid token from IP %s (token length: %d)",
            client_ip,
            len(token),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")

    if request and request.client:
        logger.info(
            "Successful authentication for user '%s' from IP %s",
            record.user_id,
            request.client.host,
        )

    if not record.token.startswith(TOKEN_HASH_PREFIX):
        updated = repo.replace_token_value(record.token, hash_token_for_storage(token))
        if updated:
            record = updated

    raw_limits = record.quota_limits or {}
    quota_limits: dict[QuotaScope, int | None] = {}
    for scope_key, value in raw_limits.items():
        try:
            quota_limits[QuotaScope(scope_key)] = value
        except ValueError:
            logger.warning("Invalid quota scope key in token: %s", scope_key)
            continue

    attributes = {
        "allowed_features": _convert_allowed_features(record.allowed_features),
        "quota_limits": quota_limits,
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
    api_token: str | None = Header(None, alias=API_TOKEN_HEADER),
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
            max_requests=settings.rate_limit_per_minute,
            window_seconds=60,
            trusted_proxies=settings.rate_limit_trusted_proxies,
        )
        try:
            auth_limiter.check_auth_attempt(request)
        except HTTPException:
            client_ip = request.client.host if request.client else "unknown"
            logger.warning("Rate limit exceeded for IP %s", client_ip)
            raise

    user: ServiceUser | None = None

    # Prefer session cookie if present
    from .auth_service import resolve_session_user  # local import to avoid cycles

    user = resolve_session_user(request, settings)

    # Fallback to API token header for machine clients
    if user is None:
        if not api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth")
        try:
            user = resolve_user_from_token(api_token, settings, request=request)
        except HTTPException:
            # Record failed attempt if rate limiting is enabled
            if settings.rate_limit_enabled:
                auth_limiter = get_auth_rate_limiter(
                    max_requests=settings.rate_limit_per_minute,
                    window_seconds=60,
                    trusted_proxies=settings.rate_limit_trusted_proxies,
                )
                auth_limiter.record_failed_auth(request)
            raise

    # Record successful auth if rate limiting is enabled
    if settings.rate_limit_enabled:
        auth_limiter = get_auth_rate_limiter(
            max_requests=settings.rate_limit_per_minute,
            window_seconds=60,
            trusted_proxies=settings.rate_limit_trusted_proxies,
        )
        auth_limiter.record_successful_auth(request)

    # Use persistent quota policy
    quota_policy = get_persistent_quota_policy(
        database_url=settings.auth_database_url_resolved, window_hours=24
    )

    return RequestContext(user=user, access_policy=_ACCESS_POLICY, quota_policy=quota_policy)

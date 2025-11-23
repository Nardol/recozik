"""Authentication service: password hashing, session issuance, user management."""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2 import exceptions as argon_exc
from argon2.low_level import Type
from fastapi import HTTPException, status
from recozik_services.security import ServiceFeature, ServiceUser

from .auth_models import AuthStore, SessionToken, User, get_auth_store
from .config import WebSettings
from .token_utils import hash_token_for_storage

logger = logging.getLogger(__name__)

ph = PasswordHasher(
    time_cost=2,
    memory_cost=19_456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
DUMMY_HASH = ph.hash("dummy-password-for-timing")
UTC = dt.timezone.utc


ACCESS_TTL = dt.timedelta(hours=1)
REFRESH_TTL_SHORT = dt.timedelta(days=7)
REFRESH_TTL_LONG = dt.timedelta(days=30)


@dataclass
class SessionPair:
    """Pair of access/refresh tokens with expiry metadata."""

    session_id: str
    refresh_token: str
    access_expires_at: dt.datetime
    refresh_expires_at: dt.datetime
    remember: bool


def hash_password(password: str) -> str:
    """Return Argon2id hash for the given password."""
    return ph.hash(password)


def validate_password_strength(password: str) -> None:
    """Raise HTTP 400 if password is too weak."""
    if len(password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 12 characters",
        )
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must include an uppercase letter",
        )
    if not any(c.islower() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must include a lowercase letter",
        )
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must include a digit",
        )
    if not any(not ch.isalnum() for ch in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must include a symbol",
        )


def verify_password(password: str, hashed: str) -> bool:
    """Return True if password matches the stored hash."""
    try:
        return ph.verify(hashed, password)
    except (argon_exc.VerifyMismatchError, argon_exc.InvalidHashError):
        return False
    except Exception:  # pragma: no cover - unexpected errors
        logger.exception("Unexpected error verifying password")
        return False


def seed_admin_user(store: AuthStore, settings: WebSettings) -> None:
    """Create an admin user if none exists."""
    admin = store.get_user(settings.admin_username)
    if admin:
        return
    validate_password_strength(settings.admin_password)
    admin_user = User(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password),
        roles=["admin"],
        allowed_features=[feat.value for feat in ServiceFeature],
        quota_limits={},
    )
    store.create_user(admin_user)


def issue_session(user: User, remember: bool, store: AuthStore) -> SessionPair:
    """Persist a new session + refresh token pair."""
    now = dt.datetime.now(UTC)
    access_expires = now + ACCESS_TTL
    refresh_expires = now + (REFRESH_TTL_LONG if remember else REFRESH_TTL_SHORT)
    session_id = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    store.save_session(
        SessionToken(
            session_id=hash_token_for_storage(session_id),
            user_id=user.id,  # type: ignore[arg-type]
            refresh_token=hash_token_for_storage(refresh_token),
            created_at=now,
            expires_at=access_expires,
            refresh_expires_at=refresh_expires,
            remember=remember,
        )
    )
    return SessionPair(
        session_id=session_id,
        refresh_token=refresh_token,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires,
        remember=remember,
    )


def build_service_user(user: User) -> ServiceUser:
    """Convert DB user to ServiceUser for policies."""
    return ServiceUser(
        user_id=user.username,
        roles=tuple(user.roles),
        attributes={
            "allowed_features": {ServiceFeature(value) for value in user.allowed_features},
            "quota_limits": user.quota_limits,
        },
    )


def ensure_login_enabled(settings: WebSettings) -> None:
    """Guard against unsafe defaults in production."""
    if settings.production_mode and settings.admin_password == "dev-password":  # noqa: S105
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unsafe admin password in production",
        )


# Cookie helpers
ACCESS_COOKIE = "recozik_session"
REFRESH_COOKIE = "recozik_refresh"
CSRF_COOKIE = "recozik_csrf"
COOKIE_PATH = "/"


def set_session_cookies(
    response,
    pair: SessionPair,
    settings: WebSettings,
) -> None:
    """Set HttpOnly cookies for access and refresh tokens."""
    secure = settings.production_mode
    samesite = "strict" if secure else "lax"
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        ACCESS_COOKIE,
        pair.session_id,
        expires=pair.access_expires_at,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path=COOKIE_PATH,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        expires=pair.refresh_expires_at,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path=COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        expires=pair.access_expires_at,
        httponly=False,
        secure=secure,
        samesite=samesite,
        path=COOKIE_PATH,
    )


def clear_session_cookies(response) -> None:
    """Clear session cookies."""
    # best-effort: clear both secure/non-secure variants
    for secure_flag in (False, True):
        response.delete_cookie(ACCESS_COOKIE, path=COOKIE_PATH, httponly=True, secure=secure_flag)
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, secure=secure_flag)
        response.delete_cookie(CSRF_COOKIE, path=COOKIE_PATH, httponly=False, secure=secure_flag)


def resolve_session_user(request, settings: WebSettings) -> ServiceUser | None:
    """Resolve user from session cookie if present and valid."""
    session_id = request.cookies.get(ACCESS_COOKIE)
    if not session_id:
        return None
    store = get_auth_store(settings.auth_database_url_resolved)
    record = store.get_session_by_id(session_id)
    if not record:
        return None
    now = dt.datetime.now(UTC)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        store.delete_session(session_id)
        return None
    user = store.get_user_by_id(record.user_id)
    if not user:
        store.delete_session(session_id)
        return None
    return build_service_user(user)

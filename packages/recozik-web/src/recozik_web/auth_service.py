"""Authentication service: password hashing, session issuance, user management."""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from fastapi import HTTPException, status
from recozik_services.security import ServiceFeature, ServiceUser

from .auth_models import AuthStore, SessionToken, User, get_auth_store
from .config import WebSettings

ph = PasswordHasher()


ACCESS_TTL = dt.timedelta(hours=1)
REFRESH_TTL = dt.timedelta(days=7)


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


def verify_password(password: str, hashed: str) -> bool:
    """Return True if password matches the stored hash."""
    try:
        return ph.verify(hashed, password)
    except Exception:
        return False


def seed_admin_user(store: AuthStore, settings: WebSettings) -> None:
    """Create an admin user if none exists."""
    admin = store.get_user(settings.admin_username)
    if admin:
        return
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
    now = dt.datetime.utcnow()
    access_expires = now + (REFRESH_TTL if remember else ACCESS_TTL)
    refresh_expires = now + REFRESH_TTL
    session_id = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    store.save_session(
        SessionToken(
            session_id=session_id,
            user_id=user.id,  # type: ignore[arg-type]
            refresh_token=refresh_token,
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
COOKIE_PATH = "/"


def set_session_cookies(
    response,
    pair: SessionPair,
) -> None:
    """Set HttpOnly cookies for access and refresh tokens."""
    response.set_cookie(
        ACCESS_COOKIE,
        pair.session_id,
        expires=pair.access_expires_at,
        httponly=True,
        secure=True,
        samesite="strict",
        path=COOKIE_PATH,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        expires=pair.refresh_expires_at,
        httponly=True,
        secure=True,
        samesite="strict",
        path=COOKIE_PATH,
    )


def clear_session_cookies(response) -> None:
    """Clear session cookies."""
    response.delete_cookie(ACCESS_COOKIE, path=COOKIE_PATH, httponly=True, secure=True)
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, httponly=True, secure=True)


def resolve_session_user(request, settings: WebSettings) -> ServiceUser | None:
    """Resolve user from session cookie if present and valid."""
    session_id = request.cookies.get(ACCESS_COOKIE)
    if not session_id:
        return None
    store = get_auth_store(settings.auth_database_url_resolved)
    record = store.get_session_by_id(session_id)
    if not record:
        return None
    now = dt.datetime.utcnow()
    if record.expires_at <= now:
        store.delete_session(session_id)
        return None
    user = store.get_user_by_id(record.user_id)
    if not user:
        store.delete_session(session_id)
        return None
    return build_service_user(user)

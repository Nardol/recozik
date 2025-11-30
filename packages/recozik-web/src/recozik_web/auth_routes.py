"""Authentication routes for login/password + sessions."""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from recozik_services.security import ServiceUser

from .auth_models import User, get_auth_store
from .auth_service import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    DUMMY_HASH,
    REFRESH_COOKIE,
    clear_session_cookies,
    hash_password,
    issue_session,
    resolve_session_user,
    set_session_cookies,
    validate_password_strength,
    verify_password,
)
from .config import WebSettings, get_settings
from .rate_limit import get_auth_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def validate_email_format(email: str) -> str:
    """Validate email format and normalize to lowercase.

    Only validates on user input, not on database load.
    Raises HTTPException with 400 status if invalid.
    """
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
    # Simple but effective email regex pattern
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")
    return email.lower()  # Normalize to lowercase


class LoginRequest(BaseModel):
    """Login payload."""

    username: str
    password: str
    remember: bool = False


class LoginResponse(BaseModel):
    """Login/refresh response with expiry info."""

    username: str
    roles: list[str]
    allowed_features: list[str]
    access_expires_at: dt.datetime
    refresh_expires_at: dt.datetime


class RegisterRequest(BaseModel):
    """Admin-only user creation payload."""

    username: str
    email: str
    display_name: str | None = None
    password: str
    roles: list[str] = Field(default_factory=lambda: ["user"])
    allowed_features: list[str] = Field(default_factory=list)
    quota_limits: dict[str, int | None] = Field(default_factory=dict)


class ChangePasswordRequest(BaseModel):
    """Payload for changing the current user's password."""

    old_password: str
    new_password: str


class UpdateUserRequest(BaseModel):
    """Admin payload for updating a user (all fields optional for partial update)."""

    email: str | None = None
    display_name: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None
    allowed_features: list[str] | None = None
    quota_limits: dict[str, int | None] | None = None


class AdminResetPasswordRequest(BaseModel):
    """Admin-only password reset (no old password required)."""

    new_password: str


class UserResponse(BaseModel):
    """Public user info (no password hash)."""

    id: int
    username: str
    email: str | None
    display_name: str | None
    is_active: bool
    roles: list[str]
    allowed_features: list[str]
    quota_limits: dict[str, int | None]
    created_at: dt.datetime


class SessionResponse(BaseModel):
    """Public session info (no token values)."""

    id: int
    user_id: int
    created_at: dt.datetime
    expires_at: dt.datetime
    refresh_expires_at: dt.datetime
    remember: bool


def _require_admin(user: ServiceUser | None) -> ServiceUser:
    if not user or "admin" not in user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


def _user_to_response(user: User) -> UserResponse:
    """Convert User model to UserResponse."""
    return UserResponse(
        id=user.id,  # type: ignore[arg-type]
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=user.roles,
        allowed_features=user.allowed_features,
        quota_limits=user.quota_limits,
        created_at=user.created_at,
    )


def _require_user(user: ServiceUser | None) -> ServiceUser:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")
    return user


def get_session_user(
    request: Request,
    settings: Annotated[WebSettings, Depends(get_settings)],
) -> ServiceUser | None:
    """Return user from session cookie or None."""
    return resolve_session_user(request, settings)


def _validate_csrf(request: Request, settings: WebSettings) -> None:
    """Double-submit cookie defense: cookie must match header."""
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )


def _maybe_limiter(settings: WebSettings, max_requests: int = 5):
    if not settings.rate_limit_enabled:
        return None
    return get_auth_rate_limiter(
        max_requests=max_requests,
        window_seconds=60,
        trusted_proxies=settings.rate_limit_trusted_proxies,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Authenticate user with password and set session cookies."""
    limiter = _maybe_limiter(settings, max_requests=5)
    if limiter:
        limiter.check_auth_attempt(request)
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user(payload.username)
    password_hash = user.password_hash if user else DUMMY_HASH
    password_ok = verify_password(payload.password, password_hash)
    if not (user and password_ok):
        if limiter:
            limiter.record_failed_auth(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    assert user is not None
    if limiter:
        limiter.record_successful_auth(request)
    pair = issue_session(user, payload.remember, store)
    set_session_cookies(response, pair, settings)
    return LoginResponse(
        username=user.username,
        roles=user.roles,
        allowed_features=user.allowed_features,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: Request,
    response: Response,
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Rotate session using refresh cookie."""
    limiter = _maybe_limiter(settings, max_requests=10)
    if limiter:
        limiter.check_auth_attempt(request)
    _validate_csrf(request, settings)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        if limiter:
            limiter.record_failed_auth(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    store = get_auth_store(settings.auth_database_url_resolved)
    record = store.get_session_by_refresh(refresh_token)
    if not record:
        if limiter:
            limiter.record_failed_auth(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    now = dt.datetime.now(dt.timezone.utc)
    refresh_expires_at = record.refresh_expires_at
    if refresh_expires_at.tzinfo is None:
        refresh_expires_at = refresh_expires_at.replace(tzinfo=dt.timezone.utc)
    if refresh_expires_at <= now:
        if limiter:
            limiter.record_failed_auth(request)
        store.delete_session_record(record)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh expired")
    user = store.get_user_by_id(record.user_id)
    if not user:
        if limiter:
            limiter.record_failed_auth(request)
        store.delete_session_record(record)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User missing")

    # rotate session
    if limiter:
        limiter.record_successful_auth(request)
    store.delete_session_record(record)
    pair = issue_session(user, record.remember, store)
    set_session_cookies(response, pair, settings)
    return LoginResponse(
        username=user.username,
        roles=user.roles,
        allowed_features=user.allowed_features,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Invalidate current session and refresh tokens."""
    _validate_csrf(request, settings)
    session_id = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    store = get_auth_store(settings.auth_database_url_resolved)
    if session_id:
        store.delete_session(session_id)
    if refresh_token:
        record = store.get_session_by_refresh(refresh_token)
        if record:
            store.delete_session_record(record)
    clear_session_cookies(response)
    return {"status": "ok"}


@router.post("/register")
def register_user(
    payload: RegisterRequest,
    request: Request,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Create a new user (admin only)."""
    limiter = _maybe_limiter(settings, max_requests=5)
    if limiter:
        limiter.check_auth_attempt(request)
    _validate_csrf(request, settings)
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    if store.get_user(payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot create user")
    hash_password(payload.password)  # ensure consistent timing
    validate_password_strength(payload.password)
    # Validate and normalize email format
    validated_email = validate_email_format(payload.email)
    user = User(
        username=payload.username,
        email=validated_email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        roles=payload.roles,
        allowed_features=payload.allowed_features,
        quota_limits=payload.quota_limits,
    )
    store.create_user(user)
    if limiter:
        limiter.record_successful_auth(request)
    return {"status": "ok"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    request: Request,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Change password for the current user and purge sessions."""
    limiter = _maybe_limiter(settings, max_requests=5)
    if limiter:
        limiter.check_auth_attempt(request)
    _validate_csrf(request, settings)
    user = _require_user(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    db_user = store.get_user(user.user_id)  # type: ignore[arg-type]
    if not db_user or not verify_password(payload.old_password, db_user.password_hash):
        if limiter:
            limiter.record_failed_auth(request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    validate_password_strength(payload.new_password)
    db_user.password_hash = hash_password(payload.new_password)
    store.upsert_user(db_user)
    store.purge_user_sessions(db_user.id)  # type: ignore[arg-type]
    clear_session_cookies(response)
    if limiter:
        limiter.record_successful_auth(request)
    return {"status": "ok"}


# Admin-only user management endpoints
admin_router = APIRouter(prefix="/admin/users", tags=["admin"])


@admin_router.get("", response_model=list[UserResponse])
def list_users(
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
    limit: int = 100,
    offset: int = 0,
):
    """List all users (admin only)."""
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    users = store.list_users(limit=limit, offset=offset)
    return [_user_to_response(u) for u in users]


@admin_router.get("/{user_id}", response_model=UserResponse)
def get_user_detail(
    user_id: int,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Get specific user details (admin only)."""
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_response(user)


@admin_router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    request: Request,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Update user roles/features/quotas (admin only, requires CSRF)."""
    _validate_csrf(request, settings)
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.email is not None:
        # Validate and normalize email format
        user.email = validate_email_format(payload.email)
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.roles is not None:
        user.roles = payload.roles
    if payload.allowed_features is not None:
        user.allowed_features = payload.allowed_features
    if payload.quota_limits is not None:
        user.quota_limits = payload.quota_limits
    store.upsert_user(user)
    return _user_to_response(user)


@admin_router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Delete a user and all their sessions (admin only, requires CSRF)."""
    _validate_csrf(request, settings)
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    deleted = store.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"status": "ok"}


@admin_router.post("/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    request: Request,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Reset user password (admin only, requires CSRF, purges their sessions)."""
    _validate_csrf(request, settings)
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    validate_password_strength(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    store.upsert_user(user)
    store.purge_user_sessions(user.id)  # type: ignore[arg-type]
    return {"status": "ok"}


@admin_router.get("/{user_id}/sessions", response_model=list[SessionResponse])
def get_user_sessions(
    user_id: int,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """List active sessions for a user (admin only)."""
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    sessions = store.get_user_sessions(user_id)
    return [
        SessionResponse(
            id=s.id,  # type: ignore[arg-type]
            user_id=s.user_id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            refresh_expires_at=s.refresh_expires_at,
            remember=s.remember,
        )
        for s in sessions
    ]


@admin_router.delete("/{user_id}/sessions")
def revoke_user_sessions(
    user_id: int,
    request: Request,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Revoke all sessions for a user (admin only, requires CSRF)."""
    _validate_csrf(request, settings)
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    store.purge_user_sessions(user_id)
    return {"status": "ok"}

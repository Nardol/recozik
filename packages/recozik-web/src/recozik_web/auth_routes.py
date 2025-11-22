"""Authentication routes for login/password + sessions."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from recozik_services.security import ServiceUser

from .auth_models import User, get_auth_store
from .auth_service import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_session_cookies,
    hash_password,
    issue_session,
    resolve_session_user,
    set_session_cookies,
    verify_password,
)
from .config import WebSettings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


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
    password: str
    roles: list[str] = Field(default_factory=lambda: ["user"])
    allowed_features: list[str] = Field(default_factory=list)
    quota_limits: dict[str, int | None] = Field(default_factory=dict)


class ChangePasswordRequest(BaseModel):
    """Payload for changing the current user's password."""

    old_password: str
    new_password: str


def _require_admin(user: ServiceUser | None) -> ServiceUser:
    if not user or "admin" not in user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


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


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Authenticate user with password and set session cookies."""
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user(payload.username)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    pair = issue_session(user, payload.remember, store)
    set_session_cookies(response, pair)
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
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    store = get_auth_store(settings.auth_database_url_resolved)
    record = store.get_session_by_refresh(refresh_token)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    now = dt.datetime.utcnow()
    if record.refresh_expires_at <= now:
        store.delete_session(record.session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh expired")
    user = store.get_user_by_id(record.user_id)
    if not user:
        store.delete_session(record.session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User missing")

    # rotate session
    store.delete_session(record.session_id)
    pair = issue_session(user, record.remember, store)
    set_session_cookies(response, pair)
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
    session_id = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    store = get_auth_store(settings.auth_database_url_resolved)
    if session_id:
        store.delete_session(session_id)
    if refresh_token:
        record = store.get_session_by_refresh(refresh_token)
        if record:
            store.delete_session(record.session_id)
    clear_session_cookies(response)
    return {"status": "ok"}


@router.post("/register", response_model=LoginResponse)
def register_user(
    payload: RegisterRequest,
    response: Response,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Create a new user (admin only) and issue a session."""
    _require_admin(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    if store.get_user(payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        roles=payload.roles,
        allowed_features=payload.allowed_features,
        quota_limits=payload.quota_limits,
    )
    store.create_user(user)
    pair = issue_session(user, remember=False, store=store)
    set_session_cookies(response, pair)
    return LoginResponse(
        username=user.username,
        roles=user.roles,
        allowed_features=user.allowed_features,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    current_user: Annotated[ServiceUser | None, Depends(get_session_user)],
    settings: Annotated[WebSettings, Depends(get_settings)],
):
    """Change password for the current user and purge sessions."""
    user = _require_user(current_user)
    store = get_auth_store(settings.auth_database_url_resolved)
    db_user = store.get_user(user.user_id)  # type: ignore[arg-type]
    if not db_user or not verify_password(payload.old_password, db_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    db_user.password_hash = hash_password(payload.new_password)
    store.upsert_user(db_user)
    store.purge_user_sessions(db_user.id)  # type: ignore[arg-type]
    clear_session_cookies(response)
    return {"status": "ok"}

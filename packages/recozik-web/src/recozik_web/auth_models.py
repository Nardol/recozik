"""Auth models and persistence for users and sessions."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .token_utils import compare_token


class User(SQLModel, table=True):
    """User account with hashed password and allowed features/roles."""

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    roles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_features: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    quota_limits: dict[str, int | None] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class SessionToken(SQLModel, table=True):
    """Opaque session + refresh tokens tracked server-side."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    refresh_token: str = Field(index=True, unique=True)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    expires_at: dt.datetime
    refresh_expires_at: dt.datetime
    remember: bool = Field(default=False)


class AuthStore:
    """Persistence layer for users and sessions."""

    def __init__(self, database_url: str) -> None:
        """Initialize the store engine."""
        connect_args = {}
        if database_url.startswith("sqlite:///"):
            sqlite_path = Path(database_url.replace("sqlite:///", "", 1))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}
        self.engine = create_engine(database_url, connect_args=connect_args)
        SQLModel.metadata.create_all(self.engine)

    def _session(self) -> Session:
        return Session(self.engine)

    # Users
    def get_user(self, username: str) -> User | None:
        """Return user by username."""
        with self._session() as session:
            stmt = select(User).where(User.username == username)
            return session.exec(stmt).first()

    def get_user_by_id(self, user_id: int) -> User | None:
        """Return user by id."""
        with self._session() as session:
            return session.get(User, user_id)

    def create_user(self, user: User) -> User:
        """Persist a new user."""
        with self._session() as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def upsert_user(self, user: User) -> User:
        """Insert or update a user keyed by primary key."""
        with self._session() as session:
            session.merge(user)
            session.commit()
            stored = session.exec(select(User).where(User.username == user.username)).first()
            return stored or user

    # Sessions
    def save_session(self, token: SessionToken) -> SessionToken:
        """Persist a session token."""
        with self._session() as session:
            session.add(token)
            session.commit()
            session.refresh(token)
            return token

    def get_session_by_id(self, session_token: str) -> SessionToken | None:
        """Return session by id (hashed storage, constant-time comparison)."""
        with self._session() as session:
            now = dt.datetime.now(dt.timezone.utc)
            rows = session.exec(select(SessionToken).where(SessionToken.expires_at > now)).all()
            for row in rows:
                if compare_token(session_token, row.session_id):
                    return row
            return None

    def get_session_by_refresh(self, refresh_token: str) -> SessionToken | None:
        """Return session by refresh token (hashed storage)."""
        with self._session() as session:
            now = dt.datetime.now(dt.timezone.utc)
            for row in session.exec(
                select(SessionToken).where(SessionToken.refresh_expires_at > now)
            ).all():
                if compare_token(refresh_token, row.refresh_token):
                    return row
            return None

    def delete_session(self, session_token: str) -> None:
        """Delete a session by id (raw token)."""
        with self._session() as session:
            row = None
            for candidate in session.exec(select(SessionToken)).all():
                if compare_token(session_token, candidate.session_id):
                    row = candidate
                    break
            if row:
                session.delete(row)
                session.commit()

    def delete_session_record(self, record: SessionToken) -> None:
        """Delete the provided session record."""
        with self._session() as session:
            persistent = session.get(SessionToken, record.id)
            if persistent:
                session.delete(persistent)
                session.commit()

    def purge_user_sessions(self, user_id: int) -> None:
        """Delete all sessions for a user."""
        with self._session() as session:
            rows = session.exec(select(SessionToken).where(SessionToken.user_id == user_id)).all()
            for row in rows:
                session.delete(row)
            session.commit()

    def delete_expired_sessions(self, before: dt.datetime) -> int:
        """Delete all sessions expired before timestamp; return count."""
        with self._session() as session:
            rows = session.exec(
                select(SessionToken).where(SessionToken.refresh_expires_at <= before)
            ).all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            session.commit()
            return count


_STORES: dict[str, AuthStore] = {}


def get_auth_store(database_url: str) -> AuthStore:
    """Return cached AuthStore for the given DB URL."""
    store = _STORES.get(database_url)
    if store is None:
        store = AuthStore(database_url)
        _STORES[database_url] = store
    return store

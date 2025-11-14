"""Persistent token/quota store backed by SQLModel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import JSON, Column, Field, Session, SQLModel, create_engine, select


class TokenRecord(SQLModel, table=True):
    """Stored representation of an API token."""

    token: str = Field(primary_key=True)
    user_id: str
    display_name: str
    roles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_features: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    quota_limits: dict[str, int | None] = Field(default_factory=dict, sa_column=Column(JSON))


class TokenRepository:
    """Repository used to manage API tokens in SQLite."""

    def __init__(self, database_url: str) -> None:
        """Initialize the SQLModel engine for token persistence."""
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite:///"):
            sqlite_path = Path(database_url.replace("sqlite:///", "", 1))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}
        self._engine = create_engine(database_url, connect_args=connect_args)
        SQLModel.metadata.create_all(self._engine)

    def list_tokens(self) -> list[TokenRecord]:
        """Return all token rows."""
        with Session(self._engine) as session:
            statement = select(TokenRecord)
            return list(session.exec(statement))

    def get(self, token: str) -> TokenRecord | None:
        """Return the token matching the provided value."""
        with Session(self._engine) as session:
            return session.get(TokenRecord, token)

    def upsert(self, record: TokenRecord) -> TokenRecord:
        """Insert or update a token and return the stored row."""
        with Session(self._engine) as session:
            session.merge(record)
            session.commit()
            return session.get(TokenRecord, record.token)


_REPOSITORIES: dict[str, TokenRepository] = {}


def get_token_repository(database_url: str) -> TokenRepository:
    """Return cached token repository for the given path."""
    repo = _REPOSITORIES.get(database_url)
    if repo is None:
        repo = TokenRepository(database_url)
        _REPOSITORIES[database_url] = repo
    return repo


def ensure_seed_tokens(repo: TokenRepository, *, defaults: list[TokenRecord]) -> None:
    """Insert default tokens if the DB is empty."""
    if repo.list_tokens():
        return
    for record in defaults:
        repo.upsert(record)

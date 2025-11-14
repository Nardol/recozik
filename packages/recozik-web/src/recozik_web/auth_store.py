"""Persistent token/quota store backed by SQLModel."""

from __future__ import annotations

from pathlib import Path

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

    def __init__(self, db_path: Path) -> None:
        """Initialize the SQLite engine for token persistence."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
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


_REPOSITORIES: dict[Path, TokenRepository] = {}


def get_token_repository(db_path: Path) -> TokenRepository:
    """Return cached token repository for the given path."""
    repo = _REPOSITORIES.get(db_path)
    if repo is None:
        repo = TokenRepository(db_path)
        _REPOSITORIES[db_path] = repo
    return repo


def ensure_seed_tokens(repo: TokenRepository, *, defaults: list[TokenRecord]) -> None:
    """Insert default tokens if the DB is empty."""
    if repo.list_tokens():
        return
    for record in defaults:
        repo.upsert(record)

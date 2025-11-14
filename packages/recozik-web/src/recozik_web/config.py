"""Application configuration helpers for the Recozik web backend."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebSettings(BaseSettings):
    """Environment-driven settings consumed by the FastAPI app."""

    model_config = SettingsConfigDict(env_prefix="RECOZIK_WEB_", extra="ignore")

    admin_token: str = "dev-admin"  # noqa: S105 - default token for local dev
    readonly_token: str | None = None
    acoustid_api_key: str = "demo-key"
    audd_token: str | None = None
    audd_endpoint_standard: str = "https://api.audd.io"
    audd_endpoint_enterprise: str = "https://enterprise.audd.io"
    base_media_root: Path = Path.cwd()
    cache_enabled: bool = True
    cache_ttl_hours: int = 24
    musicbrainz_enabled: bool = True
    musicbrainz_app_name: str = "recozik-web"
    musicbrainz_app_version: str = "0"
    musicbrainz_contact: str | None = None
    readonly_quota_acoustid: int | None = None
    readonly_quota_musicbrainz: int | None = None
    readonly_quota_audd_standard: int | None = None
    max_upload_mb: int = 32
    upload_subdir: str = "uploads"
    jobs_db_filename: str = "jobs.db"
    auth_db_filename: str = "auth.db"

    @model_validator(mode="after")
    def _resolve_media_root(self) -> WebSettings:
        """Normalize the media + upload paths."""
        self.base_media_root = self.base_media_root.expanduser().resolve()
        subdir = Path(self.upload_subdir.strip() or "uploads")
        if subdir.is_absolute() or ".." in subdir.parts:
            msg = "upload_subdir must be a relative, safe path"
            raise ValueError(msg)
        self.upload_subdir = subdir.as_posix()
        return self

    @property
    def upload_directory(self) -> Path:
        """Return the absolute upload directory."""
        return (self.base_media_root / self.upload_subdir).resolve()

    @property
    def jobs_database_path(self) -> Path:
        """Return the SQLite path used for job persistence."""
        return (self.base_media_root / self.jobs_db_filename).resolve()

    @property
    def auth_database_path(self) -> Path:
        """Return the SQLite path used for token persistence."""
        return (self.base_media_root / self.auth_db_filename).resolve()


@lru_cache
def get_settings() -> WebSettings:
    """Return cached settings instance."""
    return WebSettings()

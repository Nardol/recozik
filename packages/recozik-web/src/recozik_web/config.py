"""Application configuration helpers for the Recozik web backend."""

from __future__ import annotations

import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebSettings(BaseSettings):
    """Environment-driven settings consumed by the FastAPI app."""

    model_config = SettingsConfigDict(env_prefix="RECOZIK_WEB_", extra="ignore")

    admin_token: str = "dev-admin"  # noqa: S105 - default token for local dev
    readonly_token: str | None = None
    production_mode: bool = False
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
    jobs_database_url: str | None = None
    auth_database_url: str | None = None

    # Security settings
    cors_enabled: bool = False
    cors_origins: list[str] = []
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_trusted_proxies: int = 0
    allowed_upload_extensions: list[str] = [
        ".mp3",
        ".flac",
        ".wav",
        ".ogg",
        ".m4a",
        ".aac",
        ".opus",
        ".wma",
    ]
    security_headers_enabled: bool = True
    security_csp: str | None = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    security_referrer_policy: str = "same-origin"
    security_permissions_policy: str | None = None
    security_hsts_max_age: int = 63072000
    security_hsts_include_subdomains: bool = True
    security_hsts_preload: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value) -> list[str]:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value or []

    @field_validator("allowed_upload_extensions", mode="before")
    @classmethod
    def normalize_extensions(cls, value) -> list[str]:
        """Normalize file extensions to lowercase."""
        if isinstance(value, list):
            return [ext.lower() if isinstance(ext, str) else ext for ext in value]
        return value or []

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

    @model_validator(mode="after")
    def _validate_production_security(self) -> WebSettings:
        """Ensure admin token is secure in production mode."""
        if self.production_mode and self.admin_token == "dev-admin":  # noqa: S105
            msg = (
                "SECURITY ERROR: Default admin token detected in production mode!\n"
                "Set RECOZIK_WEB_ADMIN_TOKEN to a secure random value.\n"
                f"Example: RECOZIK_WEB_ADMIN_TOKEN={secrets.token_urlsafe(32)}"
            )
            print(msg, file=sys.stderr)
            raise ValueError(msg)
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

    @property
    def jobs_database_url_resolved(self) -> str:
        """Return the configured jobs DB URL, defaulting to SQLite in base dir."""
        return self.jobs_database_url or f"sqlite:///{self.jobs_database_path}"

    @property
    def auth_database_url_resolved(self) -> str:
        """Return the configured auth DB URL, defaulting to SQLite in base dir."""
        return self.auth_database_url or f"sqlite:///{self.auth_database_path}"


@lru_cache
def get_settings() -> WebSettings:
    """Return cached settings instance."""
    return WebSettings()

"""FastAPI application exposing Recozik services."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from recozik_services import (
    AudDConfig,
    IdentifyRequest,
    IdentifyResponse,
    IdentifyServiceError,
    identify_track,
)
from recozik_services.cli_support.musicbrainz import MusicBrainzOptions, build_settings
from recozik_services.security import AccessPolicyError, QuotaPolicyError

from recozik_core.audd import AudDEnterpriseParams, AudDMode
from recozik_core.fingerprint import AcoustIDMatch

from .auth import RequestContext, get_request_context
from .config import WebSettings, get_settings

logger = logging.getLogger("recozik.web")
app = FastAPI(title="Recozik Web API", version="0.1.0")


class LoggingCallbacks:
    """ServiceCallbacks implementation that logs messages instead of printing."""

    def info(self, message: str) -> None:  # pragma: no cover - trivial logging
        """Log informational messages coming from the services layer."""
        logger.info(message)

    def warning(self, message: str) -> None:  # pragma: no cover - trivial logging
        """Log warning messages coming from the services layer."""
        logger.warning(message)

    def error(self, message: str) -> None:  # pragma: no cover - trivial logging
        """Log error messages coming from the services layer."""
        logger.error(message)


CALLBACKS = LoggingCallbacks()


class IdentifyRequestPayload(BaseModel):
    """Input schema for /identify/from-path."""

    audio_path: str = Field(..., description="Path relative to the configured media root.")
    refresh_cache: bool = False
    cache_enabled: bool | None = None
    cache_ttl_hours: int | None = None
    metadata_fallback: bool = True
    prefer_audd: bool = False
    force_audd_enterprise: bool = False
    enable_audd: bool | None = None


class ReleaseModel(BaseModel):
    """Serialized release information returned in identify responses."""

    title: str | None = None
    release_id: str | None = None
    date: str | None = None
    country: str | None = None


class MatchModel(BaseModel):
    """Serialized match entry returned in identify responses."""

    score: float
    recording_id: str | None = None
    title: str | None = None
    artist: str | None = None
    release_group_id: str | None = None
    release_group_title: str | None = None
    releases: list[ReleaseModel]


class IdentifyResponseModel(BaseModel):
    """Top-level schema returned by identify endpoints."""

    matches: list[MatchModel]
    match_source: str | None
    metadata: dict[str, str] | None
    audd_note: str | None
    audd_error: str | None
    fingerprint: str
    duration_seconds: float


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok"}


@app.post(
    "/identify/from-path",
    response_model=IdentifyResponseModel,
    responses={
        401: {"description": "Missing or invalid API token"},
        403: {"description": "Feature not allowed"},
        404: {"description": "Audio file not found"},
        429: {"description": "Quota exceeded"},
    },
)
def identify_from_path(
    payload: IdentifyRequestPayload,
    context: RequestContext = Depends(get_request_context),
    settings: WebSettings = Depends(get_settings),
) -> IdentifyResponseModel:
    """Identify an audio file located on the server filesystem."""
    audio_path = _resolve_audio_path(payload.audio_path, settings)
    request = _build_identify_request(payload, audio_path, settings)

    try:
        response = identify_track(
            request,
            callbacks=CALLBACKS,
            user=context.user,
            access_policy=context.access_policy,
            quota_policy=context.quota_policy,
        )
    except IdentifyServiceError as exc:
        raise HTTPException(status_code=_status_for_service_error(exc), detail=str(exc)) from exc

    return _serialize_response(response)


@app.post(
    "/identify/upload",
    response_model=IdentifyResponseModel,
    responses={
        400: {"description": "Invalid upload"},
        401: {"description": "Missing or invalid API token"},
        403: {"description": "Feature not allowed"},
        413: {"description": "Upload too large"},
        415: {"description": "Unsupported media type"},
    },
)
async def identify_from_upload(
    file: UploadFile = File(...),
    refresh_cache: bool = Form(False),
    metadata_fallback: bool = Form(True),
    prefer_audd: bool = Form(False),
    force_audd_enterprise: bool = Form(False),
    enable_audd: bool | None = Form(None),
    context: RequestContext = Depends(get_request_context),
    settings: WebSettings = Depends(get_settings),
) -> IdentifyResponseModel:
    """Identify an uploaded audio file."""
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Expected audio/* upload",
        )

    temp_path = await _persist_upload(file, settings)
    payload = IdentifyRequestPayload(
        audio_path=str(temp_path),
        refresh_cache=refresh_cache,
        metadata_fallback=metadata_fallback,
        prefer_audd=prefer_audd,
        force_audd_enterprise=force_audd_enterprise,
        enable_audd=enable_audd,
    )

    try:
        request = _build_identify_request(payload, temp_path, settings)
        response = identify_track(
            request,
            callbacks=CALLBACKS,
            user=context.user,
            access_policy=context.access_policy,
            quota_policy=context.quota_policy,
        )
    except IdentifyServiceError as exc:
        raise HTTPException(status_code=_status_for_service_error(exc), detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    return _serialize_response(response)


def _resolve_audio_path(path_value: str, settings: WebSettings) -> Path:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = (settings.base_media_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(settings.base_media_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Path outside media root"
        ) from exc

    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")
    return candidate


def _build_identify_request(
    payload: IdentifyRequestPayload,
    path_value: Path,
    settings: WebSettings,
) -> IdentifyRequest:
    cache_enabled = (
        payload.cache_enabled if payload.cache_enabled is not None else settings.cache_enabled
    )
    cache_ttl = (
        payload.cache_ttl_hours if payload.cache_ttl_hours is not None else settings.cache_ttl_hours
    )
    enable_audd = payload.enable_audd
    if enable_audd is None:
        enable_audd = bool(settings.audd_token)

    audd_config = AudDConfig(
        token=settings.audd_token,
        enabled=enable_audd and bool(settings.audd_token),
        prefer=payload.prefer_audd,
        endpoint_standard=settings.audd_endpoint_standard,
        endpoint_enterprise=settings.audd_endpoint_enterprise,
        mode=AudDMode.AUTO,
        force_enterprise=payload.force_audd_enterprise,
        enterprise_fallback=True,
        params=AudDEnterpriseParams(),
        snippet_offset=None,
        snippet_min_level=None,
    )

    musicbrainz_options = MusicBrainzOptions(
        enabled=settings.musicbrainz_enabled, enrich_missing_only=True
    )
    musicbrainz_settings = build_settings(
        app_name=settings.musicbrainz_app_name,
        app_version=settings.musicbrainz_app_version,
        contact=settings.musicbrainz_contact,
        rate_limit_per_second=1.0,
        timeout_seconds=5.0,
        cache_size=0,
        max_retries=2,
    )

    return IdentifyRequest(
        audio_path=path_value,
        fpcalc_path=None,
        api_key=settings.acoustid_api_key,
        refresh_cache=payload.refresh_cache,
        cache_enabled=cache_enabled,
        cache_ttl_hours=cache_ttl,
        audd=audd_config,
        musicbrainz_options=musicbrainz_options,
        musicbrainz_settings=musicbrainz_settings,
        metadata_fallback=payload.metadata_fallback,
    )


def _serialize_response(response: IdentifyResponse) -> IdentifyResponseModel:
    matches = [_serialize_match(match) for match in response.matches]
    return IdentifyResponseModel(
        matches=matches,
        match_source=response.match_source,
        metadata=response.metadata,
        audd_note=response.audd_note,
        audd_error=response.audd_error,
        fingerprint=response.fingerprint.fingerprint,
        duration_seconds=response.fingerprint.duration_seconds,
    )


def _serialize_match(match: AcoustIDMatch) -> MatchModel:
    releases = [
        ReleaseModel(
            title=release.title,
            release_id=release.release_id,
            date=release.date,
            country=release.country,
        )
        for release in match.releases
    ]
    return MatchModel(
        score=match.score,
        recording_id=match.recording_id,
        title=match.title,
        artist=match.artist,
        release_group_id=match.release_group_id,
        release_group_title=match.release_group_title,
        releases=releases,
    )


@app.get("/whoami")
def whoami(context: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    """Return details about the token (useful for quick diagnostics)."""
    allowed = context.user.attributes.get("allowed_features", [])
    return {
        "user_id": context.user.user_id,
        "display_name": context.user.display_name,
        "roles": list(context.user.roles),
        "allowed_features": [feature.value for feature in allowed],
    }


def _status_for_service_error(exc: IdentifyServiceError) -> int:
    cause = exc.__cause__
    if isinstance(cause, AccessPolicyError):
        return status.HTTP_403_FORBIDDEN
    if isinstance(cause, QuotaPolicyError):
        return status.HTTP_429_TOO_MANY_REQUESTS
    return status.HTTP_400_BAD_REQUEST


async def _persist_upload(upload: UploadFile, settings: WebSettings) -> Path:
    upload_dir = settings.upload_directory
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload.filename or "").suffix
    temp_path = upload_dir / f"{uuid4().hex}{suffix}"

    max_bytes = max(settings.max_upload_mb, 0) * 1024 * 1024
    if max_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Upload exceeds configured size limit",
        )

    written = 0
    chunk_size = 1024 * 64
    with temp_path.open("wb") as buffer:
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                buffer.close()
                temp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Upload exceeds configured size limit",
                )
            buffer.write(chunk)
    await upload.close()

    if written == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    return temp_path

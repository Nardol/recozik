"""FastAPI application exposing Recozik services."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    status,
)
from fastapi.websockets import WebSocketDisconnect
from pydantic import BaseModel, Field
from recozik_services import (
    AudDConfig,
    IdentifyRequest,
    IdentifyResponse,
    IdentifyServiceError,
    identify_track,
)
from recozik_services.cli_support.musicbrainz import MusicBrainzOptions, build_settings
from recozik_services.security import AccessPolicyError, QuotaPolicyError, ServiceUser

from recozik_core.audd import AudDEnterpriseParams, AudDMode
from recozik_core.fingerprint import AcoustIDMatch

from .auth import API_TOKEN_HEADER, RequestContext, get_request_context, resolve_user_from_token
from .auth_store import TokenRecord, get_token_repository
from .config import WebSettings, get_settings
from .jobs import JobRecord, JobStatus, get_job_repository, get_notifier

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


class JobCallbacks(LoggingCallbacks):
    """Callback wrapper that records messages for a job."""

    def __init__(self, job_id: str, repo) -> None:
        """Store repository used to persist callback messages."""
        self.job_id = job_id
        self.repo = repo

    def info(self, message: str) -> None:  # pragma: no cover - logging wrapper
        """Record info-level callback output."""
        super().info(message)
        self.repo.append_message(self.job_id, message)

    def warning(self, message: str) -> None:  # pragma: no cover - logging wrapper
        """Record warning-level callback output."""
        super().warning(message)
        self.repo.append_message(self.job_id, message)

    def error(self, message: str) -> None:  # pragma: no cover - logging wrapper
        """Record error-level callback output."""
        super().error(message)
        self.repo.append_message(self.job_id, message)


def _ensure_admin(context: RequestContext = Depends(get_request_context)) -> None:
    if "admin" not in context.user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


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


class JobSummaryModel(BaseModel):
    """Minimal job information returned after enqueuing."""

    job_id: str
    status: JobStatus


class JobDetailModel(JobSummaryModel):
    """Detailed job payload for polling endpoints."""

    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    messages: list[str]
    result: IdentifyResponseModel | None
    error: str | None


class TokenResponseModel(BaseModel):
    """Serialized token metadata returned by admin APIs."""

    token: str
    user_id: str
    display_name: str
    roles: list[str]
    allowed_features: list[str]
    quota_limits: dict[str, int | None]


class TokenCreateModel(BaseModel):
    """Payload used to create or update tokens."""

    token: str | None = None
    user_id: str
    display_name: str
    roles: list[str] = Field(default_factory=list)
    allowed_features: list[str] = Field(default_factory=list)
    quota_limits: dict[str, int | None] = Field(default_factory=dict)


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
    response_model=JobSummaryModel,
    responses={
        400: {"description": "Invalid upload"},
        401: {"description": "Missing or invalid API token"},
        403: {"description": "Feature not allowed"},
        415: {"description": "Unsupported media type"},
        429: {"description": "Quota exceeded"},
    },
)
async def identify_from_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    refresh_cache: bool = Form(False),
    metadata_fallback: bool = Form(True),
    prefer_audd: bool = Form(False),
    force_audd_enterprise: bool = Form(False),
    enable_audd: bool | None = Form(None),
    context: RequestContext = Depends(get_request_context),
    settings: WebSettings = Depends(get_settings),
) -> JobSummaryModel:
    """Enqueue an identify job for an uploaded file."""
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Expected audio/* upload",
        )

    temp_path = await _persist_upload(file, settings)
    try:
        payload = IdentifyRequestPayload(
            audio_path=str(temp_path),
            refresh_cache=refresh_cache,
            metadata_fallback=metadata_fallback,
            prefer_audd=prefer_audd,
            force_audd_enterprise=force_audd_enterprise,
            enable_audd=enable_audd,
        )
        repo = get_job_repository(settings.jobs_database_url_resolved)
        job = repo.create_job(user_id=context.user.user_id or "anonymous")
        background_tasks.add_task(
            _run_identify_job,
            job.id,
            temp_path,
            payload,
            settings,
            context,
        )
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return JobSummaryModel(job_id=job.id, status=job.status)


def _resolve_audio_path(path_value: str, settings: WebSettings) -> Path:
    if not path_value or not path_value.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing audio path")

    # Normalize to POSIX-style separators and create a relative Path object.
    normalized_path = path_value.strip().replace("\\", "/")
    relative_path = Path(normalized_path)

    # Disallow absolute, rooted, or traversal paths.
    if relative_path.is_absolute() or any(part == ".." for part in relative_path.parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Absolute paths or directory traversal components are not allowed.",
        )

    media_root = settings.base_media_root.resolve()
    candidate_path = (media_root / relative_path).resolve()

    # Ensure the candidate path is strictly contained within media_root.
    media_root_str = str(media_root)
    candidate_path_str = str(candidate_path)
    if not (
        candidate_path_str == media_root_str
        or candidate_path_str.startswith(media_root_str + str(candidate_path.anchor or candidate_path.root or "/"))
        or candidate_path_str.startswith(media_root_str + "/")  # For POSIX systems
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Path outside media root"
        )

    if not candidate_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")
    return candidate_path


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


def _job_to_model(job: JobRecord) -> JobDetailModel:
    result_payload = IdentifyResponseModel.model_validate(job.result) if job.result else None
    return JobDetailModel(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
        messages=list(job.messages),
        result=result_payload,
        error=job.error,
    )


def _job_is_accessible(job: JobRecord, user: ServiceUser) -> bool:
    """Return True when the provided user may read the given job."""
    if user.has_role("admin"):
        return True
    if job.user_id is None:
        return False
    return job.user_id == user.user_id


def _ensure_job_access(job: JobRecord, context: RequestContext) -> None:
    """Raise when the request user is not allowed to read the job."""
    if not _job_is_accessible(job, context.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@app.get("/whoami")
def whoami(context: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    """Return details about the token (useful for quick diagnostics)."""
    allowed = context.user.attributes.get("allowed_features", [])
    return {
        "user_id": context.user.user_id,
        "display_name": context.user.display_name,
        "roles": list(context.user.roles),
        "allowed_features": list(allowed),
    }


def _status_for_service_error(exc: IdentifyServiceError) -> int:
    cause = exc.__cause__
    if isinstance(cause, AccessPolicyError):
        return status.HTTP_403_FORBIDDEN
    if isinstance(cause, QuotaPolicyError):
        return status.HTTP_429_TOO_MANY_REQUESTS
    return status.HTTP_400_BAD_REQUEST


def _run_identify_job(
    job_id: str,
    temp_path: Path,
    payload: IdentifyRequestPayload,
    settings: WebSettings,
    context: RequestContext,
) -> None:
    logger.debug("Job %s started", job_id)
    repo = get_job_repository(settings.jobs_database_url_resolved)
    repo.set_status(job_id, JobStatus.RUNNING)
    callbacks = JobCallbacks(job_id, repo)

    try:
        request = _build_identify_request(payload, temp_path, settings)
        response = identify_track(
            request,
            callbacks=callbacks,
            user=context.user,
            access_policy=context.access_policy,
            quota_policy=context.quota_policy,
        )
    except IdentifyServiceError as exc:
        repo.append_message(job_id, f"Error: {exc}")
        repo.set_status(job_id, JobStatus.FAILED, error=str(exc))
    except Exception as exc:  # pragma: no cover - defensive safety net
        logger.exception("Unexpected error while processing job %s", job_id)
        repo.append_message(job_id, f"Unexpected error: {exc}")
        repo.set_status(job_id, JobStatus.FAILED, error="Unexpected error during processing")
    else:
        serialized = _serialize_response(response).model_dump()
        repo.set_status(job_id, JobStatus.COMPLETED, result=serialized)
    finally:
        temp_path.unlink(missing_ok=True)
        logger.debug("Job %s finished", job_id)


async def _persist_upload(upload: UploadFile, settings: WebSettings) -> Path:
    upload_dir = settings.upload_directory
    upload_dir.mkdir(parents=True, exist_ok=True)

    max_bytes = max(settings.max_upload_mb, 0) * 1024 * 1024
    if max_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File uploads are disabled (max_upload_mb=0)",
        )

    # Sanitize the filename to prevent directory traversal or invalid characters.
    filename = Path(upload.filename or "").name
    suffix = Path(filename).suffix
    temp_path = upload_dir / f"{uuid4().hex}{suffix}"

    written = 0
    chunk_size = 1024 * 64
    try:
        with temp_path.open("wb") as buffer:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Upload exceeds configured size limit",
                    )
                buffer.write(chunk)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if written == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload")

    return temp_path


@app.get("/jobs/{job_id}", response_model=JobDetailModel)
def get_job_detail(
    job_id: str,
    context: RequestContext = Depends(get_request_context),
    settings: WebSettings = Depends(get_settings),
) -> JobDetailModel:
    """Return the persisted state for a job."""
    repo = get_job_repository(settings.jobs_database_url_resolved)
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _ensure_job_access(job, context)
    return _job_to_model(job)


@app.websocket("/ws/jobs/{job_id}")
async def job_updates(websocket: WebSocket, job_id: str) -> None:
    """Stream job updates over WebSocket."""
    logger.debug("WebSocket connect for %s", job_id)
    token = websocket.headers.get(API_TOKEN_HEADER) or websocket.query_params.get("token")
    settings = get_settings()

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user = resolve_user_from_token(token, settings)
        repo = get_job_repository(settings.jobs_database_url_resolved)
        job = repo.get(job_id)

        if job is None or not _job_is_accessible(job, user):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        logger.debug("WebSocket snapshot for %s", job_id)
        await websocket.send_json({"type": "snapshot", "job": repo.as_dict(job)})
        notifier = get_notifier()
        queue = notifier.subscribe(job_id)
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        finally:
            notifier.unsubscribe(job_id, queue)
    except WebSocketDisconnect:
        logger.debug("WebSocket for job %s disconnected.", job_id)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("WebSocket error for job %s", job_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


@app.get("/admin/tokens", response_model=list[TokenResponseModel])
def list_tokens(
    settings: WebSettings = Depends(get_settings),
    _: None = Depends(_ensure_admin),
) -> list[TokenResponseModel]:
    """Return all stored tokens (admin only)."""
    repo = get_token_repository(settings.auth_database_url_resolved)
    records = repo.list_tokens()
    return [
        TokenResponseModel(
            token=record.token,
            user_id=record.user_id,
            display_name=record.display_name,
            roles=record.roles,
            allowed_features=record.allowed_features,
            quota_limits=record.quota_limits,
        )
        for record in records
    ]


@app.post("/admin/tokens", response_model=TokenResponseModel)
def create_token(
    payload: TokenCreateModel,
    settings: WebSettings = Depends(get_settings),
    _: None = Depends(_ensure_admin),
) -> TokenResponseModel:
    """Create or update API tokens (admin only)."""
    repo = get_token_repository(settings.auth_database_url_resolved)
    token_value = payload.token or uuid4().hex
    record = TokenRecord(
        token=token_value,
        user_id=payload.user_id,
        display_name=payload.display_name,
        roles=payload.roles,
        allowed_features=payload.allowed_features,
        quota_limits=payload.quota_limits,
    )
    repo.upsert(record)
    return TokenResponseModel(
        token=record.token,
        user_id=record.user_id,
        display_name=record.display_name,
        roles=record.roles,
        allowed_features=record.allowed_features,
        quota_limits=record.quota_limits,
    )

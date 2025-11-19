"""Integration tests for the Recozik FastAPI backend."""

from __future__ import annotations

import os
import time
from importlib import import_module, reload
from pathlib import Path

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from recozik_services.identify import IdentifyResponse, IdentifyServiceError
from recozik_services.security import AccessPolicyError, ServiceFeature
from recozik_web.auth_store import TokenRecord, get_token_repository
from recozik_web.config import WebSettings
from recozik_web.jobs import JobStatus
from recozik_web.token_utils import TOKEN_HASH_PREFIX, hash_token_for_storage
from starlette.websockets import WebSocketDisconnect

from recozik_core.fingerprint import AcoustIDMatch, FingerprintResult, ReleaseInfo

API_TOKEN = "test-admin"  # noqa: S105 - fixed token for test fixtures


def _override_settings(tmp_path: Path) -> WebSettings:
    """Return deterministic settings tied to the provided tmp_path."""
    return WebSettings(
        admin_token=API_TOKEN,
        readonly_token=None,
        acoustid_api_key="api-key",
        audd_token=None,
        base_media_root=tmp_path,
        cache_enabled=False,
        musicbrainz_enabled=False,
    )


def _bootstrap_app(monkeypatch, tmp_path: Path, settings: WebSettings):
    """Reload FastAPI modules so they pick up test settings.

    Warning: This reload-based bootstrap is tightly coupled to module init order.
    Adjustments to recozik_web startup code may require updating this helper.
    """

    def _get_settings() -> WebSettings:
        return settings

    monkeypatch.setenv("RECOZIK_WEB_ADMIN_TOKEN", settings.admin_token)
    monkeypatch.setenv("RECOZIK_WEB_ACOUSTID_API_KEY", settings.acoustid_api_key)
    monkeypatch.setenv("RECOZIK_WEB_BASE_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setenv("RECOZIK_WEB_MUSICBRAINZ_ENABLED", str(settings.musicbrainz_enabled).lower())
    monkeypatch.setenv("RECOZIK_WEB_MAX_UPLOAD_MB", str(settings.max_upload_mb))
    monkeypatch.setenv("RECOZIK_WEB_UPLOAD_SUBDIR", settings.upload_subdir)

    config_module = reload(import_module("recozik_web.config"))
    config_module.get_settings.cache_clear()
    auth_module = reload(import_module("recozik_web.auth"))
    app_module = reload(import_module("recozik_web.app"))

    app_module.app.dependency_overrides[config_module.get_settings] = _get_settings
    app_module.app.dependency_overrides[auth_module.get_settings] = _get_settings
    app_module.get_settings = _get_settings

    client = TestClient(app_module.app)
    return client, tmp_path, app_module, settings


@pytest.fixture(name="web_app")
def web_app_fixture(monkeypatch, tmp_path: Path):
    """Yield a configured TestClient plus helper context."""
    settings = _override_settings(tmp_path)
    return _bootstrap_app(monkeypatch, tmp_path, settings)


def _create_token(
    client: TestClient,
    token_value: str,
    user_id: str,
    *,
    allowed_features: list[str] | None = None,
    quota_limits: dict[str, int | None] | None = None,
) -> str:
    """Create an API token through the admin endpoint for test purposes."""
    payload = {
        "token": token_value,
        "user_id": user_id,
        "display_name": user_id,
        "roles": [],
        "allowed_features": allowed_features if allowed_features is not None else ["identify"],
        "quota_limits": quota_limits or {},
    }
    resp = client.post("/admin/tokens", json=payload, headers={"X-API-Token": API_TOKEN})
    assert resp.status_code == 200, resp.text
    return token_value


def test_health_endpoint(web_app) -> None:
    """Check the health endpoint returns a success payload."""
    client, _, _, _ = web_app
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers_enabled(web_app) -> None:
    """Security middleware should add hardened headers."""
    client, _, _, _ = web_app
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-frame-options"] == "DENY"
    csp = response.headers.get("content-security-policy", "")
    assert "default-src" in csp


def test_identify_requires_token(web_app) -> None:
    """Missing auth header should cause a 422 error at validation time."""
    client, media_root, _, _ = web_app
    (media_root / "clip.flac").write_bytes(b"data")
    response = client.post("/identify/from-path", json={"audio_path": "clip.flac"})
    assert response.status_code == 422  # missing header


def test_identify_from_path_invokes_service(monkeypatch, web_app) -> None:
    """Path-based identify endpoint must call the shared service."""
    client, media_root, app_module, _ = web_app
    file_path = media_root / "clip.wav"
    file_path.write_bytes(b"audio")

    fingerprint = FingerprintResult(fingerprint="abc", duration_seconds=123.0)
    release = ReleaseInfo(title="Album", release_id="rel", date=None, country=None)
    match = AcoustIDMatch(
        score=0.9,
        recording_id="rec",
        title="Track",
        artist="Artist",
        release_group_id=None,
        release_group_title=None,
        releases=[release],
    )
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="acoustid",
        metadata={"artist": "Artist"},
        audd_note=None,
        audd_error=None,
    )

    captured_paths: list[Path] = []

    def fake_identify(request, **_kwargs):
        captured_paths.append(request.audio_path)
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", fake_identify)

    response = client.post(
        "/identify/from-path",
        json={"audio_path": "clip.wav"},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["match_source"] == "acoustid"
    assert data["matches"][0]["title"] == "Track"
    assert captured_paths == [file_path]


def test_identify_rejects_traversal(web_app) -> None:
    """The API should reject attempts to escape the media root."""
    client, _, _, _ = web_app
    response = client.post(
        "/identify/from-path",
        json={"audio_path": "../secret.flac"},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 400
    assert "traversal" in response.json()["detail"].lower()


def test_identify_rejects_absolute_path(web_app) -> None:
    """Absolute paths must be denied to avoid leaking server files."""
    client, media_root, _, _ = web_app
    absolute_path = (media_root / "clip.wav").resolve()
    response = client.post(
        "/identify/from-path",
        json={"audio_path": str(absolute_path)},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 400
    assert "absolute paths" in response.json()["detail"].lower()


def test_identify_rejects_symlink_escape(web_app, tmp_path) -> None:
    """Symlinks pointing outside the media root must be rejected."""
    if not hasattr(os, "symlink"):
        pytest.skip("symlink handling not supported on this platform")

    client, media_root, _, _ = web_app
    # Create a secret file outside the media root.
    secret_target = tmp_path.parent / f"{tmp_path.name}-secret.flac"
    secret_target.write_bytes(b"secret-data")

    symlink_path = media_root / "leak.flac"
    try:
        symlink_path.symlink_to(secret_target)
    except OSError as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlink creation not permitted: {exc}")

    response = client.post(
        "/identify/from-path",
        json={"audio_path": symlink_path.name},
        headers={"X-API-Token": API_TOKEN},
    )
    assert response.status_code == 400
    assert "symbolic" in response.json()["detail"].lower()


def test_whoami_returns_context(web_app) -> None:
    """Token metadata should be visible through /whoami."""
    client, _, _, _ = web_app
    response = client.get("/whoami", headers={"X-API-Token": API_TOKEN})
    body = response.json()
    assert response.status_code == 200, body
    assert body["user_id"] == "admin"
    assert "identify" in {feature.lower() for feature in body["allowed_features"]}


def test_identify_upload_invokes_service(monkeypatch, web_app) -> None:
    """Upload endpoint should stream file to disk and trigger identify."""
    client, media_root, app_module, settings = web_app

    fingerprint = FingerprintResult(fingerprint="abc", duration_seconds=123.0)
    match = AcoustIDMatch(
        score=0.9,
        recording_id="rec",
        title="Track",
        artist="Artist",
        release_group_id=None,
        release_group_title=None,
        releases=[],
    )
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="audd",
        metadata=None,
        audd_note=None,
        audd_error=None,
    )

    def fake_identify(_request, **_kwargs):
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", fake_identify)

    response = client.post(
        "/identify/upload",
        files={"file": ("clip.wav", b"audio-bytes", "audio/wav")},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    job_id = payload["job_id"]

    for _ in range(60):
        job_response = client.get(f"/jobs/{job_id}", headers={"X-API-Token": API_TOKEN})
        job_data = job_response.json()
        if job_data["status"] == "completed":
            break
        time.sleep(0.05)
    else:
        pytest.fail("identify job did not complete")

    assert job_data["result"]["match_source"] == "audd"

    upload_dir = media_root / settings.upload_subdir
    assert not any(upload_dir.glob("*"))


def test_identify_upload_rejects_large_file(monkeypatch, tmp_path: Path) -> None:
    """Uploading beyond the configured max size should return 413."""
    settings = _override_settings(tmp_path)
    settings.max_upload_mb = 0
    client, _, _, _ = _bootstrap_app(monkeypatch, tmp_path, settings)

    response = client.post(
        "/identify/upload",
        files={"file": ("clip.wav", b"x" * 1024, "audio/wav")},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 413


def test_job_websocket_stream(monkeypatch, web_app) -> None:
    """WebSocket endpoint should emit snapshot and result events."""
    client, _, app_module, _ = web_app

    fingerprint = FingerprintResult(fingerprint="abc", duration_seconds=5.0)
    match = AcoustIDMatch(
        score=0.9,
        recording_id="rec",
        title="Track",
        artist="Artist",
        release_group_id=None,
        release_group_title=None,
        releases=[],
    )
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="acoustid",
        metadata=None,
        audd_note=None,
        audd_error=None,
    )

    def slow_identify(*_args, **_kwargs):
        time.sleep(0.05)
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", slow_identify)

    resp = client.post(
        "/identify/upload",
        files={"file": ("clip.wav", b"audio-bytes", "audio/wav")},
        headers={"X-API-Token": API_TOKEN},
    )
    job_id = resp.json()["job_id"]

    repo = app_module.get_job_repository(app_module.get_settings().jobs_database_url_resolved)
    job = repo.get(job_id)
    assert job.user_id == "admin"

    time.sleep(0.05)

    with client.websocket_connect(
        f"/ws/jobs/{job_id}?token={API_TOKEN}",
        headers={"X-API-Token": API_TOKEN},
    ) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        if snapshot["job"]["status"] == "completed":
            events = []
        else:
            events = []
            for _ in range(5):
                event = websocket.receive_json()
                events.append(event)
                if event.get("type") == "result":
                    break
    assert snapshot["job"]["status"] == "completed" or any(
        evt.get("type") == "result" for evt in events
    )


def test_job_detail_rejects_other_user(monkeypatch, web_app) -> None:
    """Job polling endpoint must not leak other users' jobs."""
    client, _, app_module, _ = web_app
    other_token = _create_token(client, "other-token", "other")

    fingerprint = FingerprintResult(fingerprint="abc", duration_seconds=5.0)
    match = AcoustIDMatch(
        score=0.9, recording_id="rec", title="Track", artist="Artist", releases=[]
    )
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="acoustid",
        metadata=None,
        audd_note=None,
        audd_error=None,
    )

    def _guarded_identify(*_args, **kwargs):
        access_policy = kwargs.get("access_policy")
        user = kwargs.get("user")
        if access_policy and user:
            try:
                access_policy.ensure_feature(
                    user,
                    ServiceFeature.IDENTIFY,
                    context=kwargs,
                )
            except AccessPolicyError as exc:
                raise IdentifyServiceError(str(exc)) from exc
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", _guarded_identify)

    resp = client.post(
        "/identify/upload",
        files={"file": ("clip.wav", b"audio-bytes", "audio/wav")},
        headers={"X-API-Token": API_TOKEN},
    )
    job_id = resp.json()["job_id"]

    for _ in range(60):
        job_response = client.get(f"/jobs/{job_id}", headers={"X-API-Token": API_TOKEN})
        job_data = job_response.json()
        if job_data["status"] == "completed":
            break
        time.sleep(0.05)
    else:  # pragma: no cover - defensive timeout
        pytest.fail("job did not complete")

    forbidden = client.get(f"/jobs/{job_id}", headers={"X-API-Token": other_token})
    assert forbidden.status_code == 403


def test_job_websocket_rejects_other_user(monkeypatch, web_app) -> None:
    """WebSocket streaming should enforce job ownership."""
    client, _, app_module, _ = web_app
    other_token = _create_token(client, "ws-other-token", "ws-other")

    fingerprint = FingerprintResult(fingerprint="abc", duration_seconds=5.0)
    match = AcoustIDMatch(
        score=0.9, recording_id="rec", title="Track", artist="Artist", releases=[]
    )
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="acoustid",
        metadata=None,
        audd_note=None,
        audd_error=None,
    )

    def _guarded_identify(*_args, **kwargs):
        access_policy = kwargs.get("access_policy")
        user = kwargs.get("user")
        if access_policy and user:
            try:
                access_policy.ensure_feature(user, ServiceFeature.IDENTIFY, context=kwargs)
            except AccessPolicyError as exc:
                raise IdentifyServiceError(str(exc)) from exc
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", _guarded_identify)

    resp = client.post(
        "/identify/upload",
        files={"file": ("clip.wav", b"audio-bytes", "audio/wav")},
        headers={"X-API-Token": API_TOKEN},
    )
    job_id = resp.json()["job_id"]

    time.sleep(0.05)

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            f"/ws/jobs/{job_id}?token={other_token}",
            headers={"X-API-Token": other_token},
        ) as websocket:
            websocket.receive_json()
    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION


def test_list_jobs_returns_only_current_user(web_app) -> None:
    """GET /jobs should scope results to the current token."""
    client, _, app_module, settings = web_app
    worker_token = _create_token(client, "worker-token", "worker")
    repo = app_module.get_job_repository(settings.jobs_database_url_resolved)

    worker_jobs = [
        repo.create_job(user_id="worker"),
        repo.create_job(user_id="worker"),
        repo.create_job(user_id="worker"),
    ]
    for job in worker_jobs:
        repo.set_status(job.id, JobStatus.COMPLETED)
    repo.create_job(user_id="other-user")

    resp = client.get("/jobs", headers={"X-API-Token": worker_token})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert [entry["job_id"] for entry in payload] == [job.id for job in reversed(worker_jobs)]


def test_admin_can_list_jobs_for_any_user(web_app) -> None:
    """Admins may filter jobs by user_id."""
    client, _, app_module, settings = web_app
    repo = app_module.get_job_repository(settings.jobs_database_url_resolved)
    job = repo.create_job(user_id="inspect-user")
    repo.set_status(job.id, JobStatus.RUNNING)

    resp = client.get(
        "/jobs",
        params={"user_id": "inspect-user"},
        headers={"X-API-Token": API_TOKEN},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["job_id"] == job.id


def test_admin_tokens_hide_secret(web_app) -> None:
    """Admin token listing must never leak stored token hashes."""
    client, _, _, settings = web_app
    token_value = "custom-secret-token"  # noqa: S105 - deterministic test fixture
    resp = client.post(
        "/admin/tokens",
        json={
            "token": token_value,
            "user_id": "auditor",
            "display_name": "auditor",
            "roles": [],
            "allowed_features": ["identify"],
            "quota_limits": {},
        },
        headers={"X-API-Token": API_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"] == token_value
    assert body["token_hint"].endswith(token_value[-4:])

    listing = client.get("/admin/tokens", headers={"X-API-Token": API_TOKEN})
    assert listing.status_code == 200
    entries = listing.json()
    stored = next(entry for entry in entries if entry["user_id"] == "auditor")
    assert stored["token"] is None
    assert stored["token_hint"].endswith(token_value[-4:])

    repo = get_token_repository(settings.auth_database_url_resolved)
    stored_record = next(record for record in repo.list_tokens() if record.user_id == "auditor")
    assert stored_record.token.startswith(TOKEN_HASH_PREFIX)


def test_admin_seed_token_gains_audd_feature(monkeypatch, tmp_path: Path) -> None:
    """Existing admin tokens should pick up AudD access when enabled."""
    settings = _override_settings(tmp_path)
    settings.audd_token = "audd-admin-token"  # noqa: S105 - test fixture secret

    repo = get_token_repository(settings.auth_database_url_resolved)
    repo.upsert(
        TokenRecord(
            token=hash_token_for_storage(settings.admin_token),
            user_id="admin",
            display_name="Administrator",
            roles=["admin"],
            allowed_features=[ServiceFeature.IDENTIFY.value],
            quota_limits={},
        )
    )

    client, _, _, _ = _bootstrap_app(monkeypatch, tmp_path, settings)
    resp = client.get("/whoami", headers={"X-API-Token": API_TOKEN})
    assert resp.status_code == 200, resp.text

    stored_record = next(record for record in repo.list_tokens() if record.user_id == "admin")
    assert ServiceFeature.AUDD.value in stored_record.allowed_features


def test_restricted_token_denies_missing_feature(monkeypatch, web_app) -> None:
    """Tokens without the identify feature must not access identify endpoints."""
    client, media_root, app_module, _ = web_app
    limited_token = _create_token(
        client,
        "rename-only-token",
        "rename-only",
        allowed_features=["rename"],
    )

    target = media_root / "clip.wav"
    target.write_bytes(b"audio")

    whoami = client.get("/whoami", headers={"X-API-Token": limited_token})
    assert whoami.status_code == 200
    assert whoami.json()["allowed_features"] == ["rename"]

    fingerprint = FingerprintResult(fingerprint="abc", duration_seconds=5.0)
    match = AcoustIDMatch(
        score=0.9,
        recording_id="rec",
        title="Track",
        artist="Artist",
        releases=[],
    )
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="acoustid",
        metadata=None,
        audd_note=None,
        audd_error=None,
    )

    def _guarded_identify(*_args, **kwargs):
        access_policy = kwargs.get("access_policy")
        user = kwargs.get("user")
        if access_policy and user:
            try:
                access_policy.ensure_feature(
                    user,
                    ServiceFeature.IDENTIFY,
                    context=kwargs,
                )
            except AccessPolicyError as exc:
                raise IdentifyServiceError(str(exc)) from exc
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", _guarded_identify)

    response = client.post(
        "/identify/from-path",
        json={"audio_path": target.name},
        headers={"X-API-Token": limited_token},
    )

    assert response.status_code == 403
    assert "identify" in response.json()["detail"].lower()


def test_admin_can_manage_tokens(monkeypatch, web_app) -> None:
    """Admin endpoints should create tokens persisted in SQLite."""
    client, media_root, app_module, _ = web_app

    new_token = "custom-token"  # noqa: S105 - test fixture token
    payload = {
        "token": new_token,
        "user_id": "tester",
        "display_name": "Tester",
        "roles": ["operator"],
        "allowed_features": ["identify"],
        "quota_limits": {"acoustid_lookup": 1},
    }

    resp = client.post(
        "/admin/tokens",
        json=payload,
        headers={"X-API-Token": API_TOKEN},
    )
    assert resp.status_code == 200

    fingerprint = FingerprintResult(fingerprint="tok", duration_seconds=10.0)
    match = AcoustIDMatch(score=0.9, recording_id="tok", title="T", artist="A", releases=[])
    fake_response = IdentifyResponse(
        fingerprint=fingerprint,
        matches=[match],
        match_source="acoustid",
        metadata=None,
        audd_note=None,
        audd_error=None,
    )

    monkeypatch.setattr(
        app_module,
        "identify_track",
        lambda *_args, **_kwargs: fake_response,
    )
    media_root.joinpath("clip.wav").write_bytes(b"audio")

    resp_identify = client.post(
        "/identify/from-path",
        json={"audio_path": "clip.wav"},
        headers={"X-API-Token": new_token},
    )
    assert resp_identify.status_code == 200


def test_non_admin_cannot_manage_tokens(monkeypatch, tmp_path: Path) -> None:
    """Readonly tokens should be forbidden from admin APIs."""
    settings = _override_settings(tmp_path)
    settings.admin_token = "admin"  # noqa: S105 - test setup
    settings.readonly_token = "readonly"  # noqa: S105 - test setup
    client, _, _, _ = _bootstrap_app(monkeypatch, tmp_path, settings)

    resp = client.get(
        "/admin/tokens",
        headers={"X-API-Token": "readonly"},
    )
    assert resp.status_code == 403

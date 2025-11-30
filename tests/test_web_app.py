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
        admin_password="DevPassword1!",  # noqa: S106 - test fixture password
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

    rate_limit_module = reload(import_module("recozik_web.rate_limit"))
    # Reset rate limiters to avoid cross-test leakage.
    rate_limit_module._rate_limiter = None
    rate_limit_module._auth_rate_limiter = None

    config_module = reload(import_module("recozik_web.config"))
    config_module.get_settings.cache_clear()
    auth_module = reload(import_module("recozik_web.auth"))
    auth_routes_module = reload(import_module("recozik_web.auth_routes"))
    app_module = reload(import_module("recozik_web.app"))

    app_module.app.dependency_overrides[config_module.get_settings] = _get_settings
    app_module.app.dependency_overrides[auth_module.get_settings] = _get_settings
    app_module.app.dependency_overrides[auth_routes_module.get_settings] = _get_settings
    app_module.get_settings = _get_settings
    auth_routes_module.get_settings = _get_settings

    # Seed admin and readonly users before creating test client
    auth_module.seed_users_on_startup(settings)

    client = TestClient(app_module.app)
    return client, tmp_path, app_module, settings


@pytest.fixture(name="web_app")
def web_app_fixture(monkeypatch, tmp_path: Path):
    """Yield a configured TestClient plus helper context."""
    settings = _override_settings(tmp_path)
    return _bootstrap_app(monkeypatch, tmp_path, settings)


def _create_user(
    client: TestClient,
    username: str,
    email: str | None = None,
    password: str = "TestPassword1!",  # noqa: S107
    *,
    roles: list[str] | None = None,
    allowed_features: list[str] | None = None,
    quota_limits: dict[str, int | None] | None = None,
) -> int:
    """Create a user directly in the database for test purposes."""
    from recozik_web.auth_models import User, get_auth_store
    from recozik_web.auth_service import hash_password
    from recozik_web.config import get_settings

    settings = get_settings()
    store = get_auth_store(settings.auth_database_url_resolved)

    user = User(
        username=username,
        email=email or f"{username}@example.com",
        display_name=username.capitalize(),
        password_hash=hash_password(password),
        roles=roles or [],
        allowed_features=allowed_features or [],
        quota_limits=quota_limits or {},
    )
    created = store.create_user(user)
    assert created.id is not None, "User ID should be set after creation"
    return created.id


def _create_token(
    client: TestClient,
    token_value: str,
    user_id: int | str,
    *,
    allowed_features: list[str] | None = None,
    quota_limits: dict[str, int | None] | None = None,
) -> str:
    """Create an API token through the admin endpoint for test purposes.

    If user_id is a string, creates a user with that username first.
    """
    if isinstance(user_id, str):
        # Legacy compatibility: create a user with this username
        user_id = _create_user(
            client,
            username=user_id,
            allowed_features=allowed_features,
            quota_limits=quota_limits,
        )

    payload = {
        "token": token_value,
        "user_id": user_id,
        "display_name": f"Token for user {user_id}",
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


def _ensure_admin(settings: WebSettings):
    from recozik_web.auth_models import User, get_auth_store
    from recozik_web.auth_service import hash_password, verify_password

    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user(settings.admin_username)
    if not user:
        user = User(
            username=settings.admin_username,
            email=f"{settings.admin_username}@localhost",
            display_name="Test Administrator",
            password_hash=hash_password(settings.admin_password),
            roles=["admin"],
            allowed_features=[],
            quota_limits={},
        )
        store.create_user(user)
    else:
        # ensure password matches configured one for this test run
        user.password_hash = hash_password(settings.admin_password)
        store.upsert_user(user)
    assert verify_password(settings.admin_password, user.password_hash)


def _login_admin(client: TestClient, settings: WebSettings):
    _ensure_admin(settings)
    resp = client.post(
        "/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert resp.status_code == 200, resp.text
    return resp


def test_auth_refresh_requires_csrf(web_app) -> None:
    """Refresh must reject when CSRF header is missing."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    cookies = client.cookies

    resp_missing = client.post("/auth/refresh")
    assert resp_missing.status_code == status.HTTP_403_FORBIDDEN

    csrf = cookies.get("recozik_csrf")
    resp_ok = client.post(
        "/auth/refresh",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_ok.status_code == status.HTTP_200_OK


def test_register_requires_csrf(web_app) -> None:
    """Admin user creation must enforce CSRF."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    cookies = client.cookies
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "display_name": "New User",
        "password": "Str0ngPassw0rd!",
        "roles": ["user"],
        "allowed_features": [],
        "quota_limits": {},
    }

    resp_missing = client.post("/auth/register", json=payload)
    assert resp_missing.status_code == status.HTTP_403_FORBIDDEN

    csrf = cookies.get("recozik_csrf")
    resp_ok = client.post(
        "/auth/register",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_ok.status_code == status.HTTP_200_OK


def test_change_password_requires_csrf(web_app) -> None:
    """Password change must enforce CSRF."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    cookies = client.cookies
    payload = {"old_password": "DevPassword1!", "new_password": "Str0ngPassw0rd!"}

    resp_missing = client.post("/auth/change-password", json=payload)
    assert resp_missing.status_code == status.HTTP_403_FORBIDDEN

    csrf = cookies.get("recozik_csrf")
    resp_ok = client.post(
        "/auth/change-password",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_ok.status_code == status.HTTP_200_OK


def test_login_rate_limited(web_app) -> None:
    """Repeated failed logins should be rate limited."""
    client, _, _, settings = web_app
    _ensure_admin(settings)
    headers = {"X-Forwarded-For": "203.0.113.1"}
    for _ in range(5):
        resp = client.post(
            "/auth/login",
            json={"username": settings.admin_username, "password": "wrong"},
            headers=headers,
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp_limit = client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong"},
        headers=headers,
    )
    assert resp_limit.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_identify_requires_token(web_app) -> None:
    """Missing auth header should return 401 when auth is required."""
    client, media_root, _, _ = web_app
    (media_root / "clip.flac").write_bytes(b"data")
    response = client.post("/identify/from-path", json={"audio_path": "clip.flac"})
    # With session-based auth, missing credentials now yields 401
    assert response.status_code == 401


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
    worker_user_id = _create_user(client, username="worker")
    worker_token = _create_token(client, "worker-token", worker_user_id)
    repo = app_module.get_job_repository(settings.jobs_database_url_resolved)

    # Jobs are keyed by username, not numeric user ID
    worker_jobs = [
        repo.create_job(user_id="worker"),
        repo.create_job(user_id="worker"),
        repo.create_job(user_id="worker"),
    ]
    for job in worker_jobs:
        repo.set_status(job.id, JobStatus.COMPLETED)
    _create_user(client, username="other-user")
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
    auditor_user_id = _create_user(client, username="auditor")
    token_value = "custom-secret-token"  # noqa: S105 - deterministic test fixture
    resp = client.post(
        "/admin/tokens",
        json={
            "token": token_value,
            "user_id": auditor_user_id,
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
    stored = next(entry for entry in entries if entry["user_id"] == auditor_user_id)
    assert stored["token"] is None
    assert stored["token_hint"].endswith(token_value[-4:])

    repo = get_token_repository(settings.auth_database_url_resolved)
    stored_record = next(
        record for record in repo.list_tokens() if record.user_id == auditor_user_id
    )
    assert stored_record.token.startswith(TOKEN_HASH_PREFIX)


def test_admin_seed_token_gains_audd_feature(monkeypatch, tmp_path: Path) -> None:
    """Existing admin tokens should pick up AudD access when enabled."""
    from recozik_web.auth_models import User, get_auth_store
    from recozik_web.auth_service import hash_password

    settings = _override_settings(tmp_path)
    settings.audd_token = "audd-admin-token"  # noqa: S105 - test fixture secret

    # Create admin user first
    auth_store = get_auth_store(settings.auth_database_url_resolved)
    admin_user = User(
        username=settings.admin_username,
        email=f"{settings.admin_username}@localhost",
        display_name="Administrator",
        password_hash=hash_password(settings.admin_password),
        roles=["admin"],
        allowed_features=[ServiceFeature.IDENTIFY.value],
        quota_limits={},
    )
    created_user = auth_store.create_user(admin_user)
    assert created_user.id is not None

    # Create token with initial features (no AudD)
    repo = get_token_repository(settings.auth_database_url_resolved)
    repo.upsert(
        TokenRecord(
            token=hash_token_for_storage(settings.admin_token),
            user_id=created_user.id,
            display_name="Administrator",
            roles=["admin"],
            allowed_features=[ServiceFeature.IDENTIFY.value],
            quota_limits={},
        )
    )

    client, _, _, _ = _bootstrap_app(monkeypatch, tmp_path, settings)
    resp = client.get("/whoami", headers={"X-API-Token": API_TOKEN})
    assert resp.status_code == 200, resp.text

    stored_record = next(
        record for record in repo.list_tokens() if record.user_id == created_user.id
    )
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

    # Create a user first
    user_id = _create_user(client, "tester")

    new_token = "custom-token"  # noqa: S105 - test fixture token
    payload = {
        "token": new_token,
        "user_id": user_id,
        "display_name": "Tester CLI Token",
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


# ============================================================================
# User Management Tests
# ============================================================================


def test_admin_can_list_users(web_app) -> None:
    """Admin should be able to list all users."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)

    # Create a couple of test users
    _create_user(client, username="alice", email="alice@example.com")
    _create_user(client, username="bob", email="bob@example.com")

    resp = client.get("/admin/users")
    assert resp.status_code == 200

    users = resp.json()
    assert isinstance(users, list)
    assert len(users) >= 3  # admin + alice + bob

    usernames = [u["username"] for u in users]
    assert "alice" in usernames
    assert "bob" in usernames


def test_admin_can_create_user_via_register(web_app) -> None:
    """Admin can create users via POST /auth/register."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    payload = {
        "username": "charlie",
        "email": "charlie@example.com",
        "display_name": "Charlie Test",
        "password": "SecurePass123!",
        "roles": ["operator"],
        "allowed_features": ["identify"],
        "quota_limits": {"acoustid_lookup": 100},
    }

    resp = client.post(
        "/auth/register",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    # Verify user was created
    users_resp = client.get("/admin/users")
    users = users_resp.json()
    charlie = next((u for u in users if u["username"] == "charlie"), None)
    assert charlie is not None
    assert charlie["email"] == "charlie@example.com"
    assert charlie["display_name"] == "Charlie Test"
    assert "operator" in charlie["roles"]


def test_register_requires_strong_password(web_app) -> None:
    """User creation should enforce password strength requirements."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    # Test a few weak passwords (limited to avoid rate limiting)
    weak_passwords = [
        ("short", "Too short"),
        ("nouppercase123!", "No uppercase"),
        ("NoDigits!", "No digits"),
    ]

    for weak_pass, reason in weak_passwords:
        payload = {
            "username": "test_user",
            "email": "test@example.com",
            "password": weak_pass,
            "roles": [],
            "allowed_features": [],
            "quota_limits": {},
        }
        resp = client.post(
            "/auth/register",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 400, f"Weak password '{weak_pass}' ({reason}) should be rejected"


def test_admin_can_get_user_details(web_app) -> None:
    """Admin can retrieve individual user details."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)

    user_id = _create_user(client, username="david", email="david@example.com")

    resp = client.get(f"/admin/users/{user_id}")
    assert resp.status_code == 200

    user = resp.json()
    assert user["id"] == user_id
    assert user["username"] == "david"
    assert user["email"] == "david@example.com"
    assert "created_at" in user


def test_admin_can_update_user(web_app) -> None:
    """Admin can update user details."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    user_id = _create_user(
        client,
        username="eve",
        email="eve@example.com",
        roles=["readonly"],
    )

    update_payload = {
        "email": "eve.updated@example.com",
        "display_name": "Eve Updated",
        "is_active": True,
        "roles": ["operator", "readonly"],
        "allowed_features": ["identify", "rename"],
        "quota_limits": {"acoustid_lookup": 500},
    }

    resp = client.put(
        f"/admin/users/{user_id}",
        json=update_payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    updated = resp.json()
    assert updated["email"] == "eve.updated@example.com"
    assert updated["display_name"] == "Eve Updated"
    assert set(updated["roles"]) == {"operator", "readonly"}
    assert "identify" in updated["allowed_features"]
    assert "rename" in updated["allowed_features"]


def test_admin_can_deactivate_user(web_app) -> None:
    """Admin can deactivate users via is_active flag."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    user_id = _create_user(client, username="frank", email="frank@example.com")

    # Deactivate user
    resp = client.put(
        f"/admin/users/{user_id}",
        json={
            "is_active": False,
            "roles": [],
            "allowed_features": [],
            "quota_limits": {},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_admin_can_delete_user(web_app) -> None:
    """Admin can delete users."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    user_id = _create_user(client, username="grace", email="grace@example.com")

    resp = client.delete(
        f"/admin/users/{user_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    # Verify user is gone
    get_resp = client.get(f"/admin/users/{user_id}")
    assert get_resp.status_code == 404


def test_admin_can_reset_user_password(web_app) -> None:
    """Admin can reset user passwords."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    user_id = _create_user(
        client,
        username="henry",
        email="henry@example.com",
        password="OldPassword123!",  # noqa: S106
    )

    new_password = "NewSecurePass456!"  # noqa: S105
    resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": new_password},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200


def test_password_reset_requires_strong_password(web_app) -> None:
    """Password reset should enforce password strength."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    user_id = _create_user(client, username="iris", email="iris@example.com")

    resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": "weak"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 400


def test_admin_can_list_user_sessions(web_app) -> None:
    """Admin can view active sessions for a user."""
    from recozik_web.auth_models import get_auth_store
    from recozik_web.auth_service import issue_session

    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)

    # Create user and session
    user_id = _create_user(client, username="jack", email="jack@example.com")
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    assert user is not None

    # Create a session
    issue_session(user, remember=False, store=store)

    resp = client.get(f"/admin/users/{user_id}/sessions")
    assert resp.status_code == 200

    sessions = resp.json()
    assert isinstance(sessions, list)
    assert len(sessions) >= 1
    assert "id" in sessions[0]
    assert "created_at" in sessions[0]
    assert "expires_at" in sessions[0]


def test_admin_can_revoke_user_sessions(web_app) -> None:
    """Admin can revoke all sessions for a user."""
    from recozik_web.auth_models import get_auth_store
    from recozik_web.auth_service import issue_session

    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)
    csrf = login.cookies.get("recozik_csrf")

    # Create user and session
    user_id = _create_user(client, username="kelly", email="kelly@example.com")
    store = get_auth_store(settings.auth_database_url_resolved)
    user = store.get_user_by_id(user_id)
    assert user is not None

    # Create sessions
    issue_session(user, remember=False, store=store)
    issue_session(user, remember=True, store=store)

    # Verify sessions exist
    sessions_before = client.get(f"/admin/users/{user_id}/sessions").json()
    assert len(sessions_before) >= 2

    # Revoke all sessions
    resp = client.delete(
        f"/admin/users/{user_id}/sessions",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200

    # Verify sessions are gone
    sessions_after = client.get(f"/admin/users/{user_id}/sessions").json()
    assert len(sessions_after) == 0


def test_non_admin_cannot_access_user_endpoints(web_app) -> None:
    """Non-admin users should not access user management endpoints."""
    client, _, _, _settings = web_app

    # Create a non-admin user and login
    _create_user(
        client,
        username="normaluser",
        email="normal@example.com",
        password="NormalPass123!",  # noqa: S106
        roles=["readonly"],
    )

    # Login as normal user
    login_resp = client.post(
        "/auth/login",
        json={"username": "normaluser", "password": "NormalPass123!"},
    )
    assert login_resp.status_code == 200
    client.cookies.update(login_resp.cookies)

    # Try to access admin endpoints
    resp = client.get("/admin/users")
    assert resp.status_code == 403


def test_user_list_pagination(web_app) -> None:
    """User list should support pagination."""
    client, _, _, settings = web_app
    login = _login_admin(client, settings)
    client.cookies.update(login.cookies)

    # Create multiple users
    for i in range(5):
        _create_user(client, username=f"user_{i}", email=f"user_{i}@example.com")

    # Test limit
    resp = client.get("/admin/users?limit=3")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) <= 3

    # Test offset
    resp_offset = client.get("/admin/users?limit=3&offset=2")
    assert resp_offset.status_code == 200
    users_offset = resp_offset.json()

    # Results should be different
    if len(users) > 0 and len(users_offset) > 0:
        assert users[0]["id"] != users_offset[0]["id"]

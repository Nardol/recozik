"""Integration tests for the Recozik FastAPI backend."""

from __future__ import annotations

from importlib import import_module, reload
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from recozik_services.identify import IdentifyResponse
from recozik_web.config import WebSettings

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
    """Reload FastAPI modules so they pick up test settings."""

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

    client = TestClient(app_module.app)
    return client, tmp_path, app_module, settings


@pytest.fixture(name="web_app")
def web_app_fixture(monkeypatch, tmp_path: Path):
    """Yield a configured TestClient plus helper context."""
    settings = _override_settings(tmp_path)
    return _bootstrap_app(monkeypatch, tmp_path, settings)


def test_health_endpoint(web_app) -> None:
    """Check the health endpoint returns a success payload."""
    client, _, _, _ = web_app
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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

    def fake_identify(request, **kwargs):
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

    def fake_identify(request, **kwargs):
        return fake_response

    monkeypatch.setattr(app_module, "identify_track", fake_identify)

    response = client.post(
        "/identify/upload",
        files={"file": ("clip.wav", b"audio-bytes", "audio/wav")},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["match_source"] == "audd"

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

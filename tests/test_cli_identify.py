"""Tests for the track identification command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from recozik import audd, cli
from recozik.config import AppConfig, write_config
from recozik.fingerprint import AcoustIDMatch, FingerprintResult, ReleaseInfo

runner = CliRunner()


class DummyCache:
    """Minimal in-memory implementation of the lookup cache API."""

    def __init__(self, *args, **kwargs) -> None:
        """Store parameters and prepare an internal dictionary."""
        self.enabled = kwargs.get("enabled", True)
        self.store: dict[tuple[str, int], list[AcoustIDMatch]] = {}

    def _key(self, fingerprint: str, duration: float) -> tuple[str, int]:
        return (fingerprint, round(duration))

    def get(self, fingerprint: str, duration: float):
        """Return cached matches if caching is enabled."""
        if not self.enabled:
            return None
        return self.store.get(self._key(fingerprint, duration))

    def set(self, fingerprint: str, duration: float, matches):
        """Record matches in the fake cache when caching is enabled."""
        if not self.enabled:
            return
        self.store[self._key(fingerprint, duration)] = list(matches)

    def save(self):
        """Pretend to persist the cache (no-op for the fake cache)."""
        pass


def _fake_config(tmp_path: Path, api_key: str = "token") -> Path:
    """Write a minimal configuration file for tests and return its path."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'[acoustid]\napi_key = "{api_key}"\n', encoding="utf-8")
    return config_path


def test_identify_respects_config_defaults(monkeypatch, tmp_path: Path) -> None:
    """Apply config-provided defaults for limit, JSON rendering, and refresh."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[acoustid]",
                'api_key = "token"',
                "",
                "[identify]",
                "limit = 1",
                "json = true",
                "refresh = true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=102.0),
    )

    def fake_lookup(api_key, fingerprint_result, meta=None, timeout=None):
        assert api_key == "token"
        return [
            AcoustIDMatch(
                score=0.9,
                recording_id="id-1",
                title="First",
                artist="Artist",
            ),
            AcoustIDMatch(
                score=0.8,
                recording_id="id-2",
                title="Second",
                artist="Artist",
            ),
        ]

    monkeypatch.setattr(cli, "lookup_recordings", fake_lookup)

    cache_instances: list[DummyCache] = []

    class TrackingCache(DummyCache):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.get_called = False
            cache_instances.append(self)

        def get(self, fingerprint: str, duration: float):
            self.get_called = True
            return super().get(fingerprint, duration)

    monkeypatch.setattr(cli, "LookupCache", TrackingCache)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["recording_id"] == "id-1"
    assert cache_instances and cache_instances[0].get_called is False


def test_identify_success_json(monkeypatch, tmp_path: Path) -> None:
    """Return JSON payload when --json flag is provided."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = _fake_config(tmp_path)

    def fake_compute(_audio_path, fpcalc_path=None):
        return FingerprintResult(fingerprint="ABC", duration_seconds=123.0)

    def fake_lookup(api_key, fingerprint_result, meta=None, timeout=None):
        assert api_key == "token"
        assert fingerprint_result.fingerprint == "ABC"
        return [
            AcoustIDMatch(
                score=0.88,
                recording_id="mbid-1",
                title="Track",
                artist="Artist",
                releases=[ReleaseInfo(title="Album", release_id="rel-1", date="2020-01-01")],
            ),
        ]

    monkeypatch.setattr(cli, "compute_fingerprint", fake_compute)
    monkeypatch.setattr(cli, "lookup_recordings", fake_lookup)
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["recording_id"] == "mbid-1"
    assert payload[0]["releases"][0]["title"] == "Album"
    assert payload[0]["source"] == "acoustid"


def test_identify_success_text(monkeypatch, tmp_path: Path) -> None:
    """Render textual output with recording details."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=98.1),
    )

    monkeypatch.setattr(
        cli,
        "lookup_recordings",
        lambda *_args, **_kwargs: [
            AcoustIDMatch(
                score=0.75,
                recording_id="mbid-2",
                title="Autre titre",
                artist="Artiste Exemple",
                releases=[ReleaseInfo(title="Album X", date="2018-05-01")],
            )
        ],
    )
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert "Result 1: score 0.75" in result.stdout
    assert "Artiste Exemple - Autre titre" in result.stdout
    assert "Album: Album X (2018-05-01)" in result.stdout


def test_identify_uses_audd_fallback(monkeypatch, tmp_path: Path) -> None:
    """Call AudD when AcoustID returns no match."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=110.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    fake_match = AcoustIDMatch(
        score=0.95,
        recording_id="audd-match",
        title="Fallback Song",
        artist="Fallback Artist",
        release_group_title="Fallback Album",
    )

    class DummyAudDError(Exception):
        pass

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "recognize_with_audd", lambda token, path: [fake_match])

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
        ],
    )

    assert result.exit_code == 0
    assert "Powered by AudD Music (fallback)." in result.stdout
    assert "Fallback Artist - Fallback Song" in result.stdout
    assert "Recording ID: audd-match" in result.stdout


def test_identify_fallback_json_includes_source(monkeypatch, tmp_path: Path) -> None:
    """Expose the source field and attribution when returning JSON."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    fake_match = AcoustIDMatch(
        score=0.88,
        recording_id="audd-json",
        title="JSON Track",
        artist="Artist",
    )

    class DummyAudDError(Exception):
        pass

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "recognize_with_audd", lambda *_args, **_kwargs: [fake_match])

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["source"] == "audd"
    assert payload[0]["recording_id"] == "audd-json"
    assert "Powered by AudD Music (fallback)." in result.stderr


def test_identify_can_disable_audd(monkeypatch, tmp_path: Path) -> None:
    """Skip AudD even when a token is provided."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    def _unexpected_audd(*_args, **_kwargs):
        raise AssertionError("AudD should not be called when --no-audd is set.")

    monkeypatch.setattr(audd, "recognize_with_audd", _unexpected_audd)
    monkeypatch.setattr(audd, "AudDLookupError", RuntimeError)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
            "--no-audd",
        ],
    )

    assert result.exit_code == 0
    assert "No matches found." in result.stdout


def test_identify_prefer_audd(monkeypatch, tmp_path: Path) -> None:
    """Use AudD before AcoustID when requested."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )

    def _unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("AcoustID should not be called when AudD already returned matches.")

    monkeypatch.setattr(cli, "lookup_recordings", _unexpected_lookup)
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    fake_match = AcoustIDMatch(
        score=0.91,
        recording_id="audd-priority",
        title="Priority Song",
        artist="Priority Artist",
    )

    class DummyAudDError(Exception):
        pass

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "recognize_with_audd", lambda *_args, **_kwargs: [fake_match])

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
            "--prefer-audd",
        ],
    )

    assert result.exit_code == 0
    assert "Powered by AudD Music (fallback)." in result.stdout
    assert "Priority Artist - Priority Song" in result.stdout


def test_identify_without_key(monkeypatch, tmp_path: Path) -> None:
    """Abort when no API key is available and the user declines to configure it."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = _fake_config(tmp_path, api_key="")

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="", duration_seconds=0.0),
    )
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
        ],
        input="n\n",
    )

    assert result.exit_code == 1
    assert "No AcoustID API key configured." in result.stdout
    assert "Operation cancelled." in result.stdout


def test_identify_template_override(monkeypatch, tmp_path: Path) -> None:
    """Apply a custom output template passed on the CLI."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=100.0),
    )

    monkeypatch.setattr(
        cli,
        "lookup_recordings",
        lambda *_args, **_kwargs: [
            AcoustIDMatch(
                score=0.5,
                recording_id="rec",
                title="Titre",
                artist="Artiste",
            )
        ],
    )

    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--template",
            "{artist} :: {title}",
        ],
    )

    assert result.exit_code == 0
    assert "Artiste :: Titre" in result.stdout


def test_identify_register_key_via_prompt(monkeypatch, tmp_path: Path) -> None:
    """Store a prompted API key and continue the identification flow."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = tmp_path / "config.toml"

    def fake_compute(_audio_path, fpcalc_path=None):
        return FingerprintResult(fingerprint="PROMPT", duration_seconds=120.0)

    def fake_lookup(api_key, fingerprint_result, meta=None, timeout=None):
        assert api_key == "token"
        return [
            AcoustIDMatch(
                score=0.7,
                recording_id="id",
                title="Titre",
                artist="Artiste",
            )
        ]

    def fake_configure(existing, path, skip_validation=False):
        updated = AppConfig(
            acoustid_api_key="token",
            cache_enabled=existing.cache_enabled,
            cache_ttl_hours=existing.cache_ttl_hours,
            output_template=existing.output_template,
            log_format=existing.log_format,
            log_absolute_paths=existing.log_absolute_paths,
        )
        write_config(updated, path)
        return "token"

    monkeypatch.setattr(cli, "compute_fingerprint", fake_compute)
    monkeypatch.setattr(cli, "lookup_recordings", fake_lookup)
    monkeypatch.setattr(cli, "LookupCache", DummyCache)
    monkeypatch.setattr(cli, "_configure_api_key_interactively", fake_configure)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
        ],
        input="o\n",
    )

    assert result.exit_code == 0
    assert "Result 1" in result.stdout


def test_identify_respects_locale_env(monkeypatch, tmp_path: Path) -> None:
    """Switch to French locale when RECOZIK_LOCALE is set."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = _fake_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )

    monkeypatch.setattr(
        cli,
        "lookup_recordings",
        lambda *_args, **_kwargs: [
            AcoustIDMatch(
                score=0.42,
                recording_id="rec",
                title="Titre",
                artist="Artiste",
            )
        ],
    )
    monkeypatch.setattr(cli, "LookupCache", DummyCache)

    result = runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
        ],
        env={"RECOZIK_LOCALE": "fr_FR"},
    )

    assert result.exit_code == 0
    assert "Résultat 1" in result.stdout

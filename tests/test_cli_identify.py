"""Tests for the track identification command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from recozik import audd, cli
from recozik.config import AppConfig, write_config
from recozik.fingerprint import AcoustIDMatch, FingerprintResult, ReleaseInfo

from .helpers.identify import DummyLookupCache, make_config


def test_identify_respects_config_defaults(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
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

    cache_instances: list[DummyLookupCache] = []

    class TrackingCache(DummyLookupCache):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.get_called = False
            cache_instances.append(self)

        def get(self, fingerprint: str, duration: float):
            self.get_called = True
            return super().get(fingerprint, duration)

    monkeypatch.setattr(cli, "LookupCache", TrackingCache)

    result = cli_runner.invoke(
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


def test_identify_success_json(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Return JSON payload when --json flag is provided."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = make_config(tmp_path)

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
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    result = cli_runner.invoke(
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


def test_identify_success_text(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Render textual output with recording details."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = make_config(tmp_path)

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
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    result = cli_runner.invoke(
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


def test_identify_deduplicates_by_template(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Collapse matches that render to identical filenames."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=101.4),
    )

    def fake_lookup(_key, _fingerprint, meta=None, timeout=None):
        return [
            AcoustIDMatch(
                score=0.99,
                recording_id="rec-1",
                title="Titre",
                artist="Artiste",
                release_group_title="Album A",
            ),
            AcoustIDMatch(
                score=0.98,
                recording_id="rec-2",
                title="Titre",
                artist="Artiste",
                release_group_title="Album B",
            ),
            AcoustIDMatch(
                score=0.90,
                recording_id="rec-3",
                title="Autre titre",
                artist="Artiste",
            ),
        ]

    monkeypatch.setattr(cli, "lookup_recordings", fake_lookup)
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    result = cli_runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--limit",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.count("Result ") == 2
    assert "Recording ID: rec-1" in result.stdout
    assert "Recording ID: rec-3" in result.stdout
    assert "Recording ID: rec-2" not in result.stdout
    assert "Result 3" not in result.stdout


def test_identify_uses_audd_fallback(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Call AudD when AcoustID returns no match."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=110.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

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
    monkeypatch.setattr(audd, "recognize_with_audd", lambda token, path, **_kwargs: [fake_match])

    result = cli_runner.invoke(
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
    assert "Fallback Artist - Fallback Song" in result.stdout
    assert "Recording ID: audd-match" in result.stdout
    assert "Identification strategy: AcoustID first, AudD fallback." in result.stderr


def test_identify_fallback_json_includes_source(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Expose the source field and attribution when returning JSON."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

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

    result = cli_runner.invoke(
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
    assert "Identification strategy: AcoustID first, AudD fallback." in result.stderr


def test_identify_can_disable_audd(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Skip AudD even when a token is provided."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    def _unexpected_audd(*_args, **_kwargs):
        raise AssertionError("AudD should not be called when --no-audd is set.")

    monkeypatch.setattr(audd, "recognize_with_audd", _unexpected_audd)
    monkeypatch.setattr(audd, "AudDLookupError", RuntimeError)

    result = cli_runner.invoke(
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
    assert "AcoustID only (AudD disabled)." in result.stderr


def test_identify_prefer_audd(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Use AudD before AcoustID when requested."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )

    def _unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("AcoustID should not be called when AudD already returned matches.")

    monkeypatch.setattr(cli, "lookup_recordings", _unexpected_lookup)
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

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

    result = cli_runner.invoke(
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
    assert "Priority Artist - Priority Song" in result.stdout
    assert "AudD first, AcoustID fallback." in result.stderr


def test_identify_snippet_offset_option(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Shift the AudD snippet when --audd-snippet-offset is provided."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    fake_match = AcoustIDMatch(
        score=0.92,
        recording_id="audd-offset",
        title="Offset Track",
        artist="Artist",
    )

    captured_offsets: list[float | None] = []

    def fake_recognize(token, path, **kwargs):
        captured_offsets.append(kwargs.get("snippet_offset"))
        hook = kwargs.get("snippet_hook")
        if hook is not None:
            hook(
                audd.SnippetInfo(
                    offset_seconds=float(kwargs.get("snippet_offset") or 0.0),
                    duration_seconds=12.0,
                    rms=0.8,
                )
            )
        return [fake_match]

    monkeypatch.setattr(audd, "AudDLookupError", RuntimeError)
    monkeypatch.setattr(audd, "recognize_with_audd", fake_recognize)

    result = cli_runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
            "--prefer-audd",
            "--audd-snippet-offset",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert captured_offsets == [5.0]
    assert "~5.00s" in result.stdout
    assert "Artist - Offset Track" in result.stdout


def test_identify_snippet_low_rms_warning(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Emit a warning when the snippet RMS falls below the configured threshold."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    def fake_recognize(token, path, **kwargs):
        hook = kwargs.get("snippet_hook")
        if hook is not None:
            hook(audd.SnippetInfo(offset_seconds=0.0, duration_seconds=12.0, rms=0.0001))
        return []

    monkeypatch.setattr(audd, "AudDLookupError", RuntimeError)
    monkeypatch.setattr(audd, "recognize_with_audd", fake_recognize)

    result = cli_runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
            "--prefer-audd",
            "--audd-snippet-min-rms",
            "0.01",
        ],
    )

    assert result.exit_code == 0
    assert "RMS" in result.stderr


def test_identify_silent_source(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Silence the strategy announcement when requested."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    fake_match = AcoustIDMatch(
        score=0.9,
        recording_id="audd-silent",
        title="Silent Song",
        artist="Silent Artist",
    )

    class DummyAudDError(Exception):
        pass

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "recognize_with_audd", lambda *_args, **_kwargs: [fake_match])

    result = cli_runner.invoke(
        cli.app,
        [
            "identify",
            str(audio_path),
            "--config-path",
            str(config_path),
            "--audd-token",
            "secret-token",
            "--silent-source",
        ],
    )

    assert result.exit_code == 0
    assert "Silent Artist - Silent Song" in result.stdout
    assert "Identification strategy" not in result.stderr


def test_identify_announces_audd_snippet(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Let users know when a snippet is prepared for AudD uploads."""
    audio_path = tmp_path / "long.wav"
    audio_path.write_bytes(b"0" * 2048)
    config_path = make_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="FP", duration_seconds=90.0),
    )
    monkeypatch.setattr(cli, "lookup_recordings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    fake_match = AcoustIDMatch(
        score=0.91,
        recording_id="audd-snippet",
        title="Snippet Title",
        artist="Snippet Artist",
    )

    class DummyAudDError(Exception):
        pass

    def fake_recognize(*_args, **kwargs):
        hook = kwargs.get("snippet_hook")
        if hook is not None:
            hook(audd.SnippetInfo(offset_seconds=0.0, duration_seconds=12.0, rms=0.8))
        return [fake_match]

    monkeypatch.setattr(audd, "AudDLookupError", DummyAudDError)
    monkeypatch.setattr(audd, "MAX_AUDD_BYTES", 1)
    monkeypatch.setattr(audd, "recognize_with_audd", fake_recognize)

    result = cli_runner.invoke(
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
    assert "Preparing AudD snippet" in result.stdout
    assert "Snippet Artist - Snippet Title" in result.stdout


def test_identify_without_key(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Abort when no API key is available and the user declines to configure it."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = make_config(tmp_path, api_key="")

    monkeypatch.setattr(
        cli,
        "compute_fingerprint",
        lambda *_args, **_kwargs: FingerprintResult(fingerprint="", duration_seconds=0.0),
    )
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    result = cli_runner.invoke(
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


def test_identify_template_override(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Apply a custom output template passed on the CLI."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")
    config_path = make_config(tmp_path)

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

    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    result = cli_runner.invoke(
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


def test_identify_register_key_via_prompt(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
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
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)
    monkeypatch.setattr(cli, "_configure_api_key_interactively", fake_configure)

    result = cli_runner.invoke(
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


def test_identify_respects_locale_env(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Switch to French locale when RECOZIK_LOCALE is set."""
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = make_config(tmp_path)

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
    monkeypatch.setattr(cli, "LookupCache", DummyLookupCache)

    result = cli_runner.invoke(
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

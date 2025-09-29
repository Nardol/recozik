from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from recozik import cli
from recozik.fingerprint import AcoustIDMatch, FingerprintResult, ReleaseInfo

runner = CliRunner()


class DummyCache:
    def __init__(self, *args, **kwargs) -> None:
        self.enabled = kwargs.get("enabled", True)
        self.store: dict[tuple[str, int], list[AcoustIDMatch]] = {}

    def _key(self, fingerprint: str, duration: float) -> tuple[str, int]:
        return (fingerprint, int(round(duration)))

    def get(self, fingerprint: str, duration: float):
        if not self.enabled:
            return None
        return self.store.get(self._key(fingerprint, duration))

    def set(self, fingerprint: str, duration: float, matches):
        if not self.enabled:
            return
        self.store[self._key(fingerprint, duration)] = list(matches)

    def save(self):
        pass


def _fake_config(tmp_path: Path, api_key: str = "token") -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(f"[acoustid]\napi_key = \"{api_key}\"\n", encoding="utf-8")
    return config_path


def test_identify_success_json(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "song.wav"
    audio_path.write_bytes(b"fake")

    config_path = _fake_config(tmp_path)

    def fake_compute(_audio_path, fpcalc_path=None):
        return FingerprintResult(fingerprint="ABC", duration_seconds=123.0)

    def fake_lookup(api_key, fingerprint_result, meta=None, timeout=None):  # noqa: D401
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


def test_identify_success_text(monkeypatch, tmp_path: Path) -> None:
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
    assert "Résultat 1: score 0.75" in result.stdout
    assert "Artiste Exemple - Autre titre" in result.stdout
    assert "Album: Album X (2018-05-01)" in result.stdout


def test_identify_without_key(monkeypatch, tmp_path: Path) -> None:
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
    )

    assert result.exit_code == 1
    assert "Aucune clé API AcoustID" in result.stdout


def test_identify_template_override(monkeypatch, tmp_path: Path) -> None:
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

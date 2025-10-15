"""Tests for the AcoustID lookup helpers."""

from __future__ import annotations

from typing import Any

import pytest

from recozik.fingerprint import (
    AcoustIDLookupError,
    FingerprintResult,
    ReleaseInfo,
    lookup_recordings,
)


def _sample_response() -> dict[str, Any]:
    """Return a representative response payload from the API."""
    return {
        "status": "ok",
        "results": [
            {
                "score": 0.91,
                "recordings": [
                    {
                        "id": "mbid-1",
                        "title": "Titre",
                        "artists": [
                            {"name": "Artiste", "joinphrase": " feat. "},
                            {"name": "Invité"},
                        ],
                        "releasegroups": [
                            {"id": "rg-1", "title": "Album"},
                        ],
                        "releases": [
                            {
                                "id": "rel-1",
                                "title": "Album",
                                "date": "2022-09-01",
                                "country": "FR",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_lookup_recordings_parses_response(monkeypatch) -> None:
    """Parse API payloads into `AcoustIDMatch` instances."""
    monkeypatch.setattr(
        "recozik.fingerprint.pyacoustid.lookup",
        lambda *_args, **_kwargs: _sample_response(),
    )

    matches = lookup_recordings("token", FingerprintResult(fingerprint="FP", duration_seconds=95.3))

    assert len(matches) == 1
    match = matches[0]
    assert match.score == pytest.approx(0.91)
    assert match.recording_id == "mbid-1"
    assert match.artist == "Artiste feat. Invité"
    assert match.release_group_id == "rg-1"
    assert match.releases[0] == ReleaseInfo(
        title="Album",
        release_id="rel-1",
        date="2022-09-01",
        country="FR",
    )


def test_lookup_recordings_requires_api_key() -> None:
    """Require an API key before performing a lookup."""
    with pytest.raises(AcoustIDLookupError):
        lookup_recordings("", FingerprintResult(fingerprint="FP", duration_seconds=10))


def test_lookup_recordings_deduplicates_matches(monkeypatch) -> None:
    """Collapse duplicate recordings while preserving metadata."""
    response: dict[str, Any] = {
        "status": "ok",
        "results": [
            {
                "score": 0.95,
                "recordings": [
                    {
                        "id": "mbid-1",
                        "title": "Titre",
                        "artists": [{"name": "Artiste"}],
                        "releases": [
                            {
                                "id": "rel-1",
                                "title": "Album A",
                                "date": "2022-09-01",
                                "country": "FR",
                            }
                        ],
                    }
                ],
            },
            {
                "score": 0.87,
                "recordings": [
                    {
                        "id": "mbid-1",
                        "releasegroups": [{"id": "rg-1", "title": "Album A"}],
                        "releases": [
                            {
                                "id": "rel-1",
                                "title": "Album A",
                                "date": "2022-09-01",
                                "country": "FR",
                            },
                            {
                                "id": "rel-2",
                                "title": "Compilation",
                                "date": "2023-01-15",
                                "country": "US",
                            },
                        ],
                    },
                    {
                        "id": "mbid-2",
                        "title": "Autre Titre",
                        "artists": [{"name": "Second Artiste"}],
                        "releases": [
                            {
                                "id": "rel-3",
                                "title": "Album B",
                                "date": "2021-05-20",
                                "country": "GB",
                            }
                        ],
                    },
                ],
            },
        ],
    }

    monkeypatch.setattr(
        "recozik.fingerprint.pyacoustid.lookup",
        lambda *_args, **_kwargs: response,
    )

    matches = lookup_recordings("token", FingerprintResult(fingerprint="FP", duration_seconds=95.3))

    assert len(matches) == 2
    first, second = matches

    assert first.recording_id == "mbid-1"
    assert first.score == pytest.approx(0.95)
    assert first.release_group_id == "rg-1"
    assert {release.release_id for release in first.releases} == {"rel-1", "rel-2"}

    assert second.recording_id == "mbid-2"
    assert second.score == pytest.approx(0.87)

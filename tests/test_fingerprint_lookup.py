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
    with pytest.raises(AcoustIDLookupError):
        lookup_recordings("", FingerprintResult(fingerprint="FP", duration_seconds=10))

"""Utility functions to generate and look up audio fingerprints via Chromaprint."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

try:
    import acoustid as pyacoustid
except ImportError:  # pragma: no cover - compatibility with future or legacy versions
    import pyacoustid  # type: ignore[no-redef]

_FPCALC_ERRORS: tuple[type[Exception], ...] = tuple(
    exc
    for exc in (
        getattr(pyacoustid, "FpCalcNotFoundError", None),
        getattr(pyacoustid, "NoBackendError", None),
    )
    if isinstance(exc, type)
)


@dataclass(slots=True)
class FingerprintResult:
    """Represent the Chromaprint fingerprint output."""

    fingerprint: str
    duration_seconds: float


class FingerprintError(RuntimeError):
    """Raised when the fingerprint cannot be computed."""


@dataclass(slots=True)
class ReleaseInfo:
    """Compact metadata about a release (album, single, etc.)."""

    title: str | None = None
    release_id: str | None = None
    date: str | None = None
    country: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize the release metadata into a plain dictionary."""
        return {
            "title": self.title,
            "release_id": self.release_id,
            "date": self.date,
            "country": self.country,
        }


@dataclass(slots=True)
class AcoustIDMatch:
    """Represent a recording entry returned by the AcoustID API."""

    score: float
    recording_id: str
    title: str | None
    artist: str | None
    release_group_id: str | None = None
    release_group_title: str | None = None
    releases: list[ReleaseInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize the match into a JSON-compatible dictionary."""
        return {
            "score": self.score,
            "recording_id": self.recording_id,
            "title": self.title,
            "artist": self.artist,
            "release_group_id": self.release_group_id,
            "release_group_title": self.release_group_title,
            "releases": [release.to_dict() for release in self.releases],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> AcoustIDMatch:
        """Create a match instance from a dictionary returned by the API."""
        releases = [
            ReleaseInfo(
                title=item.get("title"),
                release_id=item.get("release_id"),
                date=item.get("date"),
                country=item.get("country"),
            )
            for item in payload.get("releases", [])
            if isinstance(item, dict)
        ]

        recording_id = payload.get("recording_id")
        if recording_id is None:
            recording_id = ""

        return cls(
            score=float(payload.get("score", 0.0)),
            recording_id=str(recording_id),
            title=payload.get("title"),
            artist=payload.get("artist"),
            release_group_id=payload.get("release_group_id"),
            release_group_title=payload.get("release_group_title"),
            releases=releases,
        )


class AcoustIDLookupError(RuntimeError):
    """Raised when the AcoustID API request fails."""


def compute_fingerprint(
    audio_path: Path,
    *,
    fpcalc_path: Path | None = None,
) -> FingerprintResult:
    """Compute the Chromaprint fingerprint for the provided audio file.

    Args:
        audio_path: Path to the audio file that must be fingerprinted.
        fpcalc_path: Explicit path to the ``fpcalc`` executable when it is outside ``PATH``.

    Returns:
        FingerprintResult: Fingerprint string and estimated track duration.

    Raises:
        FingerprintError: Raised when the file is missing or ``fpcalc`` execution fails.

    """
    if not audio_path.is_file():
        raise FingerprintError(f"Fichier audio introuvable: {audio_path}")

    fpcalc_override = str(fpcalc_path) if fpcalc_path else None
    env_var = getattr(pyacoustid, "FPCALC_ENVVAR", "FPCALC")
    previous_fpcalc = None

    if fpcalc_override:
        previous_fpcalc = os.environ.get(env_var)
        os.environ[env_var] = fpcalc_override

    try:
        raw_first, raw_second = pyacoustid.fingerprint_file(
            str(audio_path), force_fpcalc=bool(fpcalc_override)
        )
        fingerprint, duration = _normalize_fingerprint_output(raw_first, raw_second)
    except Exception as exc:  # pragma: no cover - pyacoustid utilise divers types d'exceptions
        if _FPCALC_ERRORS and isinstance(exc, _FPCALC_ERRORS):  # type: ignore[arg-type]
            raise FingerprintError(
                "L'outil fpcalc (Chromaprint) est introuvable. "
                "Installez-le ou précisez --fpcalc-path."
            ) from exc
        raise FingerprintError(f"Échec du calcul d'empreinte: {exc}") from exc
    finally:
        if fpcalc_override:
            if previous_fpcalc is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = previous_fpcalc

    return FingerprintResult(fingerprint=fingerprint, duration_seconds=float(duration))


def _normalize_fingerprint_output(
    raw_first: object,
    raw_second: object,
) -> tuple[str, float]:
    """Normalize ``pyacoustid.fingerprint_file`` output across versions.

    Recent ``acoustid`` releases return ``(duration, fingerprint)`` while older ones
    returned ``(fingerprint, duration)``.
    """

    def _ensure_str(value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    if isinstance(raw_first, (int, float)):
        duration = float(raw_first)
        fingerprint = _ensure_str(raw_second)
    elif isinstance(raw_second, (int, float)):
        fingerprint = _ensure_str(raw_first)
        duration = float(raw_second)
    else:
        # Fall back to assuming the second element stores the duration
        fingerprint = _ensure_str(raw_first)
        try:
            duration = float(raw_second)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise FingerprintError(
                "Unexpected fpcalc output: unable to determine the track duration."
            ) from exc

    return fingerprint, duration


def lookup_recordings(
    api_key: str,
    fingerprint_result: FingerprintResult,
    *,
    meta: Sequence[str] | None = None,
    timeout: float | None = None,
) -> list[AcoustIDMatch]:
    """Query the AcoustID API and return best matches."""
    if not api_key:
        raise AcoustIDLookupError("Aucune clé API fournie pour interroger AcoustID.")

    meta_fields: Sequence[str] = meta or (
        "recordings",
        "releasegroups",
        "releases",
        "tracks",
        "compress",
    )

    try:
        data = pyacoustid.lookup(
            api_key,
            fingerprint_result.fingerprint,
            round(fingerprint_result.duration_seconds),
            meta=list(meta_fields),
            timeout=timeout,
        )
    except pyacoustid.WebServiceError as exc:  # type: ignore[attr-defined]
        raise AcoustIDLookupError(f"Requête AcoustID échouée: {exc}") from exc
    except Exception as exc:  # pragma: no cover - sécurité supplémentaire
        raise AcoustIDLookupError(f"Erreur inattendue lors de l'appel AcoustID: {exc}") from exc

    if data.get("status") != "ok":
        raise AcoustIDLookupError("Réponse AcoustID invalide ou incomplète.")

    deduped_matches: dict[str, AcoustIDMatch] = {}

    for result in data.get("results", []):
        try:
            score = float(result.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0

        for recording in result.get("recordings", []) or []:
            recording_id = recording.get("id")
            if not recording_id:
                continue

            title = recording.get("title")
            artist = _format_artists(recording.get("artists"))

            release_group_id, release_group_title = _extract_release_group(recording)
            releases = _extract_releases(recording)

            match = AcoustIDMatch(
                score=score,
                recording_id=recording_id,
                title=title,
                artist=artist,
                release_group_id=release_group_id,
                release_group_title=release_group_title,
                releases=releases,
            )

            existing = deduped_matches.get(recording_id)
            if existing is None:
                deduped_matches[recording_id] = match
                continue

            _merge_matches(existing, match)

    matches = sorted(deduped_matches.values(), key=lambda match: match.score, reverse=True)

    return matches


def _format_artists(artists: Sequence[dict] | None) -> str | None:
    if not artists:
        return None

    buffer = []
    for artist in artists:
        name = artist.get("name") if isinstance(artist, dict) else None
        if not name:
            continue
        joinphrase = artist.get("joinphrase", "") if isinstance(artist, dict) else ""
        buffer.append(f"{name}{joinphrase}")

    text = "".join(buffer).strip()
    return text or None


def _extract_release_group(recording: dict) -> tuple[str | None, str | None]:
    releasegroups = recording.get("releasegroups") or []
    if not releasegroups:
        return None, None

    first = releasegroups[0]
    if not isinstance(first, dict):
        return None, None

    return first.get("id"), first.get("title")


def _extract_releases(recording: dict) -> list[ReleaseInfo]:
    releases_data = recording.get("releases") or []
    releases: list[ReleaseInfo] = []

    for release in releases_data:
        if not isinstance(release, dict):
            continue
        releases.append(
            ReleaseInfo(
                title=release.get("title"),
                release_id=release.get("id"),
                date=release.get("date"),
                country=release.get("country"),
            )
        )

    return releases


def _merge_matches(existing: AcoustIDMatch, new: AcoustIDMatch) -> None:
    """Merge duplicate AcoustID matches in-place, preserving enriched metadata."""
    if new.score > existing.score:
        existing.score = new.score
    else:
        existing.score = max(existing.score, new.score)

    if not existing.title and new.title:
        existing.title = new.title

    if not existing.artist and new.artist:
        existing.artist = new.artist

    if not existing.release_group_id and new.release_group_id:
        existing.release_group_id = new.release_group_id

    if new.release_group_title and (
        not existing.release_group_title or existing.release_group_id == new.release_group_id
    ):
        existing.release_group_title = new.release_group_title

    _merge_releases(existing.releases, new.releases)


def _merge_releases(target: list[ReleaseInfo], source: list[ReleaseInfo]) -> None:
    """Extend `target` with releases from `source`, avoiding duplicates."""
    seen = {(item.release_id, item.title, item.date, item.country) for item in target}

    for release in source:
        fingerprint = (release.release_id, release.title, release.date, release.country)
        if fingerprint in seen:
            continue
        target.append(release)
        seen.add(fingerprint)

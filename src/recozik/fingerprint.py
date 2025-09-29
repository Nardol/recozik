"""Fonctions utilitaires pour générer des empreintes audio avec Chromaprint."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Optional, Sequence

try:
    import acoustid as pyacoustid
except ImportError:  # pragma: no cover - compatibilité avec versions futures/anciennes
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
    """Représente l'empreinte générée par Chromaprint."""

    fingerprint: str
    duration_seconds: float


class FingerprintError(RuntimeError):
    """Erreur levée lorsqu'il est impossible de calculer l'empreinte."""


@dataclass(slots=True)
class ReleaseInfo:
    """Informations synthétiques sur une sortie (album, single...)."""

    title: Optional[str] = None
    release_id: Optional[str] = None
    date: Optional[str] = None
    country: Optional[str] = None

    def to_dict(self) -> dict[str, Optional[str]]:
        return {
            "title": self.title,
            "release_id": self.release_id,
            "date": self.date,
            "country": self.country,
        }


@dataclass(slots=True)
class AcoustIDMatch:
    """Représente un enregistrement renvoyé par l'API AcoustID."""

    score: float
    recording_id: str
    title: Optional[str]
    artist: Optional[str]
    release_group_id: Optional[str] = None
    release_group_title: Optional[str] = None
    releases: list[ReleaseInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
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
    def from_dict(cls, payload: dict) -> "AcoustIDMatch":
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
    """Erreur levée lorsqu'un appel à l'API AcoustID échoue."""


def compute_fingerprint(
    audio_path: Path,
    *,
    fpcalc_path: Optional[Path] = None,
) -> FingerprintResult:
    """Calcule l'empreinte Chromaprint du fichier audio fourni.

    Args:
        audio_path: chemin du fichier audio.
        fpcalc_path: chemin explicite vers l'exécutable ``fpcalc`` si non présent dans ``PATH``.

    Returns:
        FingerprintResult: empreinte et durée estimée du morceau.

    Raises:
        FingerprintError: si le fichier n'existe pas ou si ``fpcalc`` échoue.
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
                "L'outil fpcalc (Chromaprint) est introuvable. Installez-le ou précisez --fpcalc-path."
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
    """Normalise la sortie de `pyacoustid.fingerprint_file`.

    Les versions récentes d'``acoustid`` renvoient ``(duration, fingerprint)``
    alors que les anciennes renvoyaient ``(fingerprint, duration)``.
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
        # Dernier recours : on suppose que le deuxième élément est la durée
        fingerprint = _ensure_str(raw_first)
        try:
            duration = float(raw_second)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise FingerprintError(
                "Réponse inattendue de l'outil fpcalc: impossible de déterminer la durée."
            ) from exc

    return fingerprint, duration


def lookup_recordings(
    api_key: str,
    fingerprint_result: FingerprintResult,
    *,
    meta: Optional[Sequence[str]] = None,
    timeout: Optional[float] = None,
) -> list[AcoustIDMatch]:
    """Interroge l'API AcoustID et retourne les meilleures correspondances."""

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
            int(round(fingerprint_result.duration_seconds)),
            meta=list(meta_fields),
            timeout=timeout,
        )
    except pyacoustid.WebServiceError as exc:  # type: ignore[attr-defined]
        raise AcoustIDLookupError(f"Requête AcoustID échouée: {exc}") from exc
    except Exception as exc:  # pragma: no cover - sécurité supplémentaire
        raise AcoustIDLookupError(f"Erreur inattendue lors de l'appel AcoustID: {exc}") from exc

    if data.get("status") != "ok":
        raise AcoustIDLookupError("Réponse AcoustID invalide ou incomplète.")

    matches: list[AcoustIDMatch] = []

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

            matches.append(
                AcoustIDMatch(
                    score=score,
                    recording_id=recording_id,
                    title=title,
                    artist=artist,
                    release_group_id=release_group_id,
                    release_group_title=release_group_title,
                    releases=releases,
                )
            )

    matches.sort(key=lambda match: match.score, reverse=True)

    return matches


def _format_artists(artists: Optional[Sequence[dict]]) -> Optional[str]:
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


def _extract_release_group(recording: dict) -> tuple[Optional[str], Optional[str]]:
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

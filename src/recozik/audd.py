"""AudD fallback integration helpers."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import requests
import soundfile

from .fingerprint import AcoustIDMatch, ReleaseInfo
from .i18n import _

DEFAULT_ENDPOINT = "https://api.audd.io/"
MAX_AUDD_BYTES = 10 * 1024 * 1024
SNIPPET_DURATION_SECONDS = 45.0
_AUDD_TARGET_SAMPLE_RATE = 16_000
_AUDD_SNIPPET_SUFFIX = ".wav"


class AudDLookupError(RuntimeError):
    """Raised when the AudD API request fails."""


@dataclass(slots=True)
class AudDMatch:
    """Represent a simplified AudD recognition result."""

    artist: str | None
    title: str | None
    album: str | None
    release_date: str | None
    label: str | None
    confidence: float | None
    song_link: str | None
    apple_music_id: str | None
    spotify_id: str | None
    deezer_id: str | None

    def to_acoustid_match(self) -> AcoustIDMatch:
        """Convert the AudD payload to the internal AcoustIDMatch structure."""
        release_entries: list[ReleaseInfo] = []
        if self.album or self.release_date:
            release_entries.append(
                ReleaseInfo(
                    title=self.album,
                    release_id=self.apple_music_id or self.spotify_id or self.deezer_id,
                    date=self.release_date,
                    country=None,
                )
            )

        identifier = (
            self.apple_music_id
            or self.spotify_id
            or self.deezer_id
            or self.song_link
            or _build_synthetic_identifier(self.artist, self.title)
        )

        score = self.confidence if self.confidence is not None else 1.0
        try:
            clipped = max(0.0, min(float(score), 1.0))
        except (TypeError, ValueError):
            clipped = 1.0

        return AcoustIDMatch(
            score=clipped,
            recording_id=identifier,
            title=self.title,
            artist=self.artist,
            release_group_id=self.apple_music_id or self.spotify_id or self.deezer_id,
            release_group_title=self.album,
            releases=release_entries,
        )


def recognize_with_audd(
    api_token: str,
    audio_path: Path,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 20.0,
) -> list[AcoustIDMatch]:
    """Send an identification request to AudD and normalize results."""
    if not api_token:
        raise AudDLookupError(_("No AudD token provided."))
    if not audio_path.is_file():
        raise AudDLookupError(_("Audio file not found: {path}").format(path=audio_path))

    try:
        payload_manager = _prepare_audd_payload(audio_path)
    except AudDLookupError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise AudDLookupError(
            _("Unable to prepare audio for AudD: {error}").format(error=exc)
        ) from exc

    with payload_manager as payload_path:
        try:
            with payload_path.open("rb") as handle:
                files = {"file": (audio_path.name, handle, "application/octet-stream")}
                data = {
                    "api_token": api_token,
                    # Request common catalog identifiers to enrich results if available.
                    "return": "apple_music,spotify,deezer",
                }
                response = requests.post(endpoint, data=data, files=files, timeout=timeout)
        except requests.RequestException as exc:  # pragma: no cover - network failures
            raise AudDLookupError(_("AudD request failed: {error}").format(error=exc)) from exc

    if response.status_code != 200:
        raise AudDLookupError(
            _("AudD returned an unexpected HTTP status: {status}").format(
                status=response.status_code
            )
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AudDLookupError(_("Invalid JSON response received from AudD.")) from exc

    if payload.get("status") != "success":
        message = _extract_error_message(payload)
        raise AudDLookupError(message)

    result = payload.get("result")
    if not result:
        return []

    entries = result if isinstance(result, list) else [result]
    matches: list[AcoustIDMatch] = []

    for entry in entries:
        match = _normalize_entry(entry)
        if match:
            matches.append(match.to_acoustid_match())

    return matches


def _normalize_entry(entry: Any) -> AudDMatch | None:
    if not isinstance(entry, dict):
        return None

    apple_music = entry.get("apple_music") or {}
    spotify = entry.get("spotify") or {}
    deezer = entry.get("deezer") or {}

    confidence = entry.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None

    return AudDMatch(
        artist=_safe_str(entry.get("artist")),
        title=_safe_str(entry.get("title")),
        album=_safe_str(entry.get("album")),
        release_date=_safe_str(entry.get("release_date")),
        label=_safe_str(entry.get("label")),
        confidence=confidence_value,
        song_link=_safe_str(entry.get("song_link")),
        apple_music_id=_extract_first_non_empty(apple_music, ("id", "trackId")),
        spotify_id=_extract_first_non_empty(spotify, ("id", "track_id")),
        deezer_id=_extract_first_non_empty(deezer, ("id", "track_id")),
    )


def _extract_error_message(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("error_message") or error.get("message")
        if message:
            return str(message)
    if isinstance(error, str):
        return error
    result = payload.get("result")
    if isinstance(result, str):
        return result
    return _("AudD reported an error without details.")


def _extract_first_non_empty(mapping: Any, keys: tuple[str, ...]) -> str | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value:
            return str(value)
    return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_synthetic_identifier(artist: str | None, title: str | None) -> str:
    buffer = f"{artist or ''}::{title or ''}"
    digest = sha256(buffer.encode("utf-8")).hexdigest()
    return f"audd:{digest}"


def needs_audd_snippet(audio_path: Path) -> bool:
    """Return True when the audio file exceeds AudD's upload size limit."""
    try:
        return audio_path.stat().st_size > MAX_AUDD_BYTES
    except OSError as exc:  # pragma: no cover - filesystem failures
        raise AudDLookupError(_("Unable to access audio file: {error}").format(error=exc)) from exc


@contextmanager
def _prepare_audd_payload(audio_path: Path) -> Iterator[Path]:
    """Return a context manager yielding the path to upload to AudD."""
    if not needs_audd_snippet(audio_path):
        yield audio_path
        return

    snippet_path = Path(tempfile.mkstemp(prefix="recozik-audd-", suffix=_AUDD_SNIPPET_SUFFIX)[1])
    try:
        _render_snippet(audio_path, snippet_path)
        size = snippet_path.stat().st_size
        if size > MAX_AUDD_BYTES:
            raise AudDLookupError(
                _("AudD snippet still exceeds {limit} bytes (got {size}).").format(
                    limit=MAX_AUDD_BYTES,
                    size=size,
                )
            )
        yield snippet_path
    finally:
        snippet_path.unlink(missing_ok=True)


def _render_snippet(
    audio_path: Path,
    destination: Path,
    *,
    snippet_seconds: float = SNIPPET_DURATION_SECONDS,
    target_sample_rate: int = _AUDD_TARGET_SAMPLE_RATE,
) -> None:
    """Render a mono PCM snippet suitable for AudD uploads."""
    try:
        import librosa
    except Exception as exc:  # pragma: no cover - dependency missing
        raise AudDLookupError(
            _("AudD snippet generation requires librosa: {error}").format(error=exc)
        ) from exc

    try:
        with soundfile.SoundFile(audio_path, "r") as source:
            source_frames = source.frames
            source_rate = source.samplerate
            duration_frames = min(
                int(snippet_seconds * source_rate),
                source_frames,
            )
            if duration_frames <= 0:
                raise AudDLookupError(_("Audio file is empty."))
            source.seek(0)
            buffer = source.read(duration_frames, dtype="float32", always_2d=True)
    except RuntimeError as exc:
        raise AudDLookupError(
            _("Failed to read audio for AudD snippet: {error}").format(error=exc)
        ) from exc

    if buffer.size == 0:
        raise AudDLookupError(_("Failed to read audio for AudD snippet."))

    mono = buffer.mean(axis=1)
    if source_rate != target_sample_rate:
        mono = librosa.resample(mono, orig_sr=source_rate, target_sr=target_sample_rate)
        output_rate = target_sample_rate
    else:
        output_rate = source_rate

    mono = np.clip(mono, -1.0, 1.0)
    max_samples = int((MAX_AUDD_BYTES - 1024) / 2)
    if len(mono) > max_samples:
        mono = mono[:max_samples]

    soundfile.write(destination, mono, output_rate, subtype="PCM_16")

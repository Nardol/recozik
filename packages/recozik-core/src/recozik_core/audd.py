"""AudD fallback integration helpers."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import requests
import soundfile

from .fingerprint import AcoustIDMatch, ReleaseInfo
from .i18n import _

DEFAULT_ENDPOINT = "https://api.audd.io/"
ENTERPRISE_ENDPOINT = "https://enterprise.audd.io/"
MAX_AUDD_BYTES = 10 * 1024 * 1024
MAX_AUDD_ENTERPRISE_BYTES = 1024 * 1024 * 1024
SNIPPET_DURATION_SECONDS = 12.0
SNIPPET_OFFSET_SECONDS = 0.0
_AUDD_TARGET_SAMPLE_RATE = 16_000
_AUDD_SNIPPET_SUFFIX = ".wav"
_TOKEN_PATTERN = re.compile(r"(?i)(['\"]?api_token['\"]?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^&\s]+)")
_REDACTED_VALUE = "***redacted***"


def _redact_audd_token(text: str | Any) -> str:
    """Mask occurrences of the AudD token in diagnostic messages."""
    if text is None:
        return ""
    message = str(text)

    def _replacement(match: re.Match[str]) -> str:
        prefix = match.group(1)
        value = match.group(2)
        if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
            return f"{prefix}{value[0]}{_REDACTED_VALUE}{value[-1]}"
        return f"{prefix}{_REDACTED_VALUE}"

    return _TOKEN_PATTERN.sub(_replacement, message)


class AudDLookupError(RuntimeError):
    """Raised when the AudD API request fails."""


class AudDMode(str, Enum):
    """Execution mode for AudD lookups."""

    STANDARD = "standard"
    ENTERPRISE = "enterprise"
    AUTO = "auto"


@dataclass(slots=True)
class AudDEnterpriseParams:
    """Parameters specific to the AudD Enterprise endpoint."""

    skip: tuple[int, ...] = ()
    every: float | None = None
    limit: int | None = None
    skip_first_seconds: float | None = None
    accurate_offsets: bool = False
    use_timecode: bool = False


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


@dataclass(slots=True)
class SnippetInfo:
    """Metadata collected while preparing the AudD snippet."""

    offset_seconds: float
    duration_seconds: float
    rms: float


def recognize_with_audd(
    api_token: str,
    audio_path: Path,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 20.0,
    use_enterprise: bool = False,
    enterprise_params: AudDEnterpriseParams | None = None,
    snippet_offset: float | None = None,
    snippet_hook: Callable[[SnippetInfo], None] | None = None,
) -> list[AcoustIDMatch]:
    """Send an identification request to AudD and normalize results."""
    if not api_token:
        raise AudDLookupError(_("No AudD token provided."))
    if not audio_path.is_file():
        raise AudDLookupError(_("Audio file not found: {path}").format(path=audio_path))

    if use_enterprise:
        return _recognize_with_enterprise(
            api_token,
            audio_path,
            endpoint=endpoint or ENTERPRISE_ENDPOINT,
            timeout=timeout,
            enterprise_params=enterprise_params or AudDEnterpriseParams(),
        )

    offset_value = (
        SNIPPET_OFFSET_SECONDS if snippet_offset is None else max(0.0, float(snippet_offset))
    )
    try:
        payload_manager = _prepare_audd_payload(audio_path, snippet_offset=offset_value)
    except AudDLookupError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        message = _redact_audd_token(
            _("Unable to prepare audio for AudD: {error}").format(error=exc)
        )
        raise AudDLookupError(message) from exc

    with payload_manager as payload_data:
        payload_path, snippet_info = payload_data
        if snippet_hook is not None:
            with suppress(Exception):  # pragma: no cover - user-defined hook errors
                snippet_hook(snippet_info)
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
            message = _redact_audd_token(_("AudD request failed: {error}").format(error=exc))
            raise AudDLookupError(message) from exc

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


def _recognize_with_enterprise(
    api_token: str,
    audio_path: Path,
    *,
    endpoint: str,
    timeout: float,
    enterprise_params: AudDEnterpriseParams,
) -> list[AcoustIDMatch]:
    """Send an identification request through the AudD Enterprise endpoint."""
    if not endpoint:
        endpoint = ENTERPRISE_ENDPOINT

    try:
        size = audio_path.stat().st_size
    except OSError as exc:  # pragma: no cover - filesystem failures
        message = _redact_audd_token(_("Unable to access audio file: {error}").format(error=exc))
        raise AudDLookupError(message) from exc

    if size > MAX_AUDD_ENTERPRISE_BYTES:
        raise AudDLookupError(
            _("AudD enterprise upload exceeds {limit} bytes (got {size}).").format(
                limit=MAX_AUDD_ENTERPRISE_BYTES,
                size=size,
            )
        )

    data: dict[str, Any] = {
        "api_token": api_token,
        "return": "apple_music,spotify,deezer",
    }
    _apply_enterprise_params(data, enterprise_params)

    try:
        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "application/octet-stream")}
            response = requests.post(endpoint, data=data, files=files, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - network failures
        message = _redact_audd_token(_("AudD request failed: {error}").format(error=exc))
        raise AudDLookupError(message) from exc

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


def _apply_enterprise_params(
    payload: dict[str, Any],
    params: AudDEnterpriseParams,
) -> None:
    """Attach optional enterprise parameters to the request payload."""
    if params.skip:
        payload["skip"] = ",".join(str(int(value)) for value in params.skip)
    if params.every is not None:
        payload["every"] = str(params.every)
    if params.limit is not None:
        payload["limit"] = str(int(params.limit))
    if params.skip_first_seconds is not None:
        payload["skip_first_seconds"] = str(params.skip_first_seconds)
    if params.accurate_offsets:
        payload["accurate_offsets"] = "1"
    if params.use_timecode:
        payload["use_timecode"] = "1"


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
            return _redact_audd_token(message)
    if isinstance(error, str):
        return _redact_audd_token(error)
    result = payload.get("result")
    if isinstance(result, str):
        return _redact_audd_token(result)
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


def needs_audd_snippet(audio_path: Path, *, max_bytes: int | None = None) -> bool:
    """Return True when the audio file exceeds AudD's upload size limit."""
    limit = MAX_AUDD_BYTES if max_bytes is None else max_bytes
    try:
        return audio_path.stat().st_size > limit
    except OSError as exc:  # pragma: no cover - filesystem failures
        message = _redact_audd_token(_("Unable to access audio file: {error}").format(error=exc))
        raise AudDLookupError(message) from exc


@contextmanager
def _prepare_audd_payload(
    audio_path: Path,
    *,
    max_bytes: int | None = None,
    snippet_offset: float = SNIPPET_OFFSET_SECONDS,
) -> Iterator[tuple[Path, SnippetInfo]]:
    """Return a context manager yielding the snippet metadata and path to upload to AudD."""
    limit = MAX_AUDD_BYTES if max_bytes is None else max_bytes
    fd, raw_path = tempfile.mkstemp(prefix="recozik-audd-", suffix=_AUDD_SNIPPET_SUFFIX)
    try:
        os.close(fd)
    except OSError:
        pass
    snippet_path = Path(raw_path)
    try:
        info = _render_snippet(
            audio_path,
            snippet_path,
            snippet_seconds=SNIPPET_DURATION_SECONDS,
            target_sample_rate=_AUDD_TARGET_SAMPLE_RATE,
            snippet_offset=snippet_offset,
        )
        size = snippet_path.stat().st_size
        if size > limit:
            raise AudDLookupError(
                _("AudD snippet still exceeds {limit} bytes (got {size}).").format(
                    limit=limit,
                    size=size,
                )
            )
        yield snippet_path, info
    finally:
        snippet_path.unlink(missing_ok=True)


def _render_snippet(
    audio_path: Path,
    destination: Path,
    *,
    snippet_seconds: float = SNIPPET_DURATION_SECONDS,
    target_sample_rate: int = _AUDD_TARGET_SAMPLE_RATE,
    snippet_offset: float = SNIPPET_OFFSET_SECONDS,
) -> SnippetInfo:
    """Render a mono PCM snippet suitable for AudD uploads and return metrics."""
    offset_seconds = max(0.0, float(snippet_offset))
    ffmpeg_ready = _ffmpeg_support_ready()
    prefer_ffmpeg = _should_prefer_ffmpeg(audio_path) and ffmpeg_ready

    ffmpeg_error: AudDLookupError | None = None
    soundfile_error: Exception | None = None
    tried_ffmpeg = False

    if prefer_ffmpeg:
        tried_ffmpeg = True
        try:
            _render_snippet_with_ffmpeg(
                audio_path,
                destination,
                snippet_seconds=snippet_seconds,
                target_sample_rate=target_sample_rate,
                snippet_offset=offset_seconds,
            )
            analysis = _analyse_snippet(destination)
            return SnippetInfo(
                offset_seconds=offset_seconds,
                duration_seconds=analysis[0],
                rms=analysis[1],
            )
        except AudDLookupError as exc:
            ffmpeg_error = exc

    try:
        _render_snippet_with_soundfile(
            audio_path,
            destination,
            snippet_seconds=snippet_seconds,
            target_sample_rate=target_sample_rate,
            snippet_offset=offset_seconds,
        )
        analysis = _analyse_snippet(destination)
        return SnippetInfo(
            offset_seconds=offset_seconds,
            duration_seconds=analysis[0],
            rms=analysis[1],
        )
    except AudDLookupError:
        raise
    except Exception as exc:
        soundfile_error = exc

    if not tried_ffmpeg and ffmpeg_ready:
        tried_ffmpeg = True
        try:
            _render_snippet_with_ffmpeg(
                audio_path,
                destination,
                snippet_seconds=snippet_seconds,
                target_sample_rate=target_sample_rate,
                snippet_offset=offset_seconds,
            )
            analysis = _analyse_snippet(destination)
            return SnippetInfo(
                offset_seconds=offset_seconds,
                duration_seconds=analysis[0],
                rms=analysis[1],
            )
        except AudDLookupError as exc:
            ffmpeg_error = exc

    messages: list[str] = []
    if soundfile_error is not None:
        messages.append(str(soundfile_error))
    if ffmpeg_error is not None:
        messages.append(str(ffmpeg_error))

    if messages:
        details = "; ".join(messages)
    else:
        details = "unknown error"

    message = _redact_audd_token(
        _("Failed to read audio for AudD snippet: {error}").format(error=details)
    )
    raise AudDLookupError(message)


def _render_snippet_with_soundfile(
    audio_path: Path,
    destination: Path,
    *,
    snippet_seconds: float,
    target_sample_rate: int,
    snippet_offset: float,
) -> None:
    """Try to render the AudD snippet via libsndfile/librosa."""
    try:
        import librosa
    except Exception as exc:  # pragma: no cover - dependency missing
        message = _redact_audd_token(
            _("AudD snippet generation requires librosa: {error}").format(error=exc)
        )
        raise RuntimeError(message) from exc

    try:
        with soundfile.SoundFile(audio_path, "r") as source:
            source_frames = source.frames
            source_rate = source.samplerate
            start_frame = int(min(max(snippet_offset * source_rate, 0.0), float(source_frames)))
            if start_frame >= source_frames:
                raise AudDLookupError(
                    _(
                        "Audio file is shorter than the requested AudD snippet offset ({offset}s)."
                    ).format(offset=snippet_offset)
                )
            duration_frames = min(
                int(snippet_seconds * source_rate),
                max(source_frames - start_frame, 0),
            )
            if duration_frames <= 0:
                raise AudDLookupError(_("Audio file is empty."))
            source.seek(start_frame)
            buffer = source.read(duration_frames, dtype="float32", always_2d=True)
    except RuntimeError as exc:
        message = _redact_audd_token(
            _("Failed to read audio for AudD snippet: {error}").format(error=exc)
        )
        raise RuntimeError(message) from exc

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


def _render_snippet_with_ffmpeg(
    audio_path: Path,
    destination: Path,
    *,
    snippet_seconds: float,
    target_sample_rate: int,
    snippet_offset: float,
) -> None:
    """Render the AudD snippet via ffmpeg when libsndfile cannot decode the file."""
    ffmpeg_executable = shutil.which("ffmpeg")
    if not ffmpeg_executable:
        raise AudDLookupError(
            _("FFmpeg executable not found. Install ffmpeg to enable AudD fallback.")
        )

    try:  # pragma: no cover - optional dependency
        import ffmpeg  # type: ignore
    except Exception as exc:
        message = _redact_audd_token(
            _(
                "FFmpeg Python bindings are missing. Install recozik[ffmpeg-support]: {error}"
            ).format(error=exc)
        )
        raise AudDLookupError(message) from exc

    try:
        input_kwargs: dict[str, float] = {}
        if snippet_offset > 0.0:
            input_kwargs["ss"] = snippet_offset
        (
            ffmpeg.input(str(audio_path), **input_kwargs)
            .output(
                str(destination),
                ac=1,
                ar=target_sample_rate,
                t=snippet_seconds,
                format="wav",
            )
            .overwrite_output()
            .global_args("-loglevel", "error")
            .run(cmd=ffmpeg_executable, capture_stdout=True, capture_stderr=True)  # type: ignore[call-arg]
        )
    except ffmpeg.Error as exc:  # type: ignore[attr-defined]
        stderr = ""
        if getattr(exc, "stderr", b""):
            try:
                stderr = exc.stderr.decode("utf-8", "ignore")
            except Exception:  # pragma: no cover - defensive
                stderr = str(exc)
        else:
            stderr = str(exc)
        message = _redact_audd_token(
            _("FFmpeg failed to render AudD snippet: {error}").format(error=stderr)
        )
        raise AudDLookupError(message) from exc

    try:
        size = destination.stat().st_size
    except OSError as exc:  # pragma: no cover - filesystem race
        raise AudDLookupError(
            _("Failed to read audio for AudD snippet: {error}").format(error=exc)
        ) from exc

    if size > MAX_AUDD_BYTES:
        raise AudDLookupError(
            _("AudD snippet still exceeds {limit} bytes (got {size}).").format(
                limit=MAX_AUDD_BYTES,
                size=size,
            )
        )
    if size == 0:
        raise AudDLookupError(_("Failed to read audio for AudD snippet: unknown error"))


def _analyse_snippet(snippet_path: Path) -> tuple[float, float]:
    """Read the rendered snippet and compute duration/RMS metrics."""
    try:
        samples, rate = soundfile.read(snippet_path, dtype="float32")
    except Exception as exc:  # pragma: no cover - defensive path
        message = _redact_audd_token(
            _("Failed to read audio for AudD snippet: {error}").format(error=exc)
        )
        raise AudDLookupError(message) from exc

    if samples.size == 0 or rate <= 0:
        raise AudDLookupError(_("Audio file is empty."))

    if samples.ndim > 1:
        mono = np.mean(samples, axis=1)
    else:
        mono = samples

    duration_seconds = float(len(mono) / rate)
    if duration_seconds <= 0:
        raise AudDLookupError(_("Audio file is empty."))

    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
    return duration_seconds, rms


def _ffmpeg_support_ready() -> bool:
    """Return True when the FFmpeg executable and Python bindings are available."""
    if not shutil.which("ffmpeg"):
        return False
    try:  # pragma: no cover - optional dependency
        import ffmpeg  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


_FFMPEG_PREFERRED_SUFFIXES = {
    ".mp3",
    ".aac",
    ".m4a",
    ".m4b",
    ".ogg",
    ".opus",
    ".wma",
    ".ac3",
    ".amr",
}


def _should_prefer_ffmpeg(audio_path: Path) -> bool:
    """Return True when FFmpeg should be attempted before libsndfile."""
    suffix = audio_path.suffix.lower()
    if suffix in _FFMPEG_PREFERRED_SUFFIXES:
        return True
    return False

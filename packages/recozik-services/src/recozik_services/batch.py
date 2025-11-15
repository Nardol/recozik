"""Service functions powering the `identify-batch` workflow."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from recozik_core.cache import LookupCache
from recozik_core.fingerprint import AcoustIDMatch, FingerprintResult
from recozik_core.i18n import _

from .callbacks import PrintCallbacks, ServiceCallbacks
from .cli_support.metadata import extract_audio_metadata
from .cli_support.musicbrainz import MusicBrainzOptions, MusicBrainzSettings
from .identify import AudDConfig, IdentifyRequest, IdentifyServiceError, identify_track


@dataclass(slots=True)
class BatchFileResult:
    """Structured outcome for a processed file."""

    path: Path
    display_path: str
    fingerprint: FingerprintResult | None
    matches: list[AcoustIDMatch]
    status: str
    note: str | None
    error: str | None
    metadata: dict[str, str] | None


BatchLogConsumer = Callable[[BatchFileResult], None]
PathFormatter = Callable[[Path], str]


@dataclass(slots=True)
class BatchRequest:
    """Parameters required to execute identify-batch."""

    files: Iterable[Path]
    base_directory: Path
    fpcalc_path: Path | None
    api_key: str
    cache_enabled: bool
    cache_ttl_hours: int
    refresh_cache: bool
    audd: AudDConfig
    musicbrainz_options: MusicBrainzOptions
    musicbrainz_settings: MusicBrainzSettings
    metadata_fallback: bool
    limit: int
    best_only: bool
    metadata_extractor: Callable[[Path], dict[str, str] | None] = extract_audio_metadata


@dataclass(slots=True)
class BatchSummary:
    """Aggregated statistics produced by :func:`run_batch_identify`."""

    success: int
    unmatched: int
    failures: int


def _default_callbacks() -> ServiceCallbacks:
    return PrintCallbacks()


def run_batch_identify(
    request: BatchRequest,
    *,
    callbacks: ServiceCallbacks | None = None,
    log_consumer: BatchLogConsumer | None = None,
    path_formatter: PathFormatter | None = None,
    lookup_cache_cls: type[LookupCache] = LookupCache,
    identify_kwargs: dict | None = None,
) -> BatchSummary:
    """Process multiple files using the shared identify service."""
    callbacks = callbacks or _default_callbacks()
    path_formatter = path_formatter or (lambda value: str(value))

    cache = lookup_cache_cls(
        enabled=request.cache_enabled,
        ttl=timedelta(hours=max(request.cache_ttl_hours, 1)),
    )

    success = 0
    unmatched = 0
    failures = 0
    effective_limit = 1 if request.best_only else max(request.limit, 1)

    for file_path in request.files:
        display_path = path_formatter(file_path)
        identify_request = IdentifyRequest(
            audio_path=file_path,
            fpcalc_path=request.fpcalc_path,
            api_key=request.api_key,
            refresh_cache=request.refresh_cache,
            cache_enabled=request.cache_enabled,
            cache_ttl_hours=request.cache_ttl_hours,
            audd=request.audd,
            musicbrainz_options=request.musicbrainz_options,
            musicbrainz_settings=request.musicbrainz_settings,
            metadata_fallback=request.metadata_fallback,
        )
        identify_params = dict(identify_kwargs or {})
        identify_params.setdefault("cache", cache)
        identify_params.setdefault("persist_cache", False)
        identify_params.setdefault("metadata_extractor", request.metadata_extractor)

        try:
            response = identify_track(
                identify_request,
                callbacks=callbacks,
                **identify_params,
            )
        except IdentifyServiceError as exc:
            failures += 1
            if log_consumer:
                log_consumer(
                    BatchFileResult(
                        path=file_path,
                        display_path=display_path,
                        fingerprint=None,
                        matches=[],
                        status="error",
                        note=None,
                        error=str(exc),
                        metadata=None,
                    )
                )
            continue

        if response.match_source == "audd":
            callbacks.info(_("AudD identified {path}.").format(path=display_path))

        if not response.matches:
            unmatched += 1
            unmatched_note_parts = [_("No match.")]
            if response.audd_error:
                unmatched_note_parts.append(
                    _("AudD lookup failed: {error}").format(error=response.audd_error)
                )
            unmatched_note = " ".join(unmatched_note_parts)
            if log_consumer:
                log_consumer(
                    BatchFileResult(
                        path=file_path,
                        display_path=display_path,
                        fingerprint=response.fingerprint,
                        matches=[],
                        status="unmatched",
                        note=unmatched_note,
                        error=None,
                        metadata=response.metadata,
                    )
                )
            continue

        selected = response.matches[:effective_limit]
        success_note_parts: list[str] = []
        if response.match_source == "audd":
            callbacks.info(_("AudD identified {path}.").format(path=display_path))
            success_note_parts.append(response.audd_note or _("Source: AudD."))
        if response.audd_error and response.match_source != "audd":
            success_note_parts.append(
                _("AudD lookup failed: {error}").format(error=response.audd_error)
            )
        success_note: str | None = " ".join(success_note_parts) if success_note_parts else None
        success += 1
        if log_consumer:
            log_consumer(
                BatchFileResult(
                    path=file_path,
                    display_path=display_path,
                    fingerprint=response.fingerprint,
                    matches=selected,
                    status="ok",
                    note=success_note,
                    error=None,
                    metadata=None,
                )
            )

    cache.save()
    return BatchSummary(success=success, unmatched=unmatched, failures=failures)


__all__ = [
    "BatchFileResult",
    "BatchLogConsumer",
    "BatchRequest",
    "BatchSummary",
    "run_batch_identify",
]

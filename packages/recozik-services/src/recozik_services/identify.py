"""Service functions powering the `identify` command."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from recozik_core.audd import AudDEnterpriseParams, AudDMode, SnippetInfo
from recozik_core.cache import LookupCache
from recozik_core.fingerprint import (
    AcoustIDLookupError,
    AcoustIDMatch,
    FingerprintError,
    FingerprintResult,
)
from recozik_core.fingerprint import (
    compute_fingerprint as _compute_fingerprint_impl,
)
from recozik_core.fingerprint import (
    lookup_recordings as _lookup_recordings_impl,
)
from recozik_core.i18n import _
from recozik_core.musicbrainz import MusicBrainzClient, MusicBrainzSettings

from .callbacks import PrintCallbacks, ServiceCallbacks
from .cli_support.audd_helpers import AudDSupport, get_audd_support
from .cli_support.metadata import extract_audio_metadata
from .cli_support.musicbrainz import (
    MusicBrainzOptions,
    enrich_matches_with_musicbrainz,
)
from .security import (
    AccessPolicy,
    AccessPolicyError,
    AllowAllAccessPolicy,
    QuotaPolicy,
    QuotaPolicyError,
    QuotaScope,
    ServiceFeature,
    ServiceUser,
    UnlimitedQuotaPolicy,
)


@dataclass(slots=True)
class AudDConfig:
    """AudD execution parameters for a single identify run."""

    token: str | None
    enabled: bool
    prefer: bool
    endpoint_standard: str
    endpoint_enterprise: str
    mode: AudDMode
    force_enterprise: bool
    enterprise_fallback: bool
    params: AudDEnterpriseParams
    snippet_offset: float | None
    snippet_min_level: float | None


@dataclass(slots=True)
class IdentifyRequest:
    """Inputs required to identify a track."""

    audio_path: Path
    fpcalc_path: Path | None
    api_key: str
    refresh_cache: bool
    cache_enabled: bool
    cache_ttl_hours: int
    audd: AudDConfig
    musicbrainz_options: MusicBrainzOptions
    musicbrainz_settings: MusicBrainzSettings
    metadata_fallback: bool = True


@dataclass(slots=True)
class IdentifyResponse:
    """Outcome returned by :func:`identify_track`."""

    fingerprint: FingerprintResult
    matches: list[AcoustIDMatch]
    match_source: str | None
    metadata: dict[str, str] | None
    audd_note: str | None
    audd_error: str | None


class IdentifyServiceError(RuntimeError):
    """Raised when the identify service cannot complete the lookup."""


def _default_callbacks() -> ServiceCallbacks:
    return PrintCallbacks()


def identify_track(
    request: IdentifyRequest,
    *,
    callbacks: ServiceCallbacks | None = None,
    compute_fingerprint_fn: Callable[..., FingerprintResult] | None = None,
    lookup_recordings_fn: Callable[[str, FingerprintResult], Sequence[AcoustIDMatch]] | None = None,
    fingerprint_error_cls: type[Exception] = FingerprintError,
    acoustid_error_cls: type[Exception] = AcoustIDLookupError,
    lookup_cache_cls: type[LookupCache] = LookupCache,
    metadata_extractor: Callable[[Path], dict[str, str] | None] = extract_audio_metadata,
    audd_support: AudDSupport | None = None,
    cache: LookupCache | None = None,
    persist_cache: bool = True,
    user: ServiceUser | None = None,
    access_policy: AccessPolicy | None = None,
    quota_policy: QuotaPolicy | None = None,
) -> IdentifyResponse:
    """
    Identify an audio file by computing its fingerprint and retrieving matches from AudD or AcoustID, with optional MusicBrainz enrichment, caching, and policy-driven quota/access controls.
    
    Parameters:
        request (IdentifyRequest): Inputs and options for this identification run (audio path, API keys, cache and AudD/musicbrainz settings).
        callbacks (ServiceCallbacks | None): Optional callbacks for progress, info, and warnings; defaults to a print-based implementation.
        compute_fingerprint_fn (Callable[..., FingerprintResult] | None): Optional fingerprinting function; used to produce the fingerprint for the audio file.
        lookup_recordings_fn (Callable[[str, FingerprintResult], Sequence[AcoustIDMatch]] | None): Optional AcoustID lookup function; called when performing AcoustID lookups.
        fingerprint_error_cls (type[Exception]): Exception class raised by the fingerprint function; used to wrap fingerprint errors.
        acoustid_error_cls (type[Exception]): Exception class raised by the AcoustID lookup; used to wrap lookup errors.
        lookup_cache_cls (type[LookupCache]): Cache implementation class used when no cache instance is provided.
        metadata_extractor (Callable[[Path], dict[str, str] | None]): Function to extract fallback metadata from the audio file when no matches are found.
        audd_support (AudDSupport | None): Optional AudD integration provider; used for AudD lookups when enabled.
        cache (LookupCache | None): Optional pre-created cache instance; if None, an instance is created using lookup_cache_cls and request cache settings.
        persist_cache (bool): Whether to persist cache changes before returning.
        user (ServiceUser | None): Optional user context used by access and quota policies; defaults to an anonymous user.
        access_policy (AccessPolicy | None): Optional access control policy; used to enforce feature access for the request.
        quota_policy (QuotaPolicy | None): Optional quota policy; used to consume quotas for lookups and enrichment.
    
    Returns:
        IdentifyResponse: Result object containing the computed fingerprint, a list of matches (possibly empty), the match source ("acoustid" or "audd") when available, optional fallback metadata, and any AudD note or error.
    """
    if callbacks is None:
        callbacks = _default_callbacks()
    if compute_fingerprint_fn is None:
        compute_fingerprint_fn = _compute_fingerprint_impl
    if lookup_recordings_fn is None:
        lookup_recordings_fn = _lookup_recordings_impl
    if audd_support is None:
        audd_support = get_audd_support()

    user = user or ServiceUser.anonymous()
    access_policy = access_policy or AllowAllAccessPolicy()
    quota_policy = quota_policy or UnlimitedQuotaPolicy()

    def _require(feature: ServiceFeature) -> None:
        """
        Ensure the current user is authorized to use the given service feature.
        
        Parameters:
            feature (ServiceFeature): The feature to require for the current request.
        
        Raises:
            IdentifyServiceError: If the access policy denies the feature or an access-check error occurs.
        """
        try:
            access_policy.ensure_feature(user, feature, context={"request": request})
        except AccessPolicyError as exc:  # pragma: no cover - helper wrapper
            raise IdentifyServiceError(str(exc)) from exc

    def _consume(scope: QuotaScope, *, cost: int = 1) -> None:
        """
        Consume quota for the given scope on behalf of the current user and request.
        
        Parameters:
            scope (QuotaScope): The quota scope to consume from (e.g., ACOUSTID_LOOKUP, AUDD_STANDARD_LOOKUP).
            cost (int): The amount of quota units to consume (default 1).
        
        Raises:
            IdentifyServiceError: If the quota policy rejects the consumption.
        """
        try:
            quota_policy.consume(user, scope, cost=cost, context={"request": request})
        except QuotaPolicyError as exc:  # pragma: no cover - helper wrapper
            raise IdentifyServiceError(str(exc)) from exc

    _require(ServiceFeature.IDENTIFY)

    cache_instance = cache or lookup_cache_cls(
        enabled=request.cache_enabled,
        ttl=timedelta(hours=max(request.cache_ttl_hours, 1)),
    )

    try:
        fingerprint = compute_fingerprint_fn(
            request.audio_path,
            fpcalc_path=request.fpcalc_path,
        )
    except fingerprint_error_cls as exc:  # pragma: no cover - delegated to caller
        raise IdentifyServiceError(str(exc)) from exc

    matches: list[AcoustIDMatch] | None = None
    match_source: str | None = None
    audd_note: str | None = None
    audd_error: str | None = None

    if request.cache_enabled and not request.refresh_cache:
        cached = cache_instance.get(fingerprint.fingerprint, fingerprint.duration_seconds)
        if cached is not None:
            matches = list(cached)
            match_source = "acoustid"

    audd_available = bool(request.audd.token) and request.audd.enabled
    musicbrainz_client = None
    if request.musicbrainz_options.enabled:
        _require(ServiceFeature.MUSICBRAINZ_ENRICH)
        musicbrainz_client = MusicBrainzClient(request.musicbrainz_settings)

    def determine_primary_mode() -> AudDMode:
        """
        Selects the primary AudD recognition mode based on the identify request configuration.
        
        If `request.audd.force_enterprise` is true, chooses `AudDMode.ENTERPRISE`. When `request.audd.mode` is `AudDMode.AUTO`, selects `ENTERPRISE` if any enterprise-specific parameters are active (`params.skip`, `params.every` is not None, `params.limit` is not None, `params.skip_first_seconds` is not None, `params.accurate_offsets`, or `params.use_timecode`); otherwise selects `STANDARD`. For any other configured mode, returns that mode unchanged.
        
        Returns:
            AudDMode: `AudDMode.ENTERPRISE` if enterprise is required or AUTO detects enterprise parameters, `AudDMode.STANDARD` if AUTO resolves to standard, otherwise the configured `request.audd.mode`.
        """
        if request.audd.force_enterprise:
            return AudDMode.ENTERPRISE
        if request.audd.mode is AudDMode.AUTO:
            params = request.audd.params
            if (
                params.skip
                or params.every is not None
                or params.limit is not None
                or params.skip_first_seconds is not None
                or params.accurate_offsets
                or params.use_timecode
            ):
                return AudDMode.ENTERPRISE
            return AudDMode.STANDARD
        return request.audd.mode

    def run_audd(will_retry_acoustid: bool) -> list[AcoustIDMatch]:
        """
        Perform an AudD lookup (standard or enterprise) for the current request, with snippet handling and optional fallback.
        
        Performs an AudD recognition attempt using the configured primary AudD mode; if that attempt yields no results and enterprise_fallback is allowed, it will try the alternate mode. Updates the nonlocal variables `audd_note` and `audd_error` to reflect successful use or any error message. When a token is not present, returns an empty list.
        
        Parameters:
            will_retry_acoustid (bool): If true, failure messages will indicate that AcoustID may be tried as a fallback.
        
        Returns:
            list[AcoustIDMatch]: A list of matches returned by AudD, or an empty list if no matches were found or the lookup could not be performed.
        """
        nonlocal audd_note, audd_error
        _require(ServiceFeature.AUDD)
        snippet_announced = False
        snippet_warned = False

        def handle_snippet(info: SnippetInfo) -> None:
            nonlocal snippet_announced, snippet_warned
            display_seconds = int(audd_support.snippet_seconds)
            if not snippet_announced:
                if info.offset_seconds > 0:
                    message = _(
                        "Preparing AudD snippet (~{seconds}s, mono 16 kHz) "
                        "starting at ~{offset}s before upload."
                    ).format(seconds=display_seconds, offset=f"{info.offset_seconds:.2f}")
                    callbacks.info(message)
                else:
                    message = _(
                        "Preparing AudD snippet (~{seconds}s, mono 16 kHz) before upload."
                    ).format(seconds=display_seconds)
                    callbacks.info(message)
                snippet_announced = True

            if (
                request.audd.snippet_min_level is not None
                and info.rms < request.audd.snippet_min_level
                and not snippet_warned
            ):
                warning = _(
                    "AudD snippet RMS is low (~{rms:.4f}); consider adjusting the offset "
                    "or using the enterprise endpoint."
                ).format(rms=info.rms)
                callbacks.warning(warning)
                snippet_warned = True

        def _execute(mode: AudDMode) -> list[AcoustIDMatch]:
            """
            Perform an AudD lookup using the specified mode and return any matches.
            
            Consumes the appropriate quota for the chosen mode, sets the nonlocal
            variables `audd_note` (on success) and `audd_error` (on failure), and may
            emit warnings via the `callbacks` object.
            
            Parameters:
                mode (AudDMode): The AudD execution mode to use (STANDARD or ENTERPRISE).
            
            Returns:
                list[AcoustIDMatch]: Matches returned by AudD, or an empty list if no
                matches were found or an error occurred.
            """
            nonlocal audd_note, audd_error
            token = request.audd.token
            if not token:
                return []
            scope = (
                QuotaScope.AUDD_ENTERPRISE_LOOKUP
                if mode is AudDMode.ENTERPRISE
                else QuotaScope.AUDD_STANDARD_LOOKUP
            )
            _consume(scope)
            if mode is AudDMode.STANDARD:
                try:
                    result = audd_support.recognize_standard(
                        token,
                        request.audio_path,
                        endpoint=request.audd.endpoint_standard,
                        snippet_offset=request.audd.snippet_offset or 0.0,
                        snippet_hook=handle_snippet,
                    )
                    audd_note = _("Source: AudD.")
                    return result
                except audd_support.error_cls as exc:
                    audd_error = str(exc)
                    message = _("AudD lookup failed: {error}.").format(error=exc)
                    if will_retry_acoustid:
                        message = _(
                            "AudD lookup failed: {error}. Falling back to AcoustID."
                        ).format(error=exc)
                    callbacks.warning(message)
                    return []

            try:
                result = audd_support.recognize_enterprise(
                    token,
                    request.audio_path,
                    endpoint=request.audd.endpoint_enterprise,
                    params=request.audd.params,
                )
                audd_note = _("Source: AudD.")
                return result
            except audd_support.error_cls as exc:
                audd_error = str(exc)
                callbacks.warning(_("AudD lookup failed: {error}.").format(error=exc))
                return []

        primary_mode = determine_primary_mode()
        result = _execute(primary_mode)
        if result or not request.audd.enterprise_fallback:
            return result

        secondary_mode = (
            AudDMode.ENTERPRISE if primary_mode is not AudDMode.ENTERPRISE else AudDMode.STANDARD
        )
        if secondary_mode is primary_mode:
            return result
        return _execute(secondary_mode)

    audd_attempted = False

    if audd_available and request.audd.prefer and matches is None:
        audd_attempted = True
        audd_results = run_audd(will_retry_acoustid=True)
        if audd_results:
            matches = audd_results
            match_source = "audd"

    if matches is None:
        _consume(QuotaScope.ACOUSTID_LOOKUP)
        try:
            matches = list(lookup_recordings_fn(request.api_key, fingerprint))
        except acoustid_error_cls as exc:  # pragma: no cover - propagated upstream
            if persist_cache:
                cache_instance.save()
            raise IdentifyServiceError(str(exc)) from exc
        if request.cache_enabled:
            cache_instance.set(
                fingerprint.fingerprint,
                fingerprint.duration_seconds,
                matches,
            )
        match_source = "acoustid" if matches else None
    elif match_source is None:
        match_source = "acoustid"

    if audd_available and not matches and not audd_attempted:
        audd_attempted = True
        audd_results = run_audd(will_retry_acoustid=False)
        if audd_results:
            matches = audd_results
            match_source = "audd"

    if matches:
        if request.musicbrainz_options.enabled:
            _consume(QuotaScope.MUSICBRAINZ_ENRICH)
        enriched = enrich_matches_with_musicbrainz(
            matches,
            options=request.musicbrainz_options,
            settings=request.musicbrainz_settings,
            client=musicbrainz_client,
            echo=callbacks.info,
        )
        if enriched and match_source == "acoustid" and request.cache_enabled:
            cache_instance.set(
                fingerprint.fingerprint,
                fingerprint.duration_seconds,
                matches,
            )

    metadata_payload: dict[str, str] | None = None
    if not matches and request.metadata_fallback and metadata_extractor is not None:
        metadata_payload = metadata_extractor(request.audio_path)

    if persist_cache:
        cache_instance.save()
    return IdentifyResponse(
        fingerprint=fingerprint,
        matches=matches or [],
        match_source=match_source,
        metadata=metadata_payload,
        audd_note=audd_note,
        audd_error=audd_error,
    )


__all__ = [
    "AudDConfig",
    "IdentifyRequest",
    "IdentifyResponse",
    "IdentifyServiceError",
    "identify_track",
]
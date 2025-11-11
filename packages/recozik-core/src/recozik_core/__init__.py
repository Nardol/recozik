"""Core audio fingerprinting, cache, config, and localization helpers for Recozik."""

from .audd import (
    AudDEnterpriseParams,
    AudDLookupError,
    AudDMatch,
    AudDMode,
    SnippetInfo,
    needs_audd_snippet,
    recognize_with_audd,
)
from .cache import LookupCache, default_cache_path
from .config import AppConfig, default_config_path, load_config
from .fingerprint import (
    AcoustIDMatch,
    FingerprintError,
    FingerprintResult,
    ReleaseInfo,
    compute_fingerprint,
    lookup_recordings,
)
from .i18n import (
    _,
    available_locales,
    detect_system_locale,
    get_current_locale,
    gettext,
    ngettext,
    reset_locale,
    resolve_preferred_locale,
    set_locale,
)
from .musicbrainz import (
    MusicBrainzClient,
    MusicBrainzError,
    MusicBrainzRecording,
    MusicBrainzSettings,
    looks_like_mbid,
)

__all__ = [
    "AcoustIDMatch",
    "AppConfig",
    "AudDEnterpriseParams",
    "AudDLookupError",
    "AudDMatch",
    "AudDMode",
    "FingerprintError",
    "FingerprintResult",
    "LookupCache",
    "MusicBrainzClient",
    "MusicBrainzError",
    "MusicBrainzRecording",
    "MusicBrainzSettings",
    "ReleaseInfo",
    "SnippetInfo",
    "_",
    "available_locales",
    "compute_fingerprint",
    "default_cache_path",
    "default_config_path",
    "detect_system_locale",
    "get_current_locale",
    "gettext",
    "load_config",
    "looks_like_mbid",
    "lookup_recordings",
    "needs_audd_snippet",
    "ngettext",
    "recognize_with_audd",
    "reset_locale",
    "resolve_preferred_locale",
    "set_locale",
]

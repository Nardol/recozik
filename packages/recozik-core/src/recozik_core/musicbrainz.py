"""MusicBrainz lookup helpers used by the CLI layer."""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import requests

from .fingerprint import ReleaseInfo
from .i18n import _

_MBID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class MusicBrainzError(RuntimeError):
    """Raised when the MusicBrainz API cannot satisfy a request."""


@dataclass(slots=True)
class MusicBrainzSettings:
    """Connection settings shared by CLI commands."""

    enabled: bool = True
    base_url: str = "https://musicbrainz.org"
    rate_limit_per_second: float = 1.0
    timeout_seconds: float = 5.0
    app_name: str = "recozik"
    app_version: str = "0"
    contact: str | None = None
    cache_size: int = 256
    max_retries: int = 2


@dataclass(slots=True)
class MusicBrainzRecording:
    """Subset of MusicBrainz recording metadata we care about."""

    recording_id: str
    title: str | None
    artist: str | None
    release_group_id: str | None
    release_group_title: str | None
    releases: list[ReleaseInfo] = field(default_factory=list)


def looks_like_mbid(value: str | None) -> bool:
    """Return True if ``value`` matches the MusicBrainz UUID shape."""
    if not value:
        return False
    return bool(_MBID_PATTERN.fullmatch(value.strip()))


class MusicBrainzClient:
    """Thin wrapper around the JSON MusicBrainz API."""

    def __init__(self, settings: MusicBrainzSettings) -> None:
        """Store connection settings and prepare an HTTP session."""
        self._settings = settings
        self._session = requests.Session()
        self._last_request = 0.0
        self._recording_cache: OrderedDict[str, MusicBrainzRecording | None] = OrderedDict()

    def lookup_recording(self, recording_id: str) -> MusicBrainzRecording | None:
        """Return metadata for ``recording_id`` or ``None`` if missing."""
        if not looks_like_mbid(recording_id):
            return None

        if recording_id in self._recording_cache:
            return self._recording_cache[recording_id]

        payload = self._request(
            f"/ws/2/recording/{recording_id}",
            params={
                "fmt": "json",
                "inc": "artists+releases+release-groups",
            },
        )
        if not payload:
            self._store_recording(recording_id, None)
            return None
        record = _parse_recording_payload(payload)
        self._store_recording(recording_id, record)
        return record

    def _request(self, path: str, *, params: dict[str, Any]) -> dict | None:
        base = self._settings.base_url.rstrip("/")
        url = f"{base}{path}"
        attempts = max(0, int(self._settings.max_retries)) + 1
        headers = {
            "User-Agent": _build_user_agent(
                self._settings.app_name,
                self._settings.app_version,
                self._settings.contact,
            ),
            "Accept": "application/json",
        }

        for attempt in range(attempts):
            self._respect_rate_limit()
            try:
                response = self._session.get(
                    url,
                    params=dict(params),
                    headers=headers,
                    timeout=self._settings.timeout_seconds,
                )
            except requests.RequestException as exc:  # pragma: no cover - network issues
                if attempt + 1 >= attempts:
                    raise MusicBrainzError(
                        _("MusicBrainz request failed: {error}").format(error=exc)
                    ) from exc
                self._sleep_before_retry(attempt, None)
                continue

            if response.status_code == 404:
                return None

            error: MusicBrainzError | None = None
            should_retry = False
            if response.status_code == 503:
                error = MusicBrainzError(
                    _("MusicBrainz is temporarily unavailable (503). Please retry later.")
                )
                should_retry = True
            elif response.status_code == 429:
                error = MusicBrainzError(
                    _("MusicBrainz rate limit hit; slow down to stay within 1 request per second.")
                )
                should_retry = True
            elif response.status_code >= 500:
                error = MusicBrainzError(
                    _("Unexpected MusicBrainz response: HTTP {status}").format(
                        status=response.status_code
                    )
                )
                should_retry = True
            elif response.status_code != 200:
                error = MusicBrainzError(
                    _("Unexpected MusicBrainz response: HTTP {status}").format(
                        status=response.status_code
                    )
                )

            if error:
                if should_retry and attempt + 1 < attempts:
                    self._sleep_before_retry(attempt, response)
                    continue
                raise error

            try:
                payload = response.json()
            except ValueError as exc:  # pragma: no cover - defensive
                raise MusicBrainzError(_("Invalid JSON payload returned by MusicBrainz.")) from exc

            if not isinstance(payload, dict):
                raise MusicBrainzError(_("MusicBrainz returned an unexpected payload."))
            return payload

        raise MusicBrainzError(_("MusicBrainz request failed: exceeded retry budget."))

    def _respect_rate_limit(self) -> None:
        delay = 0.0
        if self._settings.rate_limit_per_second > 0:
            delay = max(0.0, 1.0 / self._settings.rate_limit_per_second)
        if delay:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < delay:
                time.sleep(delay - elapsed)
            self._last_request = time.monotonic()

    def _sleep_before_retry(self, attempt: int, response: requests.Response | None) -> None:
        retry_after = 0.0
        if response is not None:
            retry_after = _parse_retry_after(response)
        if retry_after <= 0:
            retry_after = min(2 ** (attempt + 1), 5.0)
        time.sleep(retry_after)

    def _store_recording(self, recording_id: str, record: MusicBrainzRecording | None) -> None:
        cache_size = max(0, int(self._settings.cache_size))
        if cache_size == 0:
            return
        cache = self._recording_cache
        cache[recording_id] = record
        cache.move_to_end(recording_id)
        while len(cache) > cache_size:
            cache.popitem(last=False)


def _build_user_agent(app: str, version: str | None, contact: str | None) -> str:
    app_value = (app or "recozik").strip() or "recozik"
    version_value = (version or "0").strip() or "0"
    contact_value = (contact or "").strip()
    if contact_value:
        return f"{app_value}/{version_value} ({contact_value})"
    return f"{app_value}/{version_value}"


def _parse_recording_payload(payload: dict[str, Any]) -> MusicBrainzRecording:
    recording_id = _safe_str(payload.get("id")) or ""
    title = _safe_str(payload.get("title"))
    artist = _render_artist_credit(payload.get("artist-credit") or payload.get("artist_credit"))
    releases_payload = payload.get("releases") or []
    release_group_id = None
    release_group_title = None
    releases: list[ReleaseInfo] = []

    if isinstance(releases_payload, list):
        for release in releases_payload:
            if not isinstance(release, dict):
                continue
            release_id = _safe_str(release.get("id"))
            release_title = _safe_str(release.get("title"))
            release_date = _safe_str(release.get("date") or release.get("first-release-date"))
            country = _safe_str(release.get("country"))
            releases.append(
                ReleaseInfo(
                    title=release_title,
                    release_id=release_id,
                    date=release_date,
                    country=country,
                )
            )
            if not release_group_id:
                group = release.get("release-group") or release.get("release_group")
                if isinstance(group, dict):
                    release_group_id = _safe_str(group.get("id"))
                    release_group_title = _safe_str(group.get("title"))

    if not release_group_id:
        group = payload.get("release-group") or payload.get("release_group")
        if isinstance(group, dict):
            release_group_id = _safe_str(group.get("id"))
            release_group_title = _safe_str(group.get("title"))

    return MusicBrainzRecording(
        recording_id=recording_id,
        title=title,
        artist=artist,
        release_group_id=release_group_id,
        release_group_title=release_group_title,
        releases=releases,
    )


def _render_artist_credit(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    buffer: list[str] = []
    for item in value:
        if isinstance(item, str):
            buffer.append(item)
            continue
        if not isinstance(item, dict):
            continue
        joinphrase = _safe_str(item.get("joinphrase")) or ""
        name = None
        artist = item.get("artist")
        if isinstance(artist, dict):
            name = _safe_str(artist.get("name"))
        if not name:
            name = _safe_str(item.get("name"))
        if name:
            buffer.append(f"{name}{joinphrase}")
    text = "".join(buffer).strip()
    return text or None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_retry_after(response: requests.Response) -> float:
    header = response.headers.get("Retry-After")
    if not header:
        return 0.0
    try:
        value = float(header)
    except ValueError:
        return 0.0
    if value < 0:
        return 0.0
    return value


__all__ = [
    "MusicBrainzClient",
    "MusicBrainzError",
    "MusicBrainzRecording",
    "MusicBrainzSettings",
    "looks_like_mbid",
]

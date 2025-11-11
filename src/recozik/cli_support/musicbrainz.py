"""Shared helpers to enrich matches with MusicBrainz metadata."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from recozik_core.fingerprint import AcoustIDMatch, ReleaseInfo
from recozik_core.musicbrainz import (
    MusicBrainzClient,
    MusicBrainzError,
    MusicBrainzRecording,
    MusicBrainzSettings,
    looks_like_mbid,
)

EchoFn = Callable[[str], None]


@dataclass(frozen=True)
class MusicBrainzOptions:
    """Runtime toggles derived from config + CLI overrides."""

    enabled: bool
    enrich_missing_only: bool


def build_settings(
    *,
    app_name: str,
    app_version: str,
    contact: str | None,
    rate_limit_per_second: float,
    timeout_seconds: float,
) -> MusicBrainzSettings:
    """Return reusable settings for the lightweight MusicBrainz client."""
    return MusicBrainzSettings(
        enabled=True,
        app_name=app_name or "recozik",
        app_version=app_version or "0",
        contact=contact,
        rate_limit_per_second=max(rate_limit_per_second, 0.0),
        timeout_seconds=max(timeout_seconds, 0.1),
    )


def enrich_matches_with_musicbrainz(
    matches: Iterable[AcoustIDMatch],
    *,
    options: MusicBrainzOptions,
    settings: MusicBrainzSettings,
    client: MusicBrainzClient | None = None,
    echo: EchoFn | None = None,
) -> bool:
    """Mutate matches in-place when MusicBrainz can fill missing fields."""
    if not options.enabled:
        return False

    matches = list(matches)
    if not matches:
        return False

    musicbrainz_client = client or MusicBrainzClient(settings)
    cache: dict[str, MusicBrainzRecording | None] = {}
    enriched = False

    def _warn(message: str) -> None:
        if echo:
            echo(message)

    for match in matches:
        recording_id = _recording_candidate(match)
        if not recording_id:
            continue
        if (
            options.enrich_missing_only
            and match.artist
            and match.title
            and match.release_group_title
        ):
            continue
        if recording_id not in cache:
            try:
                cache[recording_id] = musicbrainz_client.lookup_recording(recording_id)
            except MusicBrainzError as exc:
                _warn(str(exc))
                cache[recording_id] = None
        record = cache.get(recording_id)
        if not record:
            continue
        if _apply_recording(match, record):
            enriched = True

    return enriched


def _recording_candidate(match: AcoustIDMatch) -> str | None:
    identifier = (match.recording_id or "").strip()
    if looks_like_mbid(identifier):
        return identifier
    return None


def _apply_recording(match: AcoustIDMatch, record: MusicBrainzRecording) -> bool:
    changed = False

    if not match.title and record.title:
        match.title = record.title
        changed = True
    if not match.artist and record.artist:
        match.artist = record.artist
        changed = True
    if not match.release_group_id and record.release_group_id:
        match.release_group_id = record.release_group_id
        changed = True
    if not match.release_group_title and record.release_group_title:
        match.release_group_title = record.release_group_title
        changed = True

    if record.releases:
        if _merge_release_info(match.releases, record.releases):
            changed = True

    return changed


def _merge_release_info(target: list[ReleaseInfo], source: list[ReleaseInfo]) -> bool:
    updated = False
    seen = {(item.release_id, item.title, item.date, item.country) for item in target}
    for release in source:
        fingerprint = (release.release_id, release.title, release.date, release.country)
        if fingerprint in seen:
            continue
        target.append(release)
        seen.add(fingerprint)
        updated = True
    return updated


__all__ = [
    "MusicBrainzOptions",
    "build_settings",
    "enrich_matches_with_musicbrainz",
]

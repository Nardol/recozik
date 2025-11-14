"""Service-layer unit tests for Recozik."""

import json
from dataclasses import replace
from pathlib import Path

from recozik_services.batch import BatchRequest, run_batch_identify
from recozik_services.cli_support.musicbrainz import MusicBrainzOptions, build_settings
from recozik_services.identify import AudDConfig, IdentifyRequest, identify_track
from recozik_services.rename import RenamePrompts, RenameRequest, rename_from_log

from recozik_core.audd import AudDEnterpriseParams, AudDMode
from recozik_core.fingerprint import AcoustIDMatch, FingerprintResult, ReleaseInfo


class DummyPrompts(RenamePrompts):
    """Prompt stub returning static answers for rename tests."""

    def yes_no(self, message: str, *, default: bool = True, require_answer: bool = False) -> bool:
        """Return True to accept actions."""
        return True

    def select_match(self, matches, source_path):
        """Select the first match."""
        return 0

    def interactive_interrupt_decision(self, has_planned: bool) -> str:
        """Simulate resuming interactive prompts."""
        return "resume"

    def rename_interrupt_decision(self, remaining: int) -> str:
        """Continue renaming when interrupts happen."""
        return "continue"


class FakeAudDSupport:
    """Minimal AudD support stub used for identify service tests."""

    snippet_seconds = 12.0
    error_cls = RuntimeError

    def __init__(self, matches):
        """Store matches returned by `recognize_*` helpers."""
        self._matches = matches

    def recognize_standard(self, *args, **kwargs):
        """Return canned matches for the standard endpoint."""
        return list(self._matches)

    def recognize_enterprise(self, *args, **kwargs):
        """Return no match for the enterprise endpoint."""
        return []


def _identify_request(tmp_path: Path) -> IdentifyRequest:
    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"data")
    audd_config = AudDConfig(
        token=None,
        enabled=False,
        prefer=False,
        endpoint_standard="",
        endpoint_enterprise="",
        mode=AudDMode.STANDARD,
        force_enterprise=False,
        enterprise_fallback=False,
        params=AudDEnterpriseParams(),
        snippet_offset=None,
        snippet_min_level=None,
    )
    options = IdentifyRequest(
        audio_path=audio_file,
        fpcalc_path=None,
        api_key="test",
        refresh_cache=False,
        cache_enabled=False,
        cache_ttl_hours=1,
        audd=audd_config,
        musicbrainz_options=MusicBrainzOptions(enabled=False, enrich_missing_only=True),
        musicbrainz_settings=build_settings(
            app_name="recozik",
            app_version="0",
            contact=None,
            rate_limit_per_second=1.0,
            timeout_seconds=5.0,
            cache_size=0,
            max_retries=0,
        ),
        metadata_fallback=True,
    )
    return options


def test_identify_service_prefers_lookup(tmp_path):
    """Use AcoustID results when matches exist."""
    request = _identify_request(tmp_path)

    fp_result = FingerprintResult(fingerprint="abc", duration_seconds=120.0)
    match = AcoustIDMatch(
        score=0.9,
        recording_id="rec",
        title="Title",
        artist="Artist",
        release_group_id=None,
        release_group_title=None,
        releases=[ReleaseInfo(title="Album", release_id="id", date=None, country=None)],
    )
    response = identify_track(
        request,
        compute_fingerprint_fn=lambda *args, **kwargs: fp_result,
        lookup_recordings_fn=lambda api_key, fp: [match],
    )

    assert response.matches[0].title == "Title"
    assert response.match_source == "acoustid"


def test_identify_service_metadata_fallback(tmp_path):
    """Return metadata payload when no matches are found."""
    request = _identify_request(tmp_path)

    fp_result = FingerprintResult(fingerprint="abc", duration_seconds=120.0)
    response = identify_track(
        request,
        compute_fingerprint_fn=lambda *args, **kwargs: fp_result,
        lookup_recordings_fn=lambda api_key, fp: [],
        metadata_extractor=lambda path: {"artist": "Meta", "title": "Track"},
    )

    assert response.matches == []
    assert response.metadata == {"artist": "Meta", "title": "Track"}


def test_identify_service_prefers_audd(tmp_path):
    """Ensure AudD results populate the identify response."""
    request = _identify_request(tmp_path)
    audd_config = replace(
        request.audd,
        token="token",  # noqa: S106 - test stub
        enabled=True,
        prefer=True,
    )
    request = replace(request, audd=audd_config)

    fp_result = FingerprintResult(fingerprint="abc", duration_seconds=120.0)
    audd_match = AcoustIDMatch(
        score=0.95,
        recording_id="audd",
        title="AudD Track",
        artist="AudD Artist",
        release_group_id=None,
        release_group_title=None,
        releases=[],
    )
    fake_support = FakeAudDSupport([audd_match])

    response = identify_track(
        request,
        compute_fingerprint_fn=lambda *args, **kwargs: fp_result,
        lookup_recordings_fn=lambda api_key, fp: [],
        audd_support=fake_support,
    )

    assert response.match_source == "audd"
    assert response.matches[0].recording_id == "audd"


def test_batch_service_invokes_log_consumer(tmp_path):
    """Confirm batch runner emits entries through the log consumer."""
    files = []
    for name in ("a.wav", "b.wav"):
        path = tmp_path / name
        path.write_bytes(b"data")
        files.append(path)

    audd_config = AudDConfig(
        token=None,
        enabled=False,
        prefer=False,
        endpoint_standard="",
        endpoint_enterprise="",
        mode=AudDMode.STANDARD,
        force_enterprise=False,
        enterprise_fallback=False,
        params=AudDEnterpriseParams(),
        snippet_offset=None,
        snippet_min_level=None,
    )

    batch_request = BatchRequest(
        files=files,
        base_directory=tmp_path,
        fpcalc_path=None,
        api_key="key",
        cache_enabled=False,
        cache_ttl_hours=1,
        refresh_cache=False,
        audd=audd_config,
        musicbrainz_options=MusicBrainzOptions(enabled=False, enrich_missing_only=True),
        musicbrainz_settings=build_settings(
            app_name="recozik",
            app_version="0",
            contact=None,
            rate_limit_per_second=1.0,
            timeout_seconds=5.0,
            cache_size=0,
            max_retries=0,
        ),
        metadata_fallback=False,
        limit=1,
        best_only=False,
    )

    entries = []

    def fake_lookup(api_key, fp):
        match = AcoustIDMatch(
            score=0.8,
            recording_id="rec",
            title="Title",
            artist="Artist",
            release_group_id=None,
            release_group_title=None,
            releases=[],
        )
        return [match]

    summary = run_batch_identify(
        batch_request,
        callbacks=None,
        log_consumer=lambda entry: entries.append(entry),
        path_formatter=lambda path: path.name,
        identify_kwargs={
            "compute_fingerprint_fn": lambda *args, **kwargs: FingerprintResult("abc", 10.0),
            "lookup_recordings_fn": fake_lookup,
        },
    )

    assert summary.success == 2
    assert len(entries) == 2
    assert entries[0].matches


def test_batch_service_best_only_and_metadata(tmp_path):
    """Batch runner should respect best_only and metadata fallback settings."""
    files = []
    for name in ("match.wav", "meta.wav"):
        path = tmp_path / name
        path.write_bytes(b"data")
        files.append(path)

    audd_config = AudDConfig(
        token=None,
        enabled=False,
        prefer=False,
        endpoint_standard="",
        endpoint_enterprise="",
        mode=AudDMode.STANDARD,
        force_enterprise=False,
        enterprise_fallback=False,
        params=AudDEnterpriseParams(),
        snippet_offset=None,
        snippet_min_level=None,
    )

    batch_request = BatchRequest(
        files=files,
        base_directory=tmp_path,
        fpcalc_path=None,
        api_key="key",
        cache_enabled=False,
        cache_ttl_hours=1,
        refresh_cache=False,
        audd=audd_config,
        musicbrainz_options=MusicBrainzOptions(enabled=False, enrich_missing_only=True),
        musicbrainz_settings=build_settings(
            app_name="recozik",
            app_version="0",
            contact=None,
            rate_limit_per_second=1.0,
            timeout_seconds=5.0,
            cache_size=0,
            max_retries=0,
        ),
        metadata_fallback=True,
        limit=2,
        best_only=True,
        metadata_extractor=lambda path: {"artist": "Meta", "title": "Fallback"}
        if path.name == "meta.wav"
        else None,
    )

    log_entries = []

    def compute(path: Path, fpcalc_path=None):
        return FingerprintResult(fingerprint=path.name, duration_seconds=10.0)

    def lookup(api_key, fp):
        if fp.fingerprint == "match.wav":
            return [
                AcoustIDMatch(
                    score=0.9,
                    recording_id="rec1",
                    title="First",
                    artist="Artist",
                    release_group_id=None,
                    release_group_title=None,
                    releases=[],
                ),
                AcoustIDMatch(
                    score=0.8,
                    recording_id="rec2",
                    title="Second",
                    artist="Artist",
                    release_group_id=None,
                    release_group_title=None,
                    releases=[],
                ),
            ]
        return []

    summary = run_batch_identify(
        batch_request,
        callbacks=None,
        log_consumer=lambda entry: log_entries.append(entry),
        path_formatter=lambda path: path.name,
        identify_kwargs={
            "compute_fingerprint_fn": compute,
            "lookup_recordings_fn": lookup,
        },
    )

    assert summary.success == 1
    assert summary.unmatched == 1
    match_entry = next(entry for entry in log_entries if entry.display_path == "match.wav")
    assert len(match_entry.matches) == 1  # best_only truncates to 1
    meta_entry = next(entry for entry in log_entries if entry.display_path == "meta.wav")
    assert meta_entry.status == "unmatched"
    assert meta_entry.metadata and meta_entry.metadata["artist"] == "Meta"


def test_rename_service_applies_changes(tmp_path):
    """Rename service should move files and emit an export summary."""
    root = tmp_path / "music"
    root.mkdir()
    audio = root / "track.flac"
    audio.write_bytes(b"data")

    log_file = tmp_path / "log.jsonl"
    log_entry = {
        "path": "track.flac",
        "status": "ok",
        "matches": [
            {
                "artist": "Artist",
                "title": "Song",
                "score": 0.9,
                "formatted": "Artist - Song.flac",
            }
        ],
    }
    log_file.write_text(json.dumps(log_entry) + "\n", encoding="utf-8")

    request = RenameRequest(
        log_path=log_file,
        root=root,
        template="{artist} - {title}",
        require_template_fields=False,
        dry_run=False,
        interactive=False,
        confirm_each=False,
        on_conflict="append",
        backup_dir=None,
        export_path=tmp_path / "summary.json",
        metadata_fallback=False,
        metadata_fallback_confirm=False,
        deduplicate_template=True,
    )

    summary = rename_from_log(request, prompts=DummyPrompts())

    assert summary.applied == 1
    assert (root / "Artist - Song.flac").exists()
    assert summary.export_path is not None and summary.export_path.exists()


def test_rename_service_dry_run_plan_reuse(tmp_path):
    """Dry-run plans can be replayed without recomputing decisions."""
    root = tmp_path / "music"
    root.mkdir()
    audio = root / "track.flac"
    audio.write_bytes(b"data")

    log_file = tmp_path / "log.jsonl"
    log_entry = {
        "path": "track.flac",
        "status": "ok",
        "matches": [
            {
                "artist": "Artist",
                "title": "Song",
                "score": 0.9,
                "formatted": "Artist - Song.flac",
            }
        ],
    }
    log_file.write_text(json.dumps(log_entry) + "\n", encoding="utf-8")

    request = RenameRequest(
        log_path=log_file,
        root=root,
        template="{artist} - {title}",
        require_template_fields=False,
        dry_run=True,
        interactive=False,
        confirm_each=False,
        on_conflict="append",
        backup_dir=None,
        export_path=None,
        metadata_fallback=False,
        metadata_fallback_confirm=False,
        deduplicate_template=True,
    )

    dry_summary = rename_from_log(request, prompts=DummyPrompts())
    assert dry_summary.plan_entries

    apply_request = replace(
        request,
        dry_run=False,
        preplanned_entries=dry_summary.plan_entries,
    )
    final_summary = rename_from_log(apply_request, prompts=DummyPrompts())

    assert final_summary.applied == 1
    assert (root / "Artist - Song.flac").exists()
    assert final_summary.plan_entries is None


def test_rename_service_creates_backup(tmp_path):
    """Backups should be written when a directory is provided."""
    root = tmp_path / "music"
    root.mkdir()
    audio = root / "track.flac"
    audio.write_bytes(b"data")

    log_file = tmp_path / "log.jsonl"
    log_entry = {
        "path": "track.flac",
        "status": "ok",
        "matches": [
            {
                "artist": "Artist",
                "title": "Song",
                "score": 0.9,
                "formatted": "Artist - Song.flac",
            }
        ],
    }
    log_file.write_text(json.dumps(log_entry) + "\n", encoding="utf-8")

    backup_dir = tmp_path / "backup"

    request = RenameRequest(
        log_path=log_file,
        root=root,
        template="{artist} - {title}",
        require_template_fields=False,
        dry_run=False,
        interactive=False,
        confirm_each=False,
        on_conflict="append",
        backup_dir=backup_dir,
        export_path=None,
        metadata_fallback=False,
        metadata_fallback_confirm=False,
        deduplicate_template=True,
    )

    summary = rename_from_log(request, prompts=DummyPrompts())

    assert summary.applied == 1
    assert (backup_dir / "track.flac").exists()

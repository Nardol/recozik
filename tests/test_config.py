"""Tests for configuration file helpers."""

from __future__ import annotations

from pathlib import Path

from recozik.config import AppConfig, load_config, write_config

TEST_AUDD_TOKEN = "recozik-test-token"  # noqa: S105


def test_write_and_load_config(tmp_path: Path) -> None:
    """Persist a configuration object and load it back."""
    target = tmp_path / "config.toml"

    config = AppConfig(
        acoustid_api_key="abcd1234",
        cache_enabled=False,
        cache_ttl_hours=12,
        output_template="{artist} - {title} ({score:.2f})",
        log_format="jsonl",
        log_absolute_paths=True,
        metadata_fallback_enabled=False,
        rename_require_template_fields=True,
        rename_default_mode="apply",
        rename_default_interactive=True,
        rename_default_confirm_each=True,
        rename_conflict_strategy="overwrite",
        rename_metadata_confirm=False,
        rename_deduplicate_template=False,
        identify_default_limit=5,
        identify_output_json=True,
        identify_refresh_cache=True,
        identify_audd_enabled=False,
        identify_audd_prefer=True,
        identify_batch_limit=4,
        identify_batch_best_only=True,
        identify_batch_recursive=True,
        identify_batch_log_file="logs/default.jsonl",
        identify_batch_audd_enabled=False,
        identify_batch_audd_prefer=True,
    )

    write_config(config, target)

    loaded = load_config(target)

    assert loaded.acoustid_api_key == "abcd1234"
    assert loaded.audd_api_token is None
    assert loaded.cache_enabled is False
    assert loaded.cache_ttl_hours == 12
    assert loaded.output_template == "{artist} - {title} ({score:.2f})"
    assert loaded.log_format == "jsonl"
    assert loaded.log_absolute_paths is True
    assert loaded.metadata_fallback_enabled is False
    assert loaded.rename_require_template_fields is True
    assert loaded.rename_default_mode == "apply"
    assert loaded.rename_default_interactive is True
    assert loaded.rename_default_confirm_each is True
    assert loaded.rename_conflict_strategy == "overwrite"
    assert loaded.rename_metadata_confirm is False
    assert loaded.rename_deduplicate_template is False
    assert loaded.identify_default_limit == 5
    assert loaded.identify_output_json is True
    assert loaded.identify_refresh_cache is True
    assert loaded.identify_audd_enabled is False
    assert loaded.identify_audd_prefer is True
    assert loaded.identify_batch_limit == 4
    assert loaded.identify_batch_best_only is True
    assert loaded.identify_batch_recursive is True
    assert loaded.identify_batch_log_file == "logs/default.jsonl"
    assert loaded.identify_batch_audd_enabled is False
    assert loaded.identify_batch_audd_prefer is True


def test_load_config_missing_returns_default(tmp_path: Path) -> None:
    """Return defaults when the config file is absent."""
    target = tmp_path / "absent.toml"

    config = load_config(target)

    assert config.acoustid_api_key is None
    assert config.audd_api_token is None
    assert config.cache_enabled is True
    assert config.cache_ttl_hours == 24
    assert config.output_template is None
    assert config.log_format == "text"
    assert config.log_absolute_paths is False
    assert config.metadata_fallback_enabled is True
    assert config.rename_require_template_fields is False
    assert config.rename_default_mode == "dry-run"
    assert config.rename_default_interactive is False
    assert config.rename_default_confirm_each is False
    assert config.rename_conflict_strategy == "append"
    assert config.rename_metadata_confirm is True
    assert config.rename_deduplicate_template is True
    assert config.identify_default_limit == 3
    assert config.identify_output_json is False
    assert config.identify_refresh_cache is False
    assert config.identify_audd_enabled is True
    assert config.identify_audd_prefer is False
    assert config.identify_batch_limit == 3
    assert config.identify_batch_best_only is False
    assert config.identify_batch_recursive is False
    assert config.identify_batch_log_file is None
    assert config.identify_batch_audd_enabled is True
    assert config.identify_batch_audd_prefer is False


def test_write_config_with_audd_token(tmp_path: Path) -> None:
    """Persist the AudD token when present."""
    target = tmp_path / "config.toml"
    config = AppConfig(
        acoustid_api_key="key",
        audd_api_token=TEST_AUDD_TOKEN,
    )

    write_config(config, target)
    loaded = load_config(target)

    assert loaded.audd_api_token == TEST_AUDD_TOKEN
    assert loaded.rename_default_mode == "dry-run"
    assert loaded.identify_default_limit == 3
    assert loaded.rename_deduplicate_template is True

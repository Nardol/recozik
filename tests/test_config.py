from __future__ import annotations

from pathlib import Path

from recozik.config import AppConfig, load_config, write_config


def test_write_and_load_config(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"

    config = AppConfig(
        acoustid_api_key="abcd1234",
        cache_enabled=False,
        cache_ttl_hours=12,
        output_template="{artist} - {title} ({score:.2f})",
        log_format="jsonl",
        log_absolute_paths=True,
    )

    write_config(config, target)

    loaded = load_config(target)

    assert loaded.acoustid_api_key == "abcd1234"
    assert loaded.cache_enabled is False
    assert loaded.cache_ttl_hours == 12
    assert loaded.output_template == "{artist} - {title} ({score:.2f})"
    assert loaded.log_format == "jsonl"
    assert loaded.log_absolute_paths is True


def test_load_config_missing_returns_default(tmp_path: Path) -> None:
    target = tmp_path / "absent.toml"

    config = load_config(target)

    assert config.acoustid_api_key is None
    assert config.cache_enabled is True
    assert config.cache_ttl_hours == 24
    assert config.output_template is None
    assert config.log_format == "text"
    assert config.log_absolute_paths is False

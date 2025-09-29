"""User configuration helpers for recozik."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

try:  # pragma: no cover - import dépend de la version de Python
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

CONFIG_ENV_VAR = "RECOZIK_CONFIG_FILE"
CONFIG_DIR_NAME = "recozik"
CONFIG_FILE_NAME = "config.toml"


@dataclass(slots=True)
class AppConfig:
    """Application configuration exposed to the CLI."""

    acoustid_api_key: str | None = None
    cache_enabled: bool = True
    cache_ttl_hours: int = 24
    output_template: str | None = None
    log_format: str = "text"
    log_absolute_paths: bool = False

    def to_toml_dict(self) -> dict:
        """Return the configuration as a nested dictionary consumable by TOML writers."""
        data: dict[str, dict] = {
            "acoustid": {},
            "cache": {
                "enabled": self.cache_enabled,
                "ttl_hours": self.cache_ttl_hours,
            },
            "output": {},
            "logging": {
                "format": self.log_format,
                "absolute_paths": self.log_absolute_paths,
            },
        }

        if self.acoustid_api_key:
            data["acoustid"]["api_key"] = self.acoustid_api_key

        if self.output_template:
            data["output"]["template"] = self.output_template

        return data


def default_config_path() -> Path:
    """Return the user configuration file path."""
    env_value = os.environ.get(CONFIG_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()

    config_dir = Path(platformdirs.user_config_dir(CONFIG_DIR_NAME, appauthor=False))
    return config_dir / CONFIG_FILE_NAME


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from disk and return an ``AppConfig`` instance."""
    path = path or default_config_path()
    if not path.exists():
        return AppConfig()

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - dépend de l'environnement
        raise RuntimeError(f"Impossible de lire la configuration: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Configuration TOML invalide dans {path}: {exc}") from exc

    acoustid_section = data.get("acoustid", {}) or {}
    api_key = acoustid_section.get("api_key")

    if api_key is not None and not isinstance(api_key, str):
        raise RuntimeError("Le champ acoustid.api_key doit être une chaîne de caractères.")

    cache_section = data.get("cache", {}) or {}
    cache_enabled = bool(cache_section.get("enabled", True))
    cache_ttl_raw = cache_section.get("ttl_hours", 24)
    try:
        cache_ttl_hours = int(cache_ttl_raw)
    except (TypeError, ValueError) as exc:  # pragma: no cover - validation utilisateur
        raise RuntimeError("Le champ cache.ttl_hours doit être un entier.") from exc

    output_section = data.get("output", {}) or {}
    template = output_section.get("template")
    if template is not None and not isinstance(template, str):
        raise RuntimeError("Le champ output.template doit être une chaîne de caractères.")

    logging_section = data.get("logging", {}) or {}
    log_format = logging_section.get("format", "text")
    if not isinstance(log_format, str):
        log_format = "text"
    if log_format not in {"text", "jsonl"}:
        log_format = "text"
    log_absolute_paths = bool(logging_section.get("absolute_paths", False))

    return AppConfig(
        acoustid_api_key=api_key,
        cache_enabled=cache_enabled,
        cache_ttl_hours=cache_ttl_hours,
        output_template=template,
        log_format=log_format,
        log_absolute_paths=log_absolute_paths,
    )


def ensure_config_dir(path: Path | None = None) -> Path:
    """Make sure the configuration directory exists and return its path."""
    final_path = path or default_config_path()
    final_path.parent.mkdir(parents=True, exist_ok=True)
    return final_path


def write_config(config: AppConfig, path: Path | None = None) -> Path:
    """Persist configuration to TOML and return the output path."""
    target = ensure_config_dir(path)
    data = config.to_toml_dict()

    lines: list[str] = []

    lines.append("[acoustid]")
    api_key = data["acoustid"].get("api_key")
    if api_key:
        escaped = api_key.replace('"', '\\"')
        lines.append(f'api_key = "{escaped}"')
    else:
        lines.append('# api_key = "votre_cle_api"')
    lines.append("")

    lines.append("[cache]")
    lines.append(f"enabled = {str(data['cache']['enabled']).lower()}")
    lines.append(f"ttl_hours = {data['cache']['ttl_hours']}")
    lines.append("")

    lines.append("[output]")
    template = data["output"].get("template")
    if template:
        escaped_template = template.replace('"', '\\"')
        lines.append(f'template = "{escaped_template}"')
    else:
        lines.append('# template = "{artist} - {title}"')
    lines.append("")

    lines.append("[logging]")
    lines.append(f'format = "{data["logging"]["format"]}"')
    lines.append(f"absolute_paths = {str(data['logging']['absolute_paths']).lower()}")
    lines.append("")

    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return target


__all__ = [
    "CONFIG_ENV_VAR",
    "AppConfig",
    "default_config_path",
    "ensure_config_dir",
    "load_config",
    "write_config",
]

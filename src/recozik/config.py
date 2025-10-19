"""User configuration helpers for recozik."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from .i18n import _

try:  # pragma: no cover - depends on the Python version
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
    audd_api_token: str | None = None
    cache_enabled: bool = True
    cache_ttl_hours: int = 24
    output_template: str | None = None
    log_format: str = "text"
    log_absolute_paths: bool = False
    metadata_fallback_enabled: bool = True
    locale: str | None = None
    rename_log_cleanup: str = "ask"
    rename_require_template_fields: bool = False
    rename_default_mode: str = "dry-run"
    rename_default_interactive: bool = False
    rename_default_confirm_each: bool = False
    rename_conflict_strategy: str = "append"
    rename_metadata_confirm: bool = True
    identify_default_limit: int = 3
    identify_output_json: bool = False
    identify_refresh_cache: bool = False
    identify_audd_enabled: bool = True
    identify_audd_prefer: bool = False
    identify_batch_limit: int = 3
    identify_batch_best_only: bool = False
    identify_batch_recursive: bool = False
    identify_batch_log_file: str | None = None
    identify_batch_audd_enabled: bool = True
    identify_batch_audd_prefer: bool = False

    def to_toml_dict(self) -> dict:
        """Return the configuration as a nested dictionary consumable by TOML writers."""
        cleanup_mode = self.rename_log_cleanup
        if cleanup_mode not in {"ask", "always", "never"}:
            cleanup_mode = "ask"

        default_mode = self.rename_default_mode
        if default_mode not in {"dry-run", "apply"}:
            default_mode = "dry-run"

        data: dict[str, dict] = {
            "acoustid": {},
            "audd": {},
            "cache": {
                "enabled": self.cache_enabled,
                "ttl_hours": self.cache_ttl_hours,
            },
            "output": {},
            "logging": {
                "format": self.log_format,
                "absolute_paths": self.log_absolute_paths,
            },
            "metadata": {
                "fallback": self.metadata_fallback_enabled,
            },
            "general": {},
            "identify": {
                "limit": max(int(self.identify_default_limit), 1),
                "json": self.identify_output_json,
                "refresh": self.identify_refresh_cache,
                "audd_enabled": self.identify_audd_enabled,
                "prefer_audd": self.identify_audd_prefer,
            },
            "identify_batch": {
                "limit": max(int(self.identify_batch_limit), 1),
                "best_only": self.identify_batch_best_only,
                "recursive": self.identify_batch_recursive,
                "audd_enabled": self.identify_batch_audd_enabled,
                "prefer_audd": self.identify_batch_audd_prefer,
            },
            "rename": {
                "log_cleanup": cleanup_mode,
                "require_template_fields": self.rename_require_template_fields,
                "default_mode": default_mode,
                "interactive": self.rename_default_interactive,
                "confirm_each": self.rename_default_confirm_each,
                "conflict_strategy": self.rename_conflict_strategy
                if self.rename_conflict_strategy in {"append", "skip", "overwrite"}
                else "append",
                "metadata_confirm": self.rename_metadata_confirm,
            },
        }

        if self.acoustid_api_key:
            data["acoustid"]["api_key"] = self.acoustid_api_key

        if self.audd_api_token:
            data["audd"]["api_token"] = self.audd_api_token

        if self.output_template:
            data["output"]["template"] = self.output_template

        if self.locale:
            data["general"]["locale"] = self.locale

        if self.identify_batch_log_file:
            data["identify_batch"]["log_file"] = self.identify_batch_log_file

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
    except OSError as exc:  # pragma: no cover - depends on the environment
        message = _("Unable to read the configuration file: {error}").format(error=exc)
        raise RuntimeError(message) from exc
    except tomllib.TOMLDecodeError as exc:
        message = _("Invalid TOML configuration in {path}: {error}").format(path=path, error=exc)
        raise RuntimeError(message) from exc

    acoustid_section = data.get("acoustid", {}) or {}
    api_key = acoustid_section.get("api_key")

    if api_key is not None and not isinstance(api_key, str):
        raise RuntimeError(_("The field acoustid.api_key must be a string."))

    audd_section = data.get("audd", {}) or {}
    audd_token = audd_section.get("api_token")
    if audd_token is not None and not isinstance(audd_token, str):
        raise RuntimeError(_("The field audd.api_token must be a string."))

    cache_section = data.get("cache", {}) or {}
    cache_enabled = bool(cache_section.get("enabled", True))
    cache_ttl_raw = cache_section.get("ttl_hours", 24)
    try:
        cache_ttl_hours = int(cache_ttl_raw)
    except (TypeError, ValueError) as exc:  # pragma: no cover - user validation
        raise RuntimeError(_("The field cache.ttl_hours must be an integer.")) from exc

    output_section = data.get("output", {}) or {}
    template = output_section.get("template")
    if template is not None and not isinstance(template, str):
        raise RuntimeError(_("The field output.template must be a string."))

    logging_section = data.get("logging", {}) or {}
    log_format = logging_section.get("format", "text")
    if not isinstance(log_format, str):
        log_format = "text"
    if log_format not in {"text", "jsonl"}:
        log_format = "text"
    log_absolute_paths = bool(logging_section.get("absolute_paths", False))

    metadata_section = data.get("metadata", {}) or {}
    metadata_fallback = bool(metadata_section.get("fallback", True))

    general_section = data.get("general", {}) or {}
    locale_value = general_section.get("locale")
    if locale_value is not None and not isinstance(locale_value, str):
        raise RuntimeError(_("The field general.locale must be a string."))

    rename_section = data.get("rename", {}) or {}
    cleanup_value = rename_section.get("log_cleanup", "ask")
    if cleanup_value is None:
        cleanup_value = "ask"
    if not isinstance(cleanup_value, str):
        raise RuntimeError(_("The field rename.log_cleanup must be a string."))
    cleanup_value = cleanup_value.lower()
    if cleanup_value not in {"ask", "always", "never"}:
        raise RuntimeError(_("The field rename.log_cleanup must be ask, always, or never."))

    require_template_fields = rename_section.get("require_template_fields", False)
    if require_template_fields is None:
        require_template_fields = False
    if not isinstance(require_template_fields, bool):
        raise RuntimeError(_("The field rename.require_template_fields must be a boolean."))

    default_mode_value = rename_section.get("default_mode", "dry-run")
    if default_mode_value is None:
        default_mode_value = "dry-run"
    if not isinstance(default_mode_value, str):
        raise RuntimeError(_("The field rename.default_mode must be a string."))
    default_mode_value = default_mode_value.lower()
    if default_mode_value not in {"dry-run", "apply"}:
        raise RuntimeError(_("The field rename.default_mode must be dry-run or apply."))

    interactive_default = rename_section.get("interactive", False)
    if interactive_default is None:
        interactive_default = False
    if not isinstance(interactive_default, bool):
        raise RuntimeError(_("The field rename.interactive must be a boolean."))

    confirm_each_default = rename_section.get("confirm_each", False)
    if confirm_each_default is None:
        confirm_each_default = False
    if not isinstance(confirm_each_default, bool):
        raise RuntimeError(_("The field rename.confirm_each must be a boolean."))

    conflict_strategy_value = rename_section.get("conflict_strategy", "append")
    if conflict_strategy_value is None:
        conflict_strategy_value = "append"
    if not isinstance(conflict_strategy_value, str):
        raise RuntimeError(_("The field rename.conflict_strategy must be a string."))
    conflict_strategy_value = conflict_strategy_value.lower()
    if conflict_strategy_value not in {"append", "skip", "overwrite"}:
        raise RuntimeError(
            _("The field rename.conflict_strategy must be append, skip, or overwrite.")
        )

    metadata_confirm_default = rename_section.get("metadata_confirm", True)
    if metadata_confirm_default is None:
        metadata_confirm_default = True
    if not isinstance(metadata_confirm_default, bool):
        raise RuntimeError(_("The field rename.metadata_confirm must be a boolean."))

    identify_section = data.get("identify", {}) or {}
    identify_limit_raw = identify_section.get("limit", 3)
    try:
        identify_limit_value = max(int(identify_limit_raw), 1)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(_("The field identify.limit must be an integer.")) from exc
    identify_json_value = bool(identify_section.get("json", False))
    identify_refresh_value = bool(identify_section.get("refresh", False))
    identify_audd_enabled_raw = identify_section.get("audd_enabled", True)
    if identify_audd_enabled_raw is None:
        identify_audd_enabled_value = True
    elif isinstance(identify_audd_enabled_raw, bool):
        identify_audd_enabled_value = identify_audd_enabled_raw
    else:
        raise RuntimeError(_("The field identify.audd_enabled must be a boolean."))
    identify_prefer_raw = identify_section.get("prefer_audd", False)
    if identify_prefer_raw is None:
        identify_prefer_value = False
    elif isinstance(identify_prefer_raw, bool):
        identify_prefer_value = identify_prefer_raw
    else:
        raise RuntimeError(_("The field identify.prefer_audd must be a boolean."))

    identify_batch_section = data.get("identify_batch", {}) or {}
    identify_batch_limit_raw = identify_batch_section.get("limit", 3)
    try:
        identify_batch_limit_value = max(int(identify_batch_limit_raw), 1)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(_("The field identify_batch.limit must be an integer.")) from exc
    identify_batch_best_only_value = bool(identify_batch_section.get("best_only", False))
    identify_batch_recursive_value = bool(identify_batch_section.get("recursive", False))
    identify_batch_audd_enabled_raw = identify_batch_section.get("audd_enabled", True)
    if identify_batch_audd_enabled_raw is None:
        identify_batch_audd_enabled_value = True
    elif isinstance(identify_batch_audd_enabled_raw, bool):
        identify_batch_audd_enabled_value = identify_batch_audd_enabled_raw
    else:
        raise RuntimeError(_("The field identify_batch.audd_enabled must be a boolean."))
    identify_batch_prefer_raw = identify_batch_section.get("prefer_audd", False)
    if identify_batch_prefer_raw is None:
        identify_batch_prefer_value = False
    elif isinstance(identify_batch_prefer_raw, bool):
        identify_batch_prefer_value = identify_batch_prefer_raw
    else:
        raise RuntimeError(_("The field identify_batch.prefer_audd must be a boolean."))
    identify_batch_log_file_value = identify_batch_section.get("log_file")
    if identify_batch_log_file_value is not None and not isinstance(
        identify_batch_log_file_value, str
    ):
        raise RuntimeError(_("The field identify_batch.log_file must be a string."))

    return AppConfig(
        acoustid_api_key=api_key,
        audd_api_token=audd_token,
        cache_enabled=cache_enabled,
        cache_ttl_hours=cache_ttl_hours,
        output_template=template,
        log_format=log_format,
        log_absolute_paths=log_absolute_paths,
        metadata_fallback_enabled=metadata_fallback,
        locale=locale_value,
        rename_log_cleanup=cleanup_value,
        rename_require_template_fields=require_template_fields,
        rename_default_mode=default_mode_value,
        rename_default_interactive=interactive_default,
        rename_default_confirm_each=confirm_each_default,
        rename_conflict_strategy=conflict_strategy_value,
        rename_metadata_confirm=metadata_confirm_default,
        identify_default_limit=identify_limit_value,
        identify_output_json=identify_json_value,
        identify_refresh_cache=identify_refresh_value,
        identify_audd_enabled=identify_audd_enabled_value,
        identify_audd_prefer=identify_prefer_value,
        identify_batch_limit=identify_batch_limit_value,
        identify_batch_best_only=identify_batch_best_only_value,
        identify_batch_recursive=identify_batch_recursive_value,
        identify_batch_log_file=identify_batch_log_file_value,
        identify_batch_audd_enabled=identify_batch_audd_enabled_value,
        identify_batch_audd_prefer=identify_batch_prefer_value,
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
        lines.append('# api_key = "your_api_key"')
    lines.append("")

    lines.append("[audd]")
    audd_token = data["audd"].get("api_token")
    if audd_token:
        escaped = audd_token.replace('"', '\\"')
        lines.append(f'api_token = "{escaped}"')
    else:
        lines.append('# api_token = "your_audd_token"')
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

    lines.append("[metadata]")
    lines.append(f"fallback = {str(data['metadata']['fallback']).lower()}")
    lines.append("")

    lines.append("[logging]")
    lines.append(f'format = "{data["logging"]["format"]}"')
    lines.append(f"absolute_paths = {str(data['logging']['absolute_paths']).lower()}")
    lines.append("")

    lines.append("[identify]")
    lines.append(f"limit = {data['identify']['limit']}")
    lines.append(f"json = {str(data['identify']['json']).lower()}")
    lines.append(f"refresh = {str(data['identify']['refresh']).lower()}")
    lines.append(f"audd_enabled = {str(data['identify']['audd_enabled']).lower()}")
    lines.append(f"prefer_audd = {str(data['identify']['prefer_audd']).lower()}")
    lines.append("")

    lines.append("[identify_batch]")
    lines.append(f"limit = {data['identify_batch']['limit']}")
    lines.append(f"best_only = {str(data['identify_batch']['best_only']).lower()}")
    lines.append(f"recursive = {str(data['identify_batch']['recursive']).lower()}")
    lines.append(f"audd_enabled = {str(data['identify_batch']['audd_enabled']).lower()}")
    lines.append(f"prefer_audd = {str(data['identify_batch']['prefer_audd']).lower()}")
    log_file_value = data["identify_batch"].get("log_file")
    if log_file_value:
        escaped_log = log_file_value.replace('"', '\\"')
        lines.append(f'log_file = "{escaped_log}"')
    else:
        lines.append('# log_file = "recozik-batch.log"')
    lines.append("")

    lines.append("[rename]")
    cleanup_mode = data["rename"]["log_cleanup"]
    lines.append(f'log_cleanup = "{cleanup_mode}"')
    require_template_fields = data["rename"]["require_template_fields"]
    lines.append(f"require_template_fields = {str(require_template_fields).lower()}")
    lines.append(f'default_mode = "{data["rename"]["default_mode"]}"')
    lines.append(f"interactive = {str(data['rename']['interactive']).lower()}")
    lines.append(f"confirm_each = {str(data['rename']['confirm_each']).lower()}")
    lines.append(f'conflict_strategy = "{data["rename"]["conflict_strategy"]}"')
    lines.append(f"metadata_confirm = {str(data['rename']['metadata_confirm']).lower()}")
    lines.append("")

    lines.append("[general]")
    locale_setting = data["general"].get("locale")
    if locale_setting:
        escaped_locale = locale_setting.replace('"', '\\"')
        lines.append(f'locale = "{escaped_locale}"')
    else:
        lines.append('# locale = "fr_FR"')
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

"""File-system helpers used by CLI commands."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def resolve_path(path: Path) -> Path:
    """Normalize user-provided paths while expanding ``~``."""
    return path.expanduser().resolve()


def normalize_extensions(values: Iterable[str]) -> set[str]:
    """Return a sanitized set of extensions (prefixed with a dot)."""
    normalized: set[str] = set()
    for value in values:
        entry = value.strip().lower()
        if not entry:
            continue
        if not entry.startswith("."):
            entry = f".{entry}"
        normalized.add(entry)
    return normalized


def discover_audio_files(
    base_dir: Path,
    *,
    recursive: bool,
    patterns: Iterable[str],
    extensions: set[str],
) -> Iterable[Path]:
    """Yield audio files matching the provided selection criteria."""
    base_dir = base_dir.resolve()
    seen: set[Path] = set()

    def should_keep(path: Path) -> bool:
        try:
            if path.is_symlink():
                return False
            if not path.is_file():
                return False
        except OSError:
            return False
        if extensions and path.suffix.lower() not in extensions:
            return False
        return True

    iterator_patterns = list(patterns)

    def iterate() -> Iterable[Path]:
        if iterator_patterns:
            for pattern in iterator_patterns:
                if recursive:
                    yield from base_dir.rglob(pattern)
                else:
                    yield from base_dir.glob(pattern)
        else:
            if recursive:
                yield from base_dir.rglob("*")
            else:
                yield from base_dir.glob("*")

    for candidate in iterate():
        if not should_keep(candidate):
            continue
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def sanitize_filename(name: str) -> str:
    """Return a filesystem-friendly version of a filename."""
    sanitized_chars: list[str] = []
    for char in name:
        if char in INVALID_FILENAME_CHARS or ord(char) < 32 or char in {"/", "\\"}:
            sanitized_chars.append("_")
        else:
            sanitized_chars.append(char)
    sanitized = "".join(sanitized_chars)
    sanitized = sanitized.strip().strip(". ")
    return sanitized


def resolve_conflict_path(
    target_path: Path,
    source_path: Path,
    strategy: str,
    occupied: set[Path],
    dry_run: bool,
) -> Path | None:
    """Resolve collisions according to the strategy requested by the user."""
    candidate = target_path
    directory = candidate.parent

    if strategy == "append":
        base = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while (candidate.exists() and candidate != source_path) or candidate in occupied:
            candidate = directory / f"{base}-{counter}{suffix}"
            counter += 1
        return candidate

    if strategy == "skip":
        if (candidate.exists() and candidate != source_path) or candidate in occupied:
            return None
        return candidate

    if strategy == "overwrite":
        if candidate in occupied and candidate != source_path:
            return None
        return candidate

    return None


def compute_backup_path(source: Path, root: Path, backup_root: Path) -> Path:
    """Compute the backup destination keeping the directory structure."""
    try:
        relative = source.relative_to(root)
    except ValueError:
        relative = Path(source.name)
    return backup_root / relative

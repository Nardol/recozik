"""Service-layer implementation of the `rename-from-log` workflow."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from recozik_core.i18n import _

from .callbacks import PrintCallbacks, ServiceCallbacks
from .cli_support.logs import (
    extract_template_fields,
    format_score,
    load_jsonl_log,
    render_log_template,
)
from .cli_support.metadata import build_metadata_match, coerce_metadata_dict
from .cli_support.paths import (
    compute_backup_path,
    resolve_conflict_path,
    resolve_path,
    sanitize_filename,
)

_TEMPLATE_FIELDS_SUPPORTED = {
    "artist",
    "title",
    "album",
    "score",
    "recording_id",
    "release_group_id",
    "release_id",
    "ext",
    "stem",
}


class RenameServiceError(RuntimeError):
    """Raised when the rename workflow cannot proceed."""


class RenamePrompts(Protocol):
    """Prompt bridge so frontends can provide their own UI."""

    def yes_no(self, message: str, *, default: bool = True, require_answer: bool = False) -> bool:
        """Return True/False based on a yes/no prompt."""
        ...

    def select_match(self, matches: list[dict], source_path: Path) -> int | None:
        """Return the match index chosen by the user."""
        ...

    def interactive_interrupt_decision(self, has_planned: bool) -> str:
        """Handle interruptions during interactive selection."""
        ...

    def rename_interrupt_decision(self, remaining: int) -> str:
        """Handle interruptions during rename application."""
        ...


@dataclass(slots=True)
class RenameRequest:
    """User-provided configuration for rename operations."""

    log_path: Path
    root: Path
    template: str
    require_template_fields: bool
    dry_run: bool
    interactive: bool
    confirm_each: bool
    on_conflict: str
    backup_dir: Path | None
    export_path: Path | None
    metadata_fallback: bool
    metadata_fallback_confirm: bool
    deduplicate_template: bool
    preplanned_entries: list[tuple[Path, Path, dict]] | None = None


@dataclass(slots=True)
class RenameSummary:
    """Aggregate counters describing the outcome of a rename run."""

    planned: int
    applied: int
    skipped: int
    errors: int
    interrupted: bool
    dry_run: bool
    export_path: Path | None = None
    plan_entries: list[tuple[Path, Path, dict]] | None = None


def _normalize_template_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        text = str(value).strip()
    except Exception:
        return None
    return text or None


def _missing_template_fields(
    match: dict[str, object],
    required_fields: set[str],
    source_path: Path,
) -> set[str]:
    missing: set[str] = set()
    if not required_fields:
        return missing

    for field in required_fields:
        if field == "ext":
            candidate = _normalize_template_value(source_path.suffix)
        elif field == "stem":
            candidate = _normalize_template_value(source_path.stem)
        elif field == "score":
            candidate = _normalize_template_value(format_score(match.get("score")))
        else:
            candidate = _normalize_template_value(match.get(field))

        if candidate is None:
            missing.add(field)

    return missing


def _render_target_filename(template: str, match: dict[str, object], source_path: Path) -> str:
    rendered = render_log_template(match, template, source_path)
    sanitized = sanitize_filename(rendered)
    if not sanitized:
        sanitized = source_path.stem

    candidate = sanitized
    ext = source_path.suffix
    if ext and not candidate.lower().endswith(ext.lower()):
        candidate = f"{candidate}{ext}"
    return candidate


def rename_from_log(
    request: RenameRequest,
    *,
    callbacks: ServiceCallbacks | None = None,
    prompts: RenamePrompts,
) -> RenameSummary:
    """Execute the rename workflow and return summary statistics."""
    callbacks = callbacks or PrintCallbacks()

    resolved_log = resolve_path(request.log_path)
    if not resolved_log.is_file():
        raise RenameServiceError(_("Log file not found: {path}").format(path=resolved_log))

    try:
        entries = load_jsonl_log(resolved_log)
    except ValueError as exc:  # invalid JSON
        raise RenameServiceError(str(exc)) from exc

    if not entries:
        raise RenameServiceError(_("No entries found in the log."))

    root_path = resolve_path(request.root)
    template_fields_used = extract_template_fields(request.template)
    template_fields_to_check = {
        field for field in template_fields_used if field in _TEMPLATE_FIELDS_SUPPORTED
    }

    conflict_strategy = request.on_conflict.lower()
    if conflict_strategy not in {"append", "skip", "overwrite"}:
        raise RenameServiceError(
            _("Invalid conflict strategy: {choice}").format(choice=request.on_conflict)
        )

    backup_path = resolve_path(request.backup_dir) if request.backup_dir else None
    if backup_path:
        backup_path.mkdir(parents=True, exist_ok=True)

    planned: list[tuple[Path, Path, dict]] = []
    skipped = 0
    errors = 0
    apply_after_interrupt = False

    if request.preplanned_entries is not None:
        for source_entry, target_entry, match_data in request.preplanned_entries:
            source_path = (
                resolve_path(source_entry)
                if isinstance(source_entry, Path)
                else resolve_path(Path(source_entry))
            )
            target_path = (
                resolve_path(target_entry)
                if isinstance(target_entry, Path)
                else resolve_path(Path(target_entry))
            )
            planned.append((source_path, target_path, dict(match_data)))
    else:
        occupied: set[Path] = set()

        def _filter_matches(raw_matches: list[dict[str, object]], source_path: Path) -> list[dict]:
            if not request.require_template_fields or not template_fields_to_check:
                return [dict(match) for match in raw_matches]

            accepted: list[dict] = []
            for match in raw_matches:
                missing = _missing_template_fields(match, template_fields_to_check, source_path)
                if missing:
                    callbacks.warning(
                        _("Match skipped for {name}: missing template values ({fields}).").format(
                            name=source_path.name,
                            fields=", ".join(sorted(missing)),
                        )
                    )
                    continue
                accepted.append(dict(match))
            return accepted

        def _deduplicate_matches(matches: list[dict[str, object]], source_path: Path) -> list[dict]:
            if not request.deduplicate_template:
                return list(matches)
            unique: list[dict] = []
            seen: set[str] = set()
            for match in matches:
                candidate = _render_target_filename(request.template, match, source_path)
                fingerprint = candidate.casefold()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                unique.append(match)
            return unique

        def _prepare_matches(raw_matches: list[dict[str, object]], source_path: Path) -> list[dict]:
            filtered = _filter_matches(raw_matches, source_path)
            if not filtered:
                return filtered
            return _deduplicate_matches(filtered, source_path)

        for entry in entries:
            raw_path = entry.get("path")
            if not raw_path:
                errors += 1
                callbacks.warning(_("Entry without a path: skipped."))
                continue

            source_path = Path(raw_path)
            if not source_path.is_absolute():
                source_path = (root_path / source_path).resolve()

            if not source_path.exists():
                errors += 1
                callbacks.warning(_("File not found, skipped: {path}").format(path=source_path))
                continue

            status = entry.get("status")
            error_message = entry.get("error")
            note = entry.get("note")

            matches = _prepare_matches(list(entry.get("matches") or []), source_path)
            metadata_entry = coerce_metadata_dict(entry.get("metadata"))

            if status == "unmatched" and not matches:
                context = f" ({note})" if note else ""
                if request.metadata_fallback and metadata_entry:
                    callbacks.info(
                        _("No AcoustID match for {path}, using embedded metadata.").format(
                            path=source_path
                        )
                    )
                    matches = _prepare_matches([build_metadata_match(metadata_entry)], source_path)
                    if not matches:
                        skipped += 1
                        message = _("No proposal for: {path}{context}").format(
                            path=source_path, context=context
                        )
                        callbacks.info(message)
                        continue
                else:
                    skipped += 1
                    message = _("No proposal for: {path}{context}").format(
                        path=source_path, context=context
                    )
                    callbacks.info(message)
                    continue

            if error_message:
                if matches:
                    skipped += 1
                    callbacks.info(
                        _("Entry with error, skipped: {path} ({error})").format(
                            path=source_path, error=error_message
                        )
                    )
                    continue
                if request.metadata_fallback and metadata_entry:
                    callbacks.info(
                        _("No AcoustID match for {path}, using embedded metadata.").format(
                            path=source_path
                        )
                    )
                    matches = _prepare_matches([build_metadata_match(metadata_entry)], source_path)
                    if not matches:
                        skipped += 1
                        callbacks.info(_("No proposal for: {path}").format(path=source_path))
                        continue
                else:
                    skipped += 1
                    callbacks.info(
                        _("Entry with error, skipped: {path} ({error})").format(
                            path=source_path, error=error_message
                        )
                    )
                    continue

            if not matches:
                if request.metadata_fallback and metadata_entry:
                    callbacks.info(
                        _("No AcoustID match for {path}, using embedded metadata.").format(
                            path=source_path
                        )
                    )
                    matches = _prepare_matches([build_metadata_match(metadata_entry)], source_path)
                    if not matches:
                        skipped += 1
                        callbacks.info(_("No proposal for: {path}").format(path=source_path))
                        continue
                else:
                    skipped += 1
                    callbacks.info(_("No proposal for: {path}").format(path=source_path))
                    continue

            selected_match_index: int | None = 0
            if request.interactive and len(matches) > 1:
                while True:
                    try:
                        selected_match_index = prompts.select_match(matches, source_path)
                    except KeyboardInterrupt:
                        decision = prompts.interactive_interrupt_decision(bool(planned))
                        if decision == "cancel":
                            raise RenameServiceError(
                                _("Operation cancelled; no files renamed.")
                            ) from None
                        if decision == "apply":
                            apply_after_interrupt = True
                            break
                        continue
                    else:
                        break

                if apply_after_interrupt:
                    break

                if selected_match_index is None:
                    skipped += 1
                    callbacks.info(
                        _("No selection made for {name}; skipping.").format(name=source_path.name)
                    )
                    continue

            assert selected_match_index is not None
            match_data = matches[selected_match_index]
            is_metadata_match = match_data.get("source") == "metadata"
            new_name = _render_target_filename(request.template, match_data, source_path)
            target_path = source_path.with_name(new_name)
            if target_path == source_path:
                skipped += 1
                callbacks.info(_("Already named correctly: {name}").format(name=source_path.name))
                continue

            final_target = resolve_conflict_path(
                target_path,
                source_path,
                conflict_strategy,
                occupied,
                request.dry_run,
            )

            if final_target is None:
                skipped += 1
                callbacks.info(
                    _("Unresolved collision, file skipped: {name}").format(name=source_path.name)
                )
                continue

            metadata_confirmation_done = False

            if is_metadata_match and request.metadata_fallback_confirm:
                question = _(
                    "Confirm rename based on embedded metadata: {source} -> {target}?"
                ).format(source=source_path.name, target=final_target.name)
                skip_current = False
                while True:
                    try:
                        if not prompts.yes_no(question, default=True):
                            skip_current = True
                            break
                        metadata_confirmation_done = True
                        break
                    except KeyboardInterrupt:
                        decision = prompts.interactive_interrupt_decision(bool(planned))
                    if decision == "cancel":
                        raise RenameServiceError(
                            _("Operation cancelled; no files renamed.")
                        ) from None
                        if decision == "apply":
                            apply_after_interrupt = True
                            break
                        continue

                if apply_after_interrupt:
                    break

                if skip_current:
                    skipped += 1
                    callbacks.info(
                        _("Metadata-based rename skipped for {name}.").format(name=source_path.name)
                    )
                    continue

            if request.confirm_each and not metadata_confirmation_done:
                question = _("Rename {source} -> {target}?").format(
                    source=source_path.name,
                    target=final_target.name,
                )
                skip_current = False
                while True:
                    try:
                        if not prompts.yes_no(question, default=True):
                            skip_current = True
                            break
                        break
                    except KeyboardInterrupt:
                        decision = prompts.interactive_interrupt_decision(bool(planned))
                    if decision == "cancel":
                        raise RenameServiceError(
                            _("Operation cancelled; no files renamed.")
                        ) from None
                        if decision == "apply":
                            apply_after_interrupt = True
                            break
                        continue

                if apply_after_interrupt:
                    break

                if skip_current:
                    skipped += 1
                    callbacks.info(_("Rename skipped for {name}").format(name=source_path.name))
                    continue

            planned.append((source_path, final_target, match_data))
            occupied.add(final_target)

    if not planned:
        callbacks.info(
            _("No rename performed ({skipped} skipped, {errors} errors).").format(
                skipped=skipped, errors=errors
            )
        )
        return RenameSummary(
            planned=0,
            applied=0,
            skipped=skipped,
            errors=errors,
            interrupted=False,
            dry_run=request.dry_run,
        )

    if apply_after_interrupt and planned:
        callbacks.info(_("Continuing with renames confirmed before the interruption."))

    def execute_planned(run_dry_run: bool) -> tuple[int, bool, list[dict]]:
        renamed_count = 0
        index = 0
        interrupted = False
        entries_out: list[dict] = []

        while index < len(planned):
            source_path, target_path, match_data = planned[index]
            action = _("DRY-RUN") if run_dry_run else _("RENAMED")
            callbacks.info(
                _("{action}: {source} -> {target}").format(
                    action=action,
                    source=source_path,
                    target=target_path,
                )
            )

            if run_dry_run:
                entries_out.append(
                    {
                        "source": str(source_path),
                        "target": str(target_path),
                        "applied": False,
                        "match": match_data,
                    }
                )
                index += 1
                continue

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)

                if backup_path:
                    backup_file = compute_backup_path(source_path, root_path, backup_path)
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, backup_file)

                if target_path.exists() and conflict_strategy == "overwrite":
                    target_path.unlink()

                source_path.rename(target_path)
            except KeyboardInterrupt:
                decision = prompts.rename_interrupt_decision(len(planned) - index)
                if decision == "continue":
                    callbacks.info(_("Continuing renaming."))
                    continue

                interrupted = True
                callbacks.info(
                    _(
                        "Renaming interrupted; {completed} file(s) already renamed, "
                        "{remaining} file(s) left untouched."
                    ).format(
                        completed=renamed_count,
                        remaining=len(planned) - index,
                    )
                )
                break
            except OSError as exc:
                callbacks.error(
                    _("Failed to rename {source}: {error}").format(source=source_path, error=exc)
                )
                interrupted = True
                break

            renamed_count += 1
            entries_out.append(
                {
                    "source": str(source_path),
                    "target": str(target_path),
                    "applied": True,
                    "match": match_data,
                }
            )
            index += 1

        return renamed_count, interrupted, entries_out

    renamed_count, interrupted_during_rename, export_data = execute_planned(request.dry_run)

    if request.dry_run and not interrupted_during_rename:
        callbacks.info(
            _(
                "Dry-run complete: {planned} potential renames, {skipped} skipped, {errors} errors."
            ).format(planned=len(planned), skipped=skipped, errors=errors)
        )

    if not request.dry_run and not interrupted_during_rename:
        callbacks.info(
            _("Renaming complete: {renamed} file(s), {skipped} skipped, {errors} errors.").format(
                renamed=renamed_count, skipped=skipped, errors=errors
            )
        )

    exported_path: Path | None = None
    if request.export_path and export_data:
        exported_path = resolve_path(request.export_path)
        exported_path.parent.mkdir(parents=True, exist_ok=True)
        exported_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        callbacks.info(_("Summary written to {path}").format(path=exported_path))

    plan_entries = planned if request.preplanned_entries is None and request.dry_run else None

    return RenameSummary(
        planned=len(planned),
        applied=renamed_count if not request.dry_run else 0,
        skipped=skipped,
        errors=errors,
        interrupted=interrupted_during_rename,
        dry_run=request.dry_run,
        export_path=exported_path,
        plan_entries=plan_entries,
    )


__all__ = [
    "RenamePrompts",
    "RenameRequest",
    "RenameServiceError",
    "RenameSummary",
    "rename_from_log",
]

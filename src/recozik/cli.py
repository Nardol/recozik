"""Command-line interface for recozik."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from string import Formatter
from typing import Any

import click
import requests
import typer
from typer.completion import (
    get_completion_script as generate_completion_script,
)
from typer.completion import (
    install as install_completion,
)
from typer.completion import (
    shellingham as completion_shellingham,
)

from .cache import LookupCache
from .config import AppConfig, default_config_path, load_config, write_config
from .fingerprint import (
    AcoustIDLookupError,
    AcoustIDMatch,
    FingerprintError,
    FingerprintResult,
    compute_fingerprint,
    lookup_recordings,
)

try:  # pragma: no cover - dépend de l'environnement
    import mutagen  # type: ignore[import-not-found]  # noqa: F401
except ImportError:  # pragma: no cover - dépend de l'environnement
    mutagen = None  # type: ignore[assignment]

app = typer.Typer(
    add_completion=False,
    help="Reconnaissance musicale basée sur les empreintes audio.",
)
config_app = typer.Typer(
    add_completion=False,
    help="Gestion de la configuration locale.",
)
completion_app = typer.Typer(
    add_completion=False,
    help="Outils d'auto-complétion du shell.",
)

app.add_typer(config_app, name="config")
app.add_typer(completion_app, name="completion")

DEFAULT_AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus"}
_VALIDATION_TRACK_ID = "9ff43b6a-4f16-427c-93c2-92307ca505e0"
_VALIDATION_ENDPOINT = "https://api.acoustid.org/v2/lookup"


def _resolve_path(path: Path) -> Path:
    """Normalize user-provided paths while expanding ``~``."""
    return path.expanduser().resolve()


@app.callback()
def main() -> None:
    """Top-level callback for the CLI application."""


@app.command(help="Affiche les métadonnées de base du fichier audio.")
def inspect(
    audio_path: Path = typer.Argument(..., help="Chemin du fichier audio à analyser."),
) -> None:
    """Display basic metadata for the provided audio file."""
    resolved = _resolve_path(audio_path)
    if not resolved.is_file():
        typer.echo(f"Fichier introuvable: {resolved}")
        raise typer.Exit(code=1)

    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement d'exécution
        typer.echo(
            "La bibliothèque soundfile est absente; "
            "lancez `uv sync` pour installer les dépendances."
        )
        raise typer.Exit(code=1) from exc

    try:
        info = sf.info(str(resolved))
    except RuntimeError as exc:
        typer.echo(f"Impossible de lire le fichier audio: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Fichier: {resolved}")
    typer.echo(f"Format: {info.format}, {info.subtype}")
    typer.echo(f"Canaux: {info.channels}")
    typer.echo(f"Fréquence d'échantillonnage: {info.samplerate} Hz")
    typer.echo(f"Nombre d'images: {info.frames}")
    typer.echo(f"Durée estimée: {info.duration:.2f} s")

    metadata = _extract_audio_metadata(resolved)
    if metadata:
        typer.echo("Métadonnées (tags):")
        if artist := metadata.get("artist"):
            typer.echo(f"  Artiste: {artist}")
        if title := metadata.get("title"):
            typer.echo(f"  Titre: {title}")
        if album := metadata.get("album"):
            typer.echo(f"  Album: {album}")
    elif mutagen is None:  # pragma: no cover - dépend des installations
        typer.echo("Métadonnées non disponibles (bibliothèque mutagen absente).")


@app.command(help="Génère l'empreinte Chromaprint d'un fichier audio.")
def fingerprint(
    audio_path: Path = typer.Argument(..., help="Chemin du fichier audio à fingerprint."),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help="Chemin explicite vers l'exécutable fpcalc si Chromaprint n'est pas dans PATH.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Fichier dans lequel écrire l'empreinte au format JSON.",
    ),
    show_fingerprint: bool = typer.Option(
        False,
        "--show-fingerprint",
        help=(
            "Affiche l'empreinte complète dans la console "
            "(longue et moins pratique pour les lecteurs d'écran)."
        ),
    ),
) -> None:
    """Generate a Chromaprint fingerprint for an audio file."""
    resolved_audio = _resolve_path(audio_path)
    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        result: FingerprintResult = compute_fingerprint(resolved_audio, fpcalc_path=resolved_fpcalc)
    except FingerprintError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"Durée estimée: {result.duration_seconds:.2f} s")

    if output is not None:
        resolved_output = _resolve_path(output)
        payload = {
            "audio_path": str(resolved_audio),
            "duration_seconds": result.duration_seconds,
            "fingerprint": result.fingerprint,
            "fpcalc_path": str(resolved_fpcalc) if resolved_fpcalc else None,
        }
        resolved_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        typer.echo(f"Empreinte sauvegardée dans {resolved_output}")

    if show_fingerprint:
        typer.echo("Empreinte Chromaprint:")
        typer.echo(result.fingerprint)


@app.command(help="Identifie un morceau via l'API AcoustID.")
def identify(
    audio_path: Path = typer.Argument(..., help="Chemin du fichier audio à identifier."),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help="Chemin explicite vers l'exécutable fpcalc si Chromaprint n'est pas dans PATH.",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="Clé API AcoustID à utiliser (prioritaire sur la configuration).",
    ),
    limit: int = typer.Option(3, "--limit", min=1, max=10, help="Nombre de résultats à afficher."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=(
            "Affiche les résultats au format JSON "
            "(utile pour automatiser ou consommer via lecteur d'écran)."
        ),
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help="Modèle d'affichage (placeholders: {artist}, {title}, {album}, {score}, ...).",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Ignore le cache local et force un nouvel appel à l'API.",
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help="Chemin personnalisé du fichier de configuration (tests).",
    ),
) -> None:
    """Identify a track with the AcoustID API."""
    resolved_audio = _resolve_path(audio_path)
    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        typer.echo("Aucune clé API AcoustID configurée.")
        if _prompt_yes_no("Souhaitez-vous l'enregistrer maintenant ?", default=True):
            new_key = _configure_api_key_interactively(config, config_path)
            if not new_key:
                typer.echo("Aucune clé n'a été enregistrée. Opération annulée.")
                raise typer.Exit(code=1)
            key = new_key
            try:
                config = load_config(config_path)
            except RuntimeError:
                config = AppConfig(acoustid_api_key=key)
        else:
            typer.echo("Opération annulée.")
            raise typer.Exit(code=1)

    try:
        fingerprint_result: FingerprintResult = compute_fingerprint(
            resolved_audio,
            fpcalc_path=resolved_fpcalc,
        )
    except FingerprintError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    cache = LookupCache(
        enabled=config.cache_enabled,
        ttl=timedelta(hours=max(config.cache_ttl_hours, 1)),
    )

    matches = None
    if config.cache_enabled and not refresh:
        matches = cache.get(fingerprint_result.fingerprint, fingerprint_result.duration_seconds)

    if matches is None:
        try:
            matches = lookup_recordings(key, fingerprint_result)
        except AcoustIDLookupError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc
        if config.cache_enabled:
            cache.set(fingerprint_result.fingerprint, fingerprint_result.duration_seconds, matches)
            cache.save()
    else:
        matches = list(matches)

    if not matches:
        typer.echo("Aucune correspondance trouvée.")
        cache.save()
        return

    matches = matches[:limit]

    if json_output:
        payload = [match.to_dict() for match in matches]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        cache.save()
        return

    template_value = _resolve_template(template, config)

    for idx, match in enumerate(matches, start=1):
        typer.echo(f"Résultat {idx}: score {match.score:.2f}")
        typer.echo(f"  {_format_match_template(match, template_value)}")
        if match.release_group_title:
            typer.echo(f"  Album: {match.release_group_title}")
        elif match.releases:
            primary = match.releases[0]
            album = primary.title or "Album inconnu"
            suffix = f" ({primary.date})" if primary.date else ""
            typer.echo(f"  Album: {album}{suffix}")
        typer.echo(f"  Recording ID: {match.recording_id}")
        if match.release_group_id:
            typer.echo(f"  Release Group ID: {match.release_group_id}")

    cache.save()


@app.command(
    "identify-batch",
    help="Identifie les fichiers audio d'un dossier et enregistre les résultats.",
)
def identify_batch(
    directory: Path = typer.Argument(..., help="Dossier contenant les fichiers audio."),
    fpcalc_path: Path | None = typer.Option(
        None,
        "--fpcalc-path",
        help="Chemin explicite vers l'exécutable fpcalc si Chromaprint n'est pas dans PATH.",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="Clé API AcoustID à utiliser (prioritaire sur la configuration).",
    ),
    limit: int = typer.Option(
        3,
        "--limit",
        min=1,
        max=10,
        help="Nombre de propositions à conserver.",
    ),
    best_only: bool = typer.Option(
        False,
        "--best-only",
        help="Enregistre uniquement la meilleure proposition pour chaque fichier.",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive/--no-recursive",
        help="Active la recherche récursive dans les sous-dossiers.",
    ),
    pattern: list[str] = typer.Option(
        [],
        "--pattern",
        help="Motif glob à appliquer (peut être répété).",
    ),
    extension: list[str] = typer.Option(
        [],
        "--ext",
        "--extension",
        help="Extension de fichier à inclure (ex: mp3). Peut être répétée.",
    ),
    log_file: Path | None = typer.Option(
        None,
        "--log-file",
        "-o",
        help="Fichier de sortie du rapport (défaut: recozik-batch.log).",
    ),
    append: bool = typer.Option(
        False,
        "--append/--overwrite",
        help="Ajoute à la fin du log existant au lieu de recréer le fichier.",
    ),
    log_format: str | None = typer.Option(
        None,
        "--log-format",
        help="Format du log: text ou jsonl.",
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help="Modèle d'affichage des propositions ({artist}, {title}, {album}, {score}, ...).",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Ignore le cache local et force un nouvel appel à l'API.",
    ),
    metadata_fallback: bool | None = typer.Option(
        None,
        "--metadata-fallback/--no-metadata-fallback",
        help="Utilise les métadonnées embarquées lorsqu'AcoustID ne retourne aucune correspondance.",
    ),
    absolute_paths: bool | None = typer.Option(
        None,
        "--absolute-paths/--relative-paths",
        help="Contrôle l'affichage des chemins dans le log (écrase la config).",
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help="Chemin personnalisé du fichier de configuration (tests).",
    ),
) -> None:
    """Identify audio files in a directory and record the results."""
    resolved_dir = _resolve_path(directory)
    if not resolved_dir.is_dir():
        typer.echo(f"Dossier introuvable: {resolved_dir}")
        raise typer.Exit(code=1)

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        typer.echo("Aucune clé API AcoustID configurée.")
        if _prompt_yes_no("Souhaitez-vous l'enregistrer maintenant ?", default=True):
            new_key = _configure_api_key_interactively(config, config_path)
            if not new_key:
                typer.echo("Aucune clé n'a été enregistrée. Opération annulée.")
                raise typer.Exit(code=1)
            key = new_key
            try:
                config = load_config(config_path)
            except RuntimeError:
                config = AppConfig(acoustid_api_key=key)
        else:
            typer.echo("Opération annulée.")
            raise typer.Exit(code=1)

    template_value = _resolve_template(template, config)
    log_format_value = (log_format or config.log_format).lower()
    if log_format_value not in {"text", "jsonl"}:
        typer.echo("Format de log invalide. Utilisez 'text' ou 'jsonl'.")
        raise typer.Exit(code=1)

    use_absolute = config.log_absolute_paths if absolute_paths is None else absolute_paths

    effective_extensions = _normalize_extensions(extension)
    if not pattern and not effective_extensions:
        effective_extensions = DEFAULT_AUDIO_EXTENSIONS

    files = list(
        _discover_audio_files(
            resolved_dir,
            recursive=recursive,
            patterns=pattern,
            extensions=effective_extensions,
        )
    )
    files.sort()

    if not files:
        typer.echo("Aucun fichier audio correspondant.")
        return

    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    cache = LookupCache(
        enabled=config.cache_enabled,
        ttl=timedelta(hours=max(config.cache_ttl_hours, 1)),
    )

    use_metadata_fallback = (
        config.metadata_fallback_enabled if metadata_fallback is None else metadata_fallback
    )

    effective_limit = 1 if best_only else limit

    log_path = _resolve_path(log_file) if log_file else Path.cwd() / "recozik-batch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"

    success = 0
    unmatched = 0
    failures = 0

    with log_path.open(mode, encoding="utf-8") as handle:
        for file_path in files:
            if use_absolute:
                relative_display = str(file_path)
            else:
                try:
                    relative_display = str(file_path.relative_to(resolved_dir))
                except ValueError:
                    relative_display = str(file_path)

            try:
                fingerprint_result = compute_fingerprint(file_path, fpcalc_path=resolved_fpcalc)
            except FingerprintError as exc:
                _write_log_entry(
                    handle,
                    log_format_value,
                    relative_display,
                    [],
                    str(exc),
                    template_value,
                    None,
                    status="error",
                    metadata=None,
                )
                failures += 1
                continue

            matches = None
            if config.cache_enabled and not refresh:
                matches = cache.get(
                    fingerprint_result.fingerprint,
                    fingerprint_result.duration_seconds,
                )

            if matches is None:
                try:
                    matches = lookup_recordings(key, fingerprint_result)
                except AcoustIDLookupError as exc:
                    _write_log_entry(
                        handle,
                        log_format_value,
                        relative_display,
                        [],
                        str(exc),
                        template_value,
                        fingerprint_result,
                        status="error",
                        metadata=None,
                    )
                    failures += 1
                    continue
                if config.cache_enabled:
                    cache.set(
                        fingerprint_result.fingerprint,
                        fingerprint_result.duration_seconds,
                        matches,
                    )
            else:
                matches = list(matches)

            if not matches:
                metadata_payload = (
                    _extract_audio_metadata(file_path) if use_metadata_fallback else None
                )
                _write_log_entry(
                    handle,
                    log_format_value,
                    relative_display,
                    [],
                    None,
                    template_value,
                    fingerprint_result,
                    status="unmatched",
                    note="Aucune correspondance.",
                    metadata=metadata_payload,
                )
                if metadata_payload:
                    typer.echo(
                        f"Aucune correspondance pour {relative_display}, métadonnées locales enregistrées."
                    )
                unmatched += 1
                continue

            selected = matches[:effective_limit]
            _write_log_entry(
                handle,
                log_format_value,
                relative_display,
                selected,
                None,
                template_value,
                fingerprint_result,
                metadata=None,
            )
            success += 1

    cache.save()
    typer.echo(
        "Traitement terminé: "
        f"{success} fichier(s) identifiés, "
        f"{unmatched} non reconnu(s), "
        f"{failures} en erreur. Log: {log_path}"
    )


@app.command(
    "rename-from-log",
    help="Renomme les fichiers à partir d'un log JSONL produit par `identify-batch`.",
)
def rename_from_log(
    log_path: Path = typer.Argument(..., help="Log JSONL généré par `identify-batch`."),
    root: Path | None = typer.Option(
        None,
        "--root",
        help="Répertoire racine contenant les fichiers à renommer (défaut: dossier du log).",
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help=(
            "Modèle de renommage ({artist}, {title}, {album}, {score}, "
            "{recording_id}, {ext}, {stem})."
        ),
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--apply",
        help=(
            "Affiche les renommages sans les exécuter (par défaut). "
            "Utilisez --apply pour appliquer."
        ),
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive/--no-interactive",
        help=("Propose un choix interactif quand plusieurs correspondances sont disponibles."),
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm/--no-confirm",
        help="Demande une confirmation pour chaque fichier avant renommage.",
    ),
    on_conflict: str = typer.Option(
        "append",
        "--on-conflict",
        help="Gestion des collisions: append (défaut), skip, overwrite.",
    ),
    backup_dir: Path | None = typer.Option(
        None,
        "--backup-dir",
        help="Dossier dans lequel copier les originaux avant renommage (optionnel).",
    ),
    export_path: Path | None = typer.Option(
        None,
        "--export",
        help="Chemin d'un fichier JSON résumant les renommages planifiés.",
    ),
    metadata_fallback: bool | None = typer.Option(
        None,
        "--metadata-fallback/--no-metadata-fallback",
        help="Utilise les métadonnées du fichier pour renommer lorsqu'aucune proposition n'est disponible.",
    ),
    metadata_fallback_confirm: bool = typer.Option(
        True,
        "--metadata-fallback-confirm/--metadata-fallback-no-confirm",
        help=(
            "Demande une confirmation lorsqu'un renommage repose uniquement sur les métadonnées intégrées. "
            "Utilisez --metadata-fallback-no-confirm pour automatiser."
        ),
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help="Chemin personnalisé du fichier de configuration (tests).",
    ),
) -> None:
    """Rename files using a JSONL log generated by ``identify-batch``."""
    resolved_log = _resolve_path(log_path)
    if not resolved_log.is_file():
        typer.echo(f"Log introuvable: {resolved_log}")
        raise typer.Exit(code=1)

    root_path = _resolve_path(root) if root else resolved_log.parent

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    template_value = _resolve_template(template, config)
    conflict_strategy = on_conflict.lower()
    if conflict_strategy not in {"append", "skip", "overwrite"}:
        typer.echo("Valeur --on-conflict invalide. Choisissez append, skip ou overwrite.")
        raise typer.Exit(code=1)

    use_metadata_fallback = (
        config.metadata_fallback_enabled if metadata_fallback is None else metadata_fallback
    )

    try:
        entries = _load_jsonl_log(resolved_log)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if not entries:
        typer.echo("Aucune entrée dans le log.")
        return

    backup_path = _resolve_path(backup_dir) if backup_dir else None
    if backup_path:
        backup_path.mkdir(parents=True, exist_ok=True)

    planned: list[tuple[Path, Path, dict]] = []
    export_entries: list[dict] = []
    occupied: set[Path] = set()
    renamed = 0
    skipped = 0
    errors = 0

    for entry in entries:
        raw_path = entry.get("path")
        if not raw_path:
            errors += 1
            typer.echo("Entrée sans chemin: ignorée.")
            continue

        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = (root_path / source_path).resolve()

        if not source_path.exists():
            errors += 1
            typer.echo(f"Fichier introuvable, ignoré: {source_path}")
            continue

        status = entry.get("status")
        error_message = entry.get("error")
        note = entry.get("note")

        matches = entry.get("matches") or []
        metadata_entry = _coerce_metadata_dict(entry.get("metadata"))

        if status == "unmatched" and not matches:
            if use_metadata_fallback and metadata_entry:
                typer.echo(
                    f"Aucune correspondance AcoustID pour {source_path}, utilisation des métadonnées intégrées."
                )
                matches = [_build_metadata_match(metadata_entry)]
            else:
                skipped += 1
                context = f" ({note})" if note else ""
                typer.echo(
                    f"Aucune proposition pour: {source_path}{context}"
                )
                continue

        if error_message:
            if matches:
                skipped += 1
                typer.echo(
                    f"Entrée en erreur, ignorée: {source_path} ({error_message})"
                )
                continue
            if use_metadata_fallback and metadata_entry:
                typer.echo(
                    f"Aucune correspondance AcoustID pour {source_path}, utilisation des métadonnées intégrées."
                )
                matches = [_build_metadata_match(metadata_entry)]
                error_message = None
            else:
                skipped += 1
                typer.echo(
                    f"Entrée en erreur, ignorée: {source_path} ({error_message})"
                )
                continue

        if not matches:
            if use_metadata_fallback and metadata_entry:
                typer.echo(
                    f"Aucune correspondance AcoustID pour {source_path}, utilisation des métadonnées intégrées."
                )
                matches = [_build_metadata_match(metadata_entry)]
            else:
                skipped += 1
                typer.echo(f"Aucune proposition pour: {source_path}")
                continue

        selected_match_index = 0
        if interactive and len(matches) > 1:
            selected_match_index = _prompt_match_selection(matches, source_path)
            if selected_match_index is None:
                skipped += 1
                typer.echo(f"Aucune sélection faite pour {source_path.name}, passage.")
                continue

        match_data = matches[selected_match_index]
        is_metadata_match = match_data.get("source") == "metadata"
        target_base = _render_log_template(match_data, template_value, source_path)
        sanitized = _sanitize_filename(target_base)
        if not sanitized:
            sanitized = source_path.stem

        ext = source_path.suffix
        new_name = sanitized
        if ext and not new_name.lower().endswith(ext.lower()):
            new_name = f"{new_name}{ext}"

        target_path = source_path.with_name(new_name)
        if target_path == source_path:
            skipped += 1
            typer.echo(f"Déjà au bon nom: {source_path.name}")
            continue

        final_target = _resolve_conflict_path(
            target_path,
            source_path,
            conflict_strategy,
            occupied,
            dry_run,
        )

        if final_target is None:
            skipped += 1
            typer.echo(f"Collision non résolue, fichier ignoré: {source_path.name}")
            continue

        metadata_confirmation_done = False

        if is_metadata_match and metadata_fallback_confirm:
            question = (
                "Confirmer le renommage basé sur les métadonnées: "
                f"{source_path.name} -> {final_target.name} ?"
            )
            if not _prompt_yes_no(question, default=True):
                skipped += 1
                typer.echo(
                    f"Renommage par métadonnées ignoré pour {source_path.name}"
                )
                continue
            metadata_confirmation_done = True

        if confirm and not metadata_confirmation_done:
            question = f"Renommer {source_path.name} -> {final_target.name} ?"
            if not _prompt_yes_no(question, default=True):
                skipped += 1
                typer.echo(f"Renommage ignoré pour {source_path.name}")
                continue

        planned.append((source_path, final_target, match_data))
        occupied.add(final_target)

    if not planned:
        typer.echo(f"Aucun renommage à effectuer ({skipped} ignoré(s), {errors} en erreur).")
        return

    for source_path, target_path, match_data in planned:
        action = "DRY-RUN" if dry_run else "RENOMME"
        typer.echo(f"{action}: {source_path} -> {target_path}")

        if dry_run:
            export_entries.append(
                {
                    "source": str(source_path),
                    "target": str(target_path),
                    "applied": False,
                    "match": match_data,
                }
            )
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if backup_path:
            backup_file = _compute_backup_path(source_path, root_path, backup_path)
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, backup_file)

        if target_path.exists() and conflict_strategy == "overwrite":
            target_path.unlink()

        source_path.rename(target_path)
        renamed += 1
        export_entries.append(
            {
                "source": str(source_path),
                "target": str(target_path),
                "applied": True,
                "match": match_data,
            }
        )

    if dry_run:
        typer.echo(
            "Dry-run terminé: "
            f"{len(planned)} renommage(s) potentiel(s), "
            f"{skipped} ignoré(s), {errors} en erreur. "
            "Utilisez --apply pour exécuter."
        )
    else:
        typer.echo(
            f"Renommage terminé: {renamed} fichier(s), {skipped} ignoré(s), {errors} en erreur."
        )

    if export_path and export_entries:
        resolved_export = _resolve_path(export_path)
        resolved_export.parent.mkdir(parents=True, exist_ok=True)
        resolved_export.write_text(
            json.dumps(export_entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        typer.echo(f"Résumé écrit dans {resolved_export}")


@completion_app.command(
    "install",
    help="Installe le script d'auto-complétion pour le shell courant.",
)
def completion_install(
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help="Shell cible (bash, zsh, fish, powershell/pwsh). Détection automatique sinon.",
    ),
    print_command: bool = typer.Option(
        False,
        "--print-command",
        help="Affiche uniquement la commande à ajouter dans le profil sans texte supplémentaire.",
    ),
    no_write: bool = typer.Option(
        False,
        "--no-write",
        help="Génère le script sur la sortie standard sans créer/modifier de fichier.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Écrit le script de complétion dans un fichier spécifique (chemin absolu ou relatif).",
    ),
) -> None:
    """Install the shell completion script for the current shell."""
    target_shell = _normalize_shell(shell)

    if sum(bool(flag) for flag in (print_command, no_write, output is not None)) > 1:
        typer.echo("Choisissez une seule option parmi --print-command, --no-write ou --output.")
        raise typer.Exit(code=1)

    if no_write:
        detected_shell = _detect_shell(target_shell)
        if not detected_shell:
            typer.echo("Impossible de détecter le shell. Fournissez --shell (bash/zsh/fish/pwsh).")
            raise typer.Exit(code=1)

        script = generate_completion_script(
            prog_name="recozik",
            complete_var="_RECOZIK_COMPLETE",
            shell=detected_shell,
        )
        typer.echo(script)
        return

    if output is not None:
        detected_shell = _detect_shell(target_shell)
        if not detected_shell:
            typer.echo("Impossible de détecter le shell. Fournissez --shell (bash/zsh/fish/pwsh).")
            raise typer.Exit(code=1)

        script = generate_completion_script(
            prog_name="recozik",
            complete_var="_RECOZIK_COMPLETE",
            shell=detected_shell,
        )
        resolved_path = _resolve_path(output)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(script, encoding="utf-8")
        typer.echo(f"Script de complétion écrit dans {resolved_path}")
        typer.echo("Ajoutez-le manuellement à votre configuration de shell si nécessaire.")
        return

    try:
        detected_shell, script_path = install_completion(shell=target_shell, prog_name="recozik")
    except click.exceptions.Exit as exc:
        typer.echo("Shell non pris en charge pour l'auto-complétion.")
        raise typer.Exit(code=1) from exc

    command = _completion_source_command(detected_shell, script_path)

    if print_command:
        if command:
            typer.echo(command)
        else:
            typer.echo(str(script_path))
        return

    typer.echo(f"Complétion installée pour {detected_shell}.")
    typer.echo(f"Script: {script_path}")
    if command:
        typer.echo(f"Commande à ajouter: {command}")
    typer.echo(_completion_hint(detected_shell, script_path))


@completion_app.command(
    "show",
    help="Affiche le script d'auto-complétion généré.",
)
def completion_show(
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help="Shell cible (bash, zsh, fish, powershell/pwsh). Détection automatique sinon.",
    ),
) -> None:
    """Display the generated shell-completion script."""
    detected_shell = _detect_shell(shell)
    if not detected_shell:
        typer.echo("Impossible de détecter le shell. Fournissez --shell (bash/zsh/fish/pwsh).")
        raise typer.Exit(code=1)

    script = generate_completion_script(
        prog_name="recozik",
        complete_var="_RECOZIK_COMPLETE",
        shell=detected_shell,
    )
    typer.echo(script)


@completion_app.command(
    "uninstall",
    help="Supprime le script d'auto-complétion installé par recozik.",
)
def completion_uninstall(
    shell: str | None = typer.Option(
        None,
        "--shell",
        "-s",
        help="Shell cible (bash, zsh, fish, powershell/pwsh). Détection automatique sinon.",
    ),
) -> None:
    """Remove the shell-completion script installed by recozik."""
    detected_shell = _detect_shell(shell)
    if not detected_shell:
        typer.echo("Impossible de détecter le shell. Fournissez --shell (bash/zsh/fish/pwsh).")
        raise typer.Exit(code=1)

    script_path = _completion_script_path(detected_shell)
    if script_path and script_path.exists():
        script_path.unlink()
        typer.echo(f"Script de complétion supprimé: {script_path}")
    else:
        typer.echo("Aucun script de complétion spécifique à supprimer.")

    typer.echo(_completion_uninstall_hint(detected_shell))


def _normalize_shell(shell: str | None) -> str | None:
    if shell is None:
        return None

    normalized = shell.strip().lower()
    if normalized in {"", "auto"}:
        return None
    if normalized in {"powershell", "pwsh"}:
        return "pwsh"
    return normalized


def _detect_shell(shell: str | None) -> str | None:
    normalized = _normalize_shell(shell)
    if normalized:
        return normalized

    if completion_shellingham is None:
        return None

    disable_detection = os.getenv("_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION")
    if disable_detection:
        return None

    try:
        detected_shell, _ = completion_shellingham.detect_shell()
    except Exception:  # pragma: no cover - dépend du système
        return None

    return _normalize_shell(detected_shell)


def _completion_hint(shell: str, script_path: Path) -> str:
    command = _completion_source_command(shell, script_path)
    if command:
        if shell in {"bash", "zsh"}:
            return (
                f"Exécutez `{command}` ou ajoutez cette ligne à votre fichier "
                "de profil (ex. ~/.bashrc, ~/.zshrc)."
            )
        if shell == "fish":
            return f"Relancez `fish` ou exécutez `{command}` pour activer la complétion."
        if shell in {"powershell", "pwsh"}:
            return (
                f"Ajoutez `{command}` à votre `$PROFILE` (PowerShell) "
                "pour charger automatiquement la complétion."
            )
    return "La complétion est installée. Rechargez votre terminal pour l'utiliser."


def _completion_source_command(shell: str, script_path: Path) -> str | None:
    if shell in {"bash", "zsh", "fish"}:
        return f"source {script_path}"
    if shell in {"powershell", "pwsh"}:
        return f". {script_path}"
    return None


def _completion_script_path(shell: str) -> Path | None:
    if shell == "bash":
        return Path.home() / ".bash_completions" / "recozik.sh"
    if shell == "zsh":
        return Path.home() / ".zfunc" / "_recozik"
    if shell == "fish":
        return Path.home() / ".config/fish/completions/recozik.fish"
    if shell in {"powershell", "pwsh"}:
        return _powershell_profile_path(shell)
    return None


def _powershell_profile_path(shell: str) -> Path | None:
    shell_bin = "pwsh" if shell == "pwsh" else "powershell"
    try:
        command = [shell_bin, "-NoProfile", "-Command", "echo", "$profile"]
        result = subprocess.run(  # noqa: S603 - arguments forcés en liste contrôlée
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:  # pragma: no cover - dépend de l'environnement
        return None

    output = result.stdout.strip()
    if not output:
        return None
    return Path(output)


def _completion_uninstall_hint(shell: str) -> str:
    if shell == "bash":
        return (
            "Si besoin, supprimez la ligne `source ~/.bash_completions/recozik.sh` "
            "de votre ~/.bashrc."
        )
    if shell == "zsh":
        return (
            "Vérifiez votre ~/.zshrc et retirez la ligne ajoutant ~/.zfunc "
            "si vous ne l'utilisez plus."
        )
    if shell == "fish":
        return "Redémarrez fish pour prendre en compte la suppression."
    if shell in {"powershell", "pwsh"}:
        return (
            "Éditez votre fichier $PROFILE pour retirer le bloc de complétion ajouté par recozik."
        )
    return "Complétion désinstallée."


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _resolve_template(template: str | None, config: AppConfig) -> str:
    if template:
        return template
    if config.output_template:
        return config.output_template
    return "{artist} - {title}"


def _format_match_template(match: AcoustIDMatch, template: str) -> str:
    context = _build_match_context(match)
    formatter = Formatter()
    try:
        return formatter.vformat(template, (), _SafeDict(context))
    except Exception:  # pragma: no cover - template invalide
        fallback = "{artist} - {title}"
        return formatter.vformat(fallback, (), _SafeDict(context))


def _build_match_context(match: AcoustIDMatch) -> dict[str, str]:
    album = match.release_group_title
    if not album and match.releases:
        album = match.releases[0].title

    release_id = match.release_group_id
    if not release_id and match.releases:
        release_id = match.releases[0].release_id

    return {
        "artist": match.artist or "Artiste inconnu",
        "title": match.title or "Titre inconnu",
        "album": album or "",
        "release_id": release_id or "",
        "recording_id": match.recording_id or "",
        "score": f"{match.score:.2f}",
    }


def _normalize_extensions(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        entry = value.strip().lower()
        if not entry:
            continue
        if not entry.startswith("."):
            entry = f".{entry}"
        normalized.add(entry)
    return normalized


def _discover_audio_files(
    base_dir: Path,
    *,
    recursive: bool,
    patterns: Iterable[str],
    extensions: set[str],
) -> Iterable[Path]:
    seen: set[Path] = set()

    def _should_keep(path: Path) -> bool:
        if not path.is_file():
            return False
        if not extensions:
            return True
        return path.suffix.lower() in extensions

    iterator_patterns = list(patterns)
    if iterator_patterns:
        for pattern in iterator_patterns:
            globber = base_dir.rglob(pattern) if recursive else base_dir.glob(pattern)
            for item in globber:
                resolved = item.resolve()
                if resolved in seen:
                    continue
                if _should_keep(resolved):
                    seen.add(resolved)
                    yield resolved
    else:
        globber = base_dir.rglob("*") if recursive else base_dir.glob("*")
        for item in globber:
            resolved = item.resolve()
            if resolved in seen:
                continue
            if _should_keep(resolved):
                seen.add(resolved)
                yield resolved


def _write_log_entry(
    handle,
    log_format: str,
    path_display: str,
    matches: Iterable[AcoustIDMatch],
    error: str | None,
    template: str,
    fingerprint: FingerprintResult | None,
    *,
    status: str = "ok",
    note: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    if log_format == "jsonl":
        entry = {
            "path": path_display,
            "duration_seconds": fingerprint.duration_seconds if fingerprint else None,
            "error": error,
            "status": status,
            "note": note,
            "matches": [
                {
                    "rank": idx,
                    "formatted": _format_match_template(match, template),
                    "score": match.score,
                    "recording_id": match.recording_id,
                    "artist": match.artist,
                    "title": match.title,
                    "album": match.release_group_title
                    or (match.releases[0].title if match.releases else None),
                    "release_group_id": match.release_group_id,
                    "release_id": match.releases[0].release_id if match.releases else None,
                }
                for idx, match in enumerate(matches, start=1)
            ],
            "metadata": metadata or None,
        }
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return

    handle.write(f"file: {path_display}\n")
    if fingerprint:
        handle.write(f"  duration: {fingerprint.duration_seconds:.2f}s\n")
    if status and status != "ok":
        handle.write(f"  status: {status}\n")
    if note:
        handle.write(f"  note: {note}\n")
    if metadata:
        handle.write("  metadata:\n")
        for key in ("artist", "title", "album"):
            value = metadata.get(key)
            if value:
                handle.write(f"    {key}: {value}\n")
    if error:
        handle.write(f"  error: {error}\n\n")
        return

    for idx, match in enumerate(matches, start=1):
        formatted = _format_match_template(match, template)
        handle.write(f"  {idx}. {formatted} (score {match.score:.2f})\n")
    handle.write("\n")


def _load_jsonl_log(path: Path) -> list[dict]:
    entries: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Le log doit être au format JSONL "
                    "(réexécutez `identify-batch` avec --log-format jsonl)."
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Entrée invalide au format JSONL (ligne {line_number}).")
            entries.append(payload)
    return entries


def _render_log_template(match: dict, template: str, source_path: Path) -> str:
    context = {
        "artist": match.get("artist") or "Artiste inconnu",
        "title": match.get("title") or "Titre inconnu",
        "album": match.get("album") or "",
        "score": _format_score(match.get("score")),
        "recording_id": match.get("recording_id") or "",
        "release_group_id": match.get("release_group_id") or "",
        "release_id": match.get("release_id") or "",
        "ext": source_path.suffix,
        "stem": source_path.stem,
    }

    formatted = match.get("formatted")
    formatter = Formatter()
    try:
        return formatter.vformat(template, (), _SafeDict(context))
    except Exception:
        if formatted:
            return formatted
        return formatter.vformat("{artist} - {title}", (), _SafeDict(context))


def _format_score(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value or "")


def _extract_audio_metadata(path: Path) -> dict[str, str] | None:
    if mutagen is None:  # pragma: no cover - dépend des installations
        return None

    try:
        audio = mutagen.File(path, easy=True)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - sécurité supplémentaire
        return None

    if audio is None:
        return None

    tags = getattr(audio, "tags", None)
    if not tags:
        return None

    def _first_value(tag_value: Any) -> str | None:
        if tag_value is None:
            return None
        if isinstance(tag_value, str):
            candidate = tag_value.strip()
            return candidate or None
        if isinstance(tag_value, (list, tuple, set)):
            for item in tag_value:
                candidate = _first_value(item)
                if candidate:
                    return candidate
            return None
        try:
            candidate = str(tag_value).strip()
        except Exception:  # pragma: no cover - conversion prudente
            return None
        return candidate or None

    metadata: dict[str, str] = {}
    for key in ("artist", "title", "album"):
        value = _first_value(tags.get(key))  # type: ignore[arg-type]
        if value:
            metadata[key] = value

    return metadata or None



def _coerce_metadata_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    result: dict[str, str] = {}
    for key in ("artist", "title", "album"):
        raw = value.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            candidate = raw.strip()
        else:
            try:
                candidate = str(raw).strip()
            except Exception:  # pragma: no cover - conversion prudente
                continue
        if candidate:
            result[key] = candidate
    return result



def _build_metadata_match(metadata: dict[str, str]) -> dict[str, object]:
    artist_value = metadata.get("artist") or "Artiste inconnu"
    title_value = metadata.get("title") or "Titre inconnu"
    formatted = f"{artist_value} - {title_value}"
    return {
        "score": None,
        "recording_id": None,
        "artist": metadata.get("artist"),
        "title": metadata.get("title"),
        "album": metadata.get("album"),
        "release_group_id": None,
        "release_id": None,
        "formatted": formatted,
        "source": "metadata",
    }


INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def _sanitize_filename(name: str) -> str:
    sanitized_chars: list[str] = []
    for char in name:
        if char in INVALID_FILENAME_CHARS or ord(char) < 32 or char in {"/", "\\"}:
            sanitized_chars.append("_")
        else:
            sanitized_chars.append(char)
    sanitized = "".join(sanitized_chars)
    sanitized = sanitized.strip().strip(". ")
    return sanitized


def _resolve_conflict_path(
    target_path: Path,
    source_path: Path,
    strategy: str,
    occupied: set[Path],
    dry_run: bool,
) -> Path | None:
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


def _compute_backup_path(source: Path, root: Path, backup_root: Path) -> Path:
    try:
        relative = source.relative_to(root)
    except ValueError:
        relative = Path(source.name)
    return backup_root / relative


def _prompt_match_selection(matches: list[dict], source_path: Path) -> int | None:
    typer.echo(f"Plusieurs propositions pour {source_path.name}:")
    for idx, match in enumerate(matches, start=1):
        artist = match.get("artist") or "Artiste inconnu"
        title = match.get("title") or "Titre inconnu"
        score = _format_score(match.get("score"))
        typer.echo(f"  {idx}. {artist} - {title} (score {score})")

    prompt = "Sélectionnez un numéro (ENTER pour annuler) : "

    while True:
        choice = typer.prompt(prompt, default="", show_default=False).strip()
        if not choice:
            return None

        try:
            idx = int(choice)
        except ValueError:
            typer.echo("Sélection invalide, veuillez réessayer.")
            continue

        if 1 <= idx <= len(matches):
            return idx - 1

        typer.echo("Indice hors plage, veuillez réessayer.")


def _prompt_yes_no(message: str, *, default: bool = True) -> bool:
    suffix = "[o/N]" if not default else "[O/n]"
    prompt = f"{message} {suffix}"
    default_char = "o" if default else "n"

    while True:
        response = typer.prompt(prompt, default=default_char, show_default=False)
        if not response:
            return default
        normalized = response.strip().lower()
        if normalized in {"o", "oui", "y", "yes"}:
            return True
        if normalized in {"n", "non", "no"}:
            return False
        typer.echo("Réponse invalide (o/n).")


def _prompt_api_key() -> str | None:
    key = typer.prompt("Clé API AcoustID", show_default=False).strip()
    if not key:
        return None
    confirmation = typer.prompt("Confirmez la clé", default=key, show_default=False).strip()
    if confirmation != key:
        typer.echo("Les clés ne correspondent pas.")
        return None
    return key


def _validate_client_key(key: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        response = requests.get(
            _VALIDATION_ENDPOINT,
            params={"client": key, "trackid": _VALIDATION_TRACK_ID, "json": 1},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"Impossible de contacter AcoustID ({exc})."

    if response.status_code != 200:
        return False, f"Réponse HTTP inattendue ({response.status_code})."

    try:
        data = response.json()
    except ValueError:
        return False, "Réponse JSON invalide reçue depuis AcoustID."

    if data.get("status") != "ok":
        error = data.get("message")
        if not error and isinstance(data.get("error"), dict):
            error = data["error"].get("message")
        return False, error or "Clé refusée par AcoustID."

    return True, ""


def _configure_api_key_interactively(
    existing: AppConfig,
    config_path: Path | None,
    *,
    skip_validation: bool = False,
) -> str | None:
    key = _prompt_api_key()
    if not key:
        return None

    if not skip_validation:
        valid, message = _validate_client_key(key)
        if not valid:
            typer.echo(f"Validation de la clé échouée: {message}")
            return None

    updated = AppConfig(
        acoustid_api_key=key,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
    )

    target = write_config(updated, config_path)
    typer.echo(f"Clé AcoustID enregistrée dans {target}")
    return key


@config_app.command(
    "path",
    help="Affiche le chemin du fichier de configuration actuellement utilisé.",
)
def config_path(
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Print the configuration file path in use."""
    target = config_path or default_config_path()
    typer.echo(str(target))


@config_app.command(
    "show",
    help="Affiche les principaux paramètres de configuration.",
)
def config_show(
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Show the key configuration settings."""
    target = config_path or default_config_path()
    try:
        config = load_config(target)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    key = config.acoustid_api_key
    if key:
        masked = key[:4] + "…" + key[-4:] if len(key) > 8 else "…" * len(key)
        typer.echo(f"Clé AcoustID: {masked}")
    else:
        typer.echo("Clé AcoustID: non configurée")
        typer.echo("Créez ou mettez à jour votre clé avec `recozik config set-key`.")
    cache_state = "oui" if config.cache_enabled else "non"
    typer.echo(f"Cache activé: {cache_state} (TTL: {config.cache_ttl_hours} h)")
    template = config.output_template or "{artist} - {title}"
    typer.echo(f"Template par défaut: {template}")
    path_mode = "absolus" if config.log_absolute_paths else "relatifs"
    typer.echo(f"Format du log: {config.log_format} (chemins {path_mode})")
    typer.echo(f"Fichier: {target}")


@config_app.command(
    "set-key",
    help="Enregistre une clé API AcoustID dans la configuration.",
)
def config_set_key(
    api_key_arg: str | None = typer.Argument(
        None,
        help="Clé API AcoustID à enregistrer.",
    ),
    api_key_opt: str | None = typer.Option(
        None,
        "--api-key",
        "-k",
        help="Clé API AcoustID à enregistrer (alternative à l'argument).",
    ),
    skip_validation: bool = typer.Option(
        False,
        "--skip-validation/--validate",
        help="Ignore la vérification en ligne (déconseillé).",
    ),
    config_path: Path | None = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Persist the AcoustID API key into the configuration file."""
    target_path = config_path or default_config_path()
    try:
        existing = load_config(target_path)
    except RuntimeError:
        existing = AppConfig()

    key = (api_key_opt or api_key_arg or "").strip()

    if key:
        confirmation = typer.prompt("Confirmez la clé", default=key)
        if confirmation.strip() != key:
            typer.echo("Les clés ne correspondent pas. Opération annulée.")
            raise typer.Exit(code=1)
    else:
        key = _prompt_api_key()
        if not key:
            typer.echo("Aucune clé API fournie.")
            raise typer.Exit(code=1)

    if not skip_validation:
        valid, message = _validate_client_key(key)
        if not valid:
            typer.echo(f"Validation de la clé échouée: {message}")
            raise typer.Exit(code=1)

    updated = AppConfig(
        acoustid_api_key=key,
        cache_enabled=existing.cache_enabled,
        cache_ttl_hours=existing.cache_ttl_hours,
        output_template=existing.output_template,
        log_format=existing.log_format,
        log_absolute_paths=existing.log_absolute_paths,
    )

    target = write_config(updated, config_path)
    typer.echo(f"Clé AcoustID enregistrée dans {target}")


if __name__ == "__main__":  # pragma: no cover
    app()

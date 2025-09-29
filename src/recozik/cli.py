"""Interface en ligne de commande pour recozik."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path
from string import Formatter
from typing import Iterable, Optional

import click
import typer
from typer.completion import (
    get_completion_script as generate_completion_script,
    install as install_completion,
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

app = typer.Typer(add_completion=False, help="Reconnaissance musicale basée sur les empreintes audio.")
config_app = typer.Typer(add_completion=False, help="Gestion de la configuration locale.")
completion_app = typer.Typer(add_completion=False, help="Outils d'auto-complétion du shell.")

app.add_typer(config_app, name="config")
app.add_typer(completion_app, name="completion")

DEFAULT_AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus"}


def _resolve_path(path: Path) -> Path:
    """Normalise un chemin utilisateur en tenant compte de ``~``."""
    return path.expanduser().resolve()


@app.callback()
def main() -> None:
    """Point d'entrée principal de l'application."""


@app.command()
def inspect(
    audio_path: Path = typer.Argument(..., help="Chemin du fichier audio à analyser."),
) -> None:
    """Affiche les métadonnées de base du fichier audio."""

    resolved = _resolve_path(audio_path)
    if not resolved.is_file():
        typer.echo(f"Fichier introuvable: {resolved}")
        raise typer.Exit(code=1)

    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement d'exécution
        typer.echo("La bibliothèque soundfile est absente; lancez `uv sync` pour installer les dépendances.")
        raise typer.Exit(code=1) from exc

    try:
        info = sf.info(str(resolved))
    except RuntimeError as exc:
        typer.echo(f"Impossible de lire le fichier audio: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Fichier: {resolved}")
    typer.echo(f"Format: {info.format}, {info.subtype}")
    typer.echo(f"Canaux: {info.channels}")
    typer.echo(f"Fréquence d'échantillonnage: {info.samplerate} Hz")
    typer.echo(f"Nombre d'images: {info.frames}")
    typer.echo(f"Durée estimée: {info.duration:.2f} s")


@app.command()
def fingerprint(
    audio_path: Path = typer.Argument(..., help="Chemin du fichier audio à fingerprint."),
    fpcalc_path: Optional[Path] = typer.Option(
        None,
        "--fpcalc-path",
        help="Chemin explicite vers l'exécutable fpcalc si Chromaprint n'est pas dans PATH.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Fichier dans lequel écrire l'empreinte au format JSON.",
    ),
    show_fingerprint: bool = typer.Option(
        False,
        "--show-fingerprint",
        help="Affiche l'empreinte complète dans la console (longue et moins pratique pour les lecteurs d'écran).",
    ),
) -> None:
    """Génère l'empreinte Chromaprint d'un fichier audio."""

    resolved_audio = _resolve_path(audio_path)
    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        result: FingerprintResult = compute_fingerprint(resolved_audio, fpcalc_path=resolved_fpcalc)
    except FingerprintError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

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


@app.command()
def identify(
    audio_path: Path = typer.Argument(..., help="Chemin du fichier audio à identifier."),
    fpcalc_path: Optional[Path] = typer.Option(
        None,
        "--fpcalc-path",
        help="Chemin explicite vers l'exécutable fpcalc si Chromaprint n'est pas dans PATH.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Clé API AcoustID à utiliser (prioritaire sur la configuration).",
    ),
    limit: int = typer.Option(3, "--limit", min=1, max=10, help="Nombre de résultats à afficher."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Affiche les résultats au format JSON (utile pour automatiser ou consommer via lecteur d'écran).",
    ),
    template: Optional[str] = typer.Option(
        None,
        "--template",
        help="Modèle d'affichage (placeholders: {artist}, {title}, {album}, {score}, ...).",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Ignore le cache local et force un nouvel appel à l'API.",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help="Chemin personnalisé du fichier de configuration (tests).",
    ),
) -> None:
    """Identifie un morceau via l'API AcoustID."""

    resolved_audio = _resolve_path(audio_path)
    resolved_fpcalc = _resolve_path(fpcalc_path) if fpcalc_path else None

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        target = config_path or default_config_path()
        typer.echo("Aucune clé API AcoustID configurée.")
        typer.echo(
            "Utilisez `recozik config set-key` ou éditez le fichier "
            f"{target} pour enregistrer votre clé."
        )
        raise typer.Exit(code=1)

    try:
        fingerprint_result: FingerprintResult = compute_fingerprint(resolved_audio, fpcalc_path=resolved_fpcalc)
    except FingerprintError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

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
            raise typer.Exit(code=1)
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


@app.command("identify-batch")
def identify_batch(
    directory: Path = typer.Argument(..., help="Dossier contenant les fichiers audio."),
    fpcalc_path: Optional[Path] = typer.Option(
        None,
        "--fpcalc-path",
        help="Chemin explicite vers l'exécutable fpcalc si Chromaprint n'est pas dans PATH.",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="Clé API AcoustID à utiliser (prioritaire sur la configuration).",
    ),
    limit: int = typer.Option(3, "--limit", min=1, max=10, help="Nombre de propositions à conserver."),
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
    log_file: Optional[Path] = typer.Option(
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
    log_format: Optional[str] = typer.Option(
        None,
        "--log-format",
        help="Format du log: text ou jsonl.",
    ),
    template: Optional[str] = typer.Option(
        None,
        "--template",
        help="Modèle d'affichage des propositions ({artist}, {title}, {album}, {score}, ...).",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Ignore le cache local et force un nouvel appel à l'API.",
    ),
    absolute_paths: Optional[bool] = typer.Option(
        None,
        "--absolute-paths/--relative-paths",
        help="Contrôle l'affichage des chemins dans le log (écrase la config).",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config-path",
        hidden=True,
        help="Chemin personnalisé du fichier de configuration (tests).",
    ),
) -> None:
    """Identifie tous les fichiers audio d'un dossier et consigne les résultats."""

    resolved_dir = _resolve_path(directory)
    if not resolved_dir.is_dir():
        typer.echo(f"Dossier introuvable: {resolved_dir}")
        raise typer.Exit(code=1)

    try:
        config = load_config(config_path)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    key = (api_key or config.acoustid_api_key or "").strip()
    if not key:
        target = config_path or default_config_path()
        typer.echo("Aucune clé API AcoustID configurée.")
        typer.echo(
            "Utilisez `recozik config set-key` ou éditez le fichier "
            f"{target} pour enregistrer votre clé."
        )
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

    effective_limit = 1 if best_only else limit

    log_path = _resolve_path(log_file) if log_file else Path.cwd() / "recozik-batch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"

    total = len(files)
    success = 0
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
                )
                failures += 1
                continue

            matches = None
            if config.cache_enabled and not refresh:
                matches = cache.get(fingerprint_result.fingerprint, fingerprint_result.duration_seconds)

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
                _write_log_entry(
                    handle,
                    log_format_value,
                    relative_display,
                    [],
                    "Aucune correspondance.",
                    template_value,
                    fingerprint_result,
                )
                failures += 1
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
            )
            success += 1

    cache.save()
    typer.echo(
        f"Traitement terminé: {success} fichier(s) identifiés, {failures} en échec. Log: {log_path}"
    )

@completion_app.command("install")
def completion_install(
    shell: Optional[str] = typer.Option(
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
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Écrit le script de complétion dans un fichier spécifique (chemin absolu ou relatif).",
    ),
) -> None:
    """Installe le script d'auto-complétion pour le shell courant."""

    target_shell = _normalize_shell(shell)

    if sum(bool(flag) for flag in (print_command, no_write, output is not None)) > 1:
        typer.echo("Choisissez une seule option parmi --print-command, --no-write ou --output.")
        raise typer.Exit(code=1)

    if no_write:
        detected_shell = _detect_shell(target_shell)
        if not detected_shell:
            typer.echo(
                "Impossible de détecter le shell. Fournissez --shell (bash/zsh/fish/pwsh)."
            )
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
            typer.echo(
                "Impossible de détecter le shell. Fournissez --shell (bash/zsh/fish/pwsh)."
            )
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
        detected_shell, script_path = install_completion(
            shell=target_shell, prog_name="recozik"
        )
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


@completion_app.command("show")
def completion_show(
    shell: Optional[str] = typer.Option(
        None,
        "--shell",
        "-s",
        help="Shell cible (bash, zsh, fish, powershell/pwsh). Détection automatique sinon.",
    ),
) -> None:
    """Affiche le script d'auto-complétion généré."""

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


@completion_app.command("uninstall")
def completion_uninstall(
    shell: Optional[str] = typer.Option(
        None,
        "--shell",
        "-s",
        help="Shell cible (bash, zsh, fish, powershell/pwsh). Détection automatique sinon.",
    ),
) -> None:
    """Supprime le script d'auto-complétion installé par recozik."""

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


def _normalize_shell(shell: Optional[str]) -> Optional[str]:
    if shell is None:
        return None

    normalized = shell.strip().lower()
    if normalized in {"", "auto"}:
        return None
    if normalized in {"powershell", "pwsh"}:
        return "pwsh"
    return normalized


def _detect_shell(shell: Optional[str]) -> Optional[str]:
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
                f"Exécutez `{command}` ou ajoutez cette ligne à votre fichier de profil (ex. ~/.bashrc, ~/.zshrc)."
            )
        if shell == "fish":
            return (
                f"Relancez `fish` ou exécutez `{command}` pour activer la complétion."
            )
        if shell in {"powershell", "pwsh"}:
            return (
                f"Ajoutez `{command}` à votre `$PROFILE` (PowerShell) pour charger automatiquement la complétion."
            )
    return "La complétion est installée. Rechargez votre terminal pour l'utiliser."


def _completion_source_command(shell: str, script_path: Path) -> Optional[str]:
    if shell in {"bash", "zsh", "fish"}:
        return f"source {script_path}"
    if shell in {"powershell", "pwsh"}:
        return f". {script_path}"
    return None


def _completion_script_path(shell: str) -> Optional[Path]:
    if shell == "bash":
        return Path.home() / ".bash_completions" / "recozik.sh"
    if shell == "zsh":
        return Path.home() / ".zfunc" / "_recozik"
    if shell == "fish":
        return Path.home() / ".config/fish/completions/recozik.fish"
    if shell in {"powershell", "pwsh"}:
        return _powershell_profile_path(shell)
    return None


def _powershell_profile_path(shell: str) -> Optional[Path]:
    shell_bin = "pwsh" if shell == "pwsh" else "powershell"
    try:
        result = subprocess.run(
            [shell_bin, "-NoProfile", "-Command", "echo", "$profile"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:  # pragma: no cover - dépend de l'environnement
        return None

    output = result.stdout.decode().strip()
    if not output:
        return None
    return Path(output)


def _completion_uninstall_hint(shell: str) -> str:
    if shell == "bash":
        return (
            "Si besoin, supprimez la ligne `source ~/.bash_completions/recozik.sh` de votre ~/.bashrc."
        )
    if shell == "zsh":
        return (
            "Vérifiez votre ~/.zshrc et retirez la ligne ajoutant ~/.zfunc si vous ne l'utilisez plus."
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


def _resolve_template(template: Optional[str], config: AppConfig) -> str:
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
        if not entry.startswith('.'):
            entry = f'.{entry}'
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
    error: Optional[str],
    template: str,
    fingerprint: Optional[FingerprintResult],
) -> None:
    if log_format == "jsonl":
        entry = {
            "path": path_display,
            "duration_seconds": fingerprint.duration_seconds if fingerprint else None,
            "error": error,
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
                }
                for idx, match in enumerate(matches, start=1)
            ],
        }
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return

    handle.write(f"file: {path_display}\n")
    if fingerprint:
        handle.write(f"  duration: {fingerprint.duration_seconds:.2f}s\n")
    if error:
        handle.write(f"  error: {error}\n\n")
        return

    for idx, match in enumerate(matches, start=1):
        formatted = _format_match_template(match, template)
        handle.write(f"  {idx}. {formatted} (score {match.score:.2f})\n")
    handle.write("\n")


@config_app.command("path")
def config_path(config_path: Optional[Path] = typer.Option(None, "--config-path", hidden=True)) -> None:
    """Affiche le chemin du fichier de configuration utilisé."""

    target = config_path or default_config_path()
    typer.echo(str(target))


@config_app.command("show")
def config_show(config_path: Optional[Path] = typer.Option(None, "--config-path", hidden=True)) -> None:
    """Affiche les informations principales de la configuration."""

    target = config_path or default_config_path()
    try:
        config = load_config(target)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    key = config.acoustid_api_key
    if key:
        masked = key[:4] + "…" + key[-4:] if len(key) > 8 else "…" * len(key)
        typer.echo(f"Clé AcoustID: {masked}")
    else:
        typer.echo("Clé AcoustID: non configurée")
        typer.echo(
            "Créez ou mettez à jour votre clé avec `recozik config set-key`."
        )
    typer.echo(f"Cache activé: {'oui' if config.cache_enabled else 'non'} (TTL: {config.cache_ttl_hours} h)")
    template = config.output_template or "{artist} - {title}"
    typer.echo(f"Template par défaut: {template}")
    typer.echo(
        f"Format du log: {config.log_format} (chemins {'absolus' if config.log_absolute_paths else 'relatifs'})"
    )
    typer.echo(f"Fichier: {target}")


@config_app.command("set-key")
def config_set_key(
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        prompt="Clé API AcoustID",
        hide_input=True,
        confirmation_prompt=True,
        help="Clé obtenue sur https://acoustid.org/api-key",
    ),
    config_path: Optional[Path] = typer.Option(None, "--config-path", hidden=True),
) -> None:
    """Enregistre la clé d'API AcoustID dans le fichier de configuration."""

    key = (api_key or "").strip()
    if not key:
        typer.echo("Aucune clé API fournie.")
        raise typer.Exit(code=1)

    target_path = config_path or default_config_path()
    try:
        existing = load_config(target_path)
    except RuntimeError:
        existing = AppConfig()

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

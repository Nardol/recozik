"""Interactive prompt helpers for CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
import typer

from ..i18n import _
from .logs import format_score


def prompt_yes_no(message: str, *, default: bool = True, require_answer: bool = False) -> bool:
    """Display a yes/no prompt compatible with multiple locales."""
    suffix = _("[y/N]") if not default else _("[Y/n]")
    prompt = f"{message} {suffix}"
    default_char = "y" if default else "n"

    while True:
        response = typer.prompt(prompt, default=default_char, show_default=False)
        if not response:
            if require_answer:
                typer.echo(_("Invalid input (y/n)."))
                continue
            return default
        normalized = response.strip().lower()
        if normalized in {"o", "oui", "y", "yes"}:
            return True
        if normalized in {"n", "non", "no"}:
            return False
        typer.echo(_("Invalid input (y/n)."))


def prompt_api_key() -> str | None:
    """Prompt the user for an AcoustID API key."""
    key = typer.prompt(_("AcoustID API key"), show_default=False).strip()
    if not key:
        return None
    confirmation = typer.prompt(_("Confirm the key"), default=key, show_default=False).strip()
    if confirmation != key:
        typer.echo(_("The keys do not match."))
        return None
    return key


def prompt_interactive_interrupt_decision(has_planned: bool) -> str:
    """Handle interrupts during interactive rename selection."""
    typer.echo(_("Interrupt received during interactive selection."))
    typer.echo(_("  1. Cancel everything and exit."))
    typer.echo(_("  2. Stop asking questions and apply the confirmed renames."))
    typer.echo(_("  3. Resume the current question."))
    choices = {"1": "cancel", "2": "apply", "3": "resume"}
    prompt = _("Choose an option: ")

    while True:
        try:
            selection = typer.prompt(prompt, show_default=False).strip()
        except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
            typer.echo(_("Use the menu to continue."))
            continue

        if selection in choices:
            if selection == "2" and not has_planned:
                typer.echo(_("No rename has been confirmed yet, nothing to apply."))
                continue
            return choices[selection]

        typer.echo(_("Invalid option, please try again."))


def prompt_rename_interrupt_decision(remaining: int) -> str:
    """Handle interrupts once the rename stage has started."""
    typer.echo(
        _("Renaming is in progress. {remaining} file(s) still need to be processed.").format(
            remaining=remaining
        )
    )
    typer.echo(_("  1. Stop now (remaining files will stay unchanged)."))
    typer.echo(_("  2. Continue renaming the remaining files."))
    prompt = _("Choose an option: ")
    choices = {"1": "cancel", "2": "continue"}

    while True:
        try:
            selection = typer.prompt(prompt, default="2", show_default=False).strip()
        except (typer.Abort, KeyboardInterrupt, click.exceptions.Abort):
            typer.echo(_("Please confirm how you want to proceed."))
            continue

        if selection in choices:
            return choices[selection]

        typer.echo(_("Invalid option, please try again."))


def prompt_match_selection(matches: list[dict], source_path: Path) -> int | None:
    """Prompt the user to select a match among multiple proposals."""
    typer.echo(_("Multiple proposals for {name}:").format(name=source_path.name))
    for idx, match in enumerate(matches, start=1):
        artist = match.get("artist") or _("Unknown artist")
        title = match.get("title") or _("Unknown title")
        score = format_score(match.get("score"))
        typer.echo(
            _("  {index}. {artist} - {title} (score {score})").format(
                index=idx,
                artist=artist,
                title=title,
                score=score,
            )
        )

    prompt = _("Select a number (press ENTER to cancel): ")

    while True:
        choice = typer.prompt(prompt, default="", show_default=False).strip()
        if not choice:
            return None

        try:
            idx = int(choice)
        except ValueError:
            typer.echo(_("Invalid selection, please try again."))
            continue

        if 1 <= idx <= len(matches):
            return idx - 1

        typer.echo(_("Index out of range, please try again."))

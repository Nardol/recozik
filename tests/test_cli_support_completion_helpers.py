"""Unit tests for CLI completion helper utilities."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from recozik_services.cli_support import completion as service_completion

from recozik.cli_support import completion


class _StubDetector:
    def __init__(self, shell: str | None, raise_error: bool = False) -> None:
        self._shell = shell
        self._raise = raise_error

    def detect_shell(self) -> tuple[str, Path | None]:
        if self._raise:
            raise RuntimeError("boom")
        assert self._shell is not None
        return self._shell, None


def test_normalize_shell_aliases() -> None:  # noqa: D103
    assert completion.normalize_shell("  bash  ") == "bash"
    assert completion.normalize_shell("PowerShell") == "pwsh"
    assert completion.normalize_shell("PwSh") == "pwsh"
    assert completion.normalize_shell("") is None
    assert completion.normalize_shell("auto") is None


def test_detect_shell_prefers_explicit_value(monkeypatch) -> None:  # noqa: D103
    detector = _StubDetector("zsh")
    assert completion.detect_shell("bash", detector=detector) == "bash"


def test_detect_shell_uses_detector(monkeypatch) -> None:  # noqa: D103
    detector = _StubDetector("ZSH")
    assert completion.detect_shell(None, detector=detector) == "zsh"


def test_detect_shell_respects_disable_env(monkeypatch) -> None:  # noqa: D103
    detector = _StubDetector("bash")
    monkeypatch.setenv("_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION", "1")
    assert completion.detect_shell(None, detector=detector) is None


def test_detect_shell_handles_detector_errors() -> None:  # noqa: D103
    detector = _StubDetector("bash", raise_error=True)
    assert completion.detect_shell(None, detector=detector) is None


def test_completion_source_command_per_shell(tmp_path) -> None:  # noqa: D103
    script = tmp_path / "recozik.sh"
    assert completion.completion_source_command("bash", script) == f"source {script}"
    assert completion.completion_source_command("zsh", script) == f"source {script}"
    assert completion.completion_source_command("fish", script) == f"source {script}"
    assert completion.completion_source_command("pwsh", script) == f". {script}"
    assert completion.completion_source_command("powershell", script) == f". {script}"
    assert completion.completion_source_command("tcsh", script) is None


def test_completion_hint_includes_command(tmp_path) -> None:  # noqa: D103
    script = tmp_path / "comp.sh"
    hint = completion.completion_hint("bash", script)
    assert str(script) in hint
    assert "profile" in hint.lower()


def test_completion_script_path_respects_home(monkeypatch, tmp_path) -> None:  # noqa: D103
    monkeypatch.setattr(service_completion.Path, "home", lambda: tmp_path)
    expected_fish = tmp_path / ".config/fish/completions/recozik.fish"
    assert completion.completion_script_path("fish") == expected_fish
    assert completion.completion_script_path("zsh") == tmp_path / ".zfunc" / "_recozik"


def test_completion_script_path_powershell(monkeypatch, tmp_path) -> None:  # noqa: D103
    target = tmp_path / "profile.ps1"
    monkeypatch.setattr(service_completion, "powershell_profile_path", lambda shell: target)
    assert completion.completion_script_path("pwsh") == target


def test_powershell_profile_path_success(monkeypatch, tmp_path) -> None:  # noqa: D103
    expected = tmp_path / "Microsoft.PowerShell_profile.ps1"

    def fake_run(command, check, capture_output, text):
        assert command[0] in {"pwsh", "powershell"}
        return SimpleNamespace(stdout=str(expected) + "\n")

    monkeypatch.setattr(service_completion.subprocess, "run", fake_run)
    assert completion.powershell_profile_path("pwsh") == expected


def test_powershell_profile_path_missing(monkeypatch) -> None:  # noqa: D103
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(service_completion.subprocess, "run", fake_run)
    assert completion.powershell_profile_path("pwsh") is None


def test_completion_uninstall_hint_fallback() -> None:  # noqa: D103
    message = completion.completion_uninstall_hint("unknown-shell")
    assert "Completion" in message

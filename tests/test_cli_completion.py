"""Tests for the CLI completion subcommands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from recozik import cli


def test_completion_install(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Install the completion script for an explicit shell."""
    script_path = tmp_path / "recozik-completion.sh"

    def fake_install(shell=None, prog_name=None, complete_var=None):
        assert shell == "bash"
        assert prog_name == "recozik"
        return "bash", script_path

    monkeypatch.setattr(cli, "install_completion", fake_install)

    result = cli_runner.invoke(cli.app, ["completion", "install", "--shell", "bash"])

    assert result.exit_code == 0
    assert "Completion installed for bash." in result.stdout
    assert str(script_path) in result.stdout
    assert "Command to add" in result.stdout


def test_completion_show(monkeypatch, cli_runner: CliRunner) -> None:
    """Show the generated completion script for the detected shell."""

    def fake_detect_shell(shell_option):
        return "zsh"

    def fake_script(*, prog_name, complete_var, shell):
        assert prog_name == "recozik"
        assert complete_var == "_RECOZIK_COMPLETE"
        assert shell == "zsh"
        return "#comp"

    monkeypatch.setattr(cli, "_detect_shell", lambda shell: "zsh")
    monkeypatch.setattr(cli, "generate_completion_script", fake_script)

    result = cli_runner.invoke(cli.app, ["completion", "show"])

    assert result.exit_code == 0
    assert "#comp" in result.stdout


def test_completion_uninstall(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Remove the existing completion script for the detected shell."""
    target_script = tmp_path / "script"
    target_script.write_text("echo")

    monkeypatch.setattr(cli, "_detect_shell", lambda shell: "bash")
    monkeypatch.setattr(cli, "_completion_script_path", lambda shell: target_script)

    result = cli_runner.invoke(cli.app, ["completion", "uninstall"])

    assert result.exit_code == 0
    assert "Completion script removed" in result.stdout
    assert not target_script.exists()


def test_completion_install_print_command(
    monkeypatch, tmp_path: Path, cli_runner: CliRunner
) -> None:
    """Print the sourcing command instead of writing the script to disk."""
    script_path = tmp_path / "recozik.sh"

    monkeypatch.setattr(
        cli,
        "install_completion",
        lambda shell=None, prog_name=None: ("bash", script_path),
    )

    result = cli_runner.invoke(
        cli.app,
        ["completion", "install", "--shell", "bash", "--print-command"],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == f"source {script_path}"


def test_completion_install_no_write(monkeypatch, cli_runner: CliRunner) -> None:
    """Return the generated script when --no-write is used."""
    monkeypatch.setattr(
        cli,
        "install_completion",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("install should not be called")),
    )
    monkeypatch.setattr(cli, "generate_completion_script", lambda **kwargs: "# script")

    result = cli_runner.invoke(
        cli.app,
        ["completion", "install", "--shell", "bash", "--no-write"],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "# script"


def test_completion_install_shell_auto(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Detect the shell automatically when "auto" is provided."""
    script_path = tmp_path / "recozik.zsh"

    captured = {}

    def fake_install(shell=None, prog_name=None, complete_var=None):
        captured["shell"] = shell
        return "zsh", script_path

    monkeypatch.setattr(cli, "install_completion", fake_install)

    result = cli_runner.invoke(
        cli.app,
        ["completion", "install", "--shell", "auto"],
    )

    assert result.exit_code == 0
    assert captured["shell"] is None


def test_completion_install_output(monkeypatch, tmp_path: Path, cli_runner: CliRunner) -> None:
    """Write the generated script to a custom location."""
    target = tmp_path / "custom" / "script.sh"

    monkeypatch.setattr(
        cli,
        "install_completion",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("install should not be called")),
    )
    monkeypatch.setattr(
        cli,
        "generate_completion_script",
        lambda **kwargs: "# out",
    )

    result = cli_runner.invoke(
        cli.app,
        [
            "completion",
            "install",
            "--shell",
            "bash",
            "--output",
            str(target),
        ],
    )

    assert result.exit_code == 0
    assert target.read_text() == "# out"
    assert "Completion script written" in result.stdout


def test_completion_install_conflicting_flags(tmp_path: Path, cli_runner: CliRunner) -> None:
    """Refuse to combine --no-write and --print-command flags."""
    result = cli_runner.invoke(
        cli.app,
        [
            "completion",
            "install",
            "--shell",
            "bash",
            "--no-write",
            "--print-command",
        ],
    )

    assert result.exit_code == 1
    assert "Use only one of" in result.stdout

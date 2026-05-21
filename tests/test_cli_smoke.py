from __future__ import annotations

from typer.testing import CliRunner

from mokioclaw.cli.app import app


def test_cli_shows_help_without_task() -> None:
    runner = CliRunner()

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "mokioclaw" in result.output


def test_cli_accepts_max_attempts_option_without_task() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--max-attempts", "2"])

    assert result.exit_code == 0
    assert "mokioclaw" in result.output


def test_cli_accepts_approval_mode_option_without_task() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--approval-mode", "deny"])

    assert result.exit_code == 0
    assert "mokioclaw" in result.output

from __future__ import annotations

from typer.testing import CliRunner

from traderbot.cli import app

from tests.conftest import strip_ansi

runner = CliRunner()


class TestSandboxHelp:
    def test_sandbox_help_succeeds(self) -> None:
        result = runner.invoke(app, ["sandbox", "--help"])
        assert result.exit_code == 0
        assert "sandbox" in result.output.lower()

    def test_sandbox_enter_help(self) -> None:
        result = runner.invoke(app, ["sandbox", "enter", "--help"])
        assert result.exit_code == 0

    def test_sandbox_exit_help(self) -> None:
        result = runner.invoke(app, ["sandbox", "exit", "--help"])
        assert result.exit_code == 0
        assert "--json" in strip_ansi(result.output)

    def test_sandbox_status_help(self) -> None:
        result = runner.invoke(app, ["sandbox", "status", "--help"])
        assert result.exit_code == 0
        assert "--json" in strip_ansi(result.output)

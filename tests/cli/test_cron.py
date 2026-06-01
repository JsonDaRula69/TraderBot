from __future__ import annotations

from typer.testing import CliRunner

from traderbot.cli import app

runner = CliRunner()


class TestCronHelp:
    def test_cron_help_succeeds(self) -> None:
        result = runner.invoke(app, ["cron", "--help"])
        assert result.exit_code == 0
        assert "cron" in result.output.lower() or "setup" in result.output.lower()

    def test_setup_heartbeat_tasks_help(self) -> None:
        result = runner.invoke(app, ["cron", "setup-heartbeat-tasks", "--help"])
        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--role" in result.output

    def test_remove_heartbeat_tasks_help(self) -> None:
        result = runner.invoke(app, ["cron", "remove-heartbeat-tasks", "--help"])
        assert result.exit_code == 0
        assert "--agent" in result.output

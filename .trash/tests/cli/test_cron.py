from __future__ import annotations

from typer.testing import CliRunner

from traderbot.cli import app

from tests.conftest import strip_ansi

runner = CliRunner()


class TestCronHelp:
    def test_cron_help_succeeds(self) -> None:
        result = runner.invoke(app, ["cron", "--help"])
        assert result.exit_code == 0
        assert "cron" in result.output.lower() or "setup" in result.output.lower()

    def test_setup_heartbeat_tasks_help(self) -> None:
        result = runner.invoke(app, ["cron", "setup", "--help"])
        assert result.exit_code == 0
        assert "--agent" in strip_ansi(result.output)
        assert "--role" in strip_ansi(result.output)

    def test_cron_setup_role_sysadmin_help(self) -> None:
        result = runner.invoke(app, ["cron", "setup", "--help"])
        assert result.exit_code == 0
        assert "--role" in strip_ansi(result.output)


class TestSysadminCronNoDuplicates:
    """Regression: _SYSADMIN_CRON_JOBS must not contain duplicate names."""

    def test_sysadmin_cron_jobs_no_duplicate_names(self) -> None:
        from traderbot.cli.cron import _SYSADMIN_CRON_JOBS

        names = [j["name"] for j in _SYSADMIN_CRON_JOBS]
        assert len(names) == len(set(names)), (
            f"Duplicate cron job names: {[n for n in names if names.count(n) > 1]}"
        )


class TestRemoveNewsIngestTimerUsesAgentUser:
    """Regression: _remove_news_ingest_timer must use agent_user, not agent_id.

    Bug: the function parameter was named agent_id but should be agent_user,
    matching the install function signature and systemd unit file naming.
    """

    def test_remove_news_ingest_timer_uses_agent_user(self) -> None:
        import inspect

        from traderbot.cli.cron import _remove_news_ingest_timer

        source = inspect.getsource(_remove_news_ingest_timer)
        assert "agent_user" in source, "Function must use agent_user parameter"
        assert "agent_id" not in source, "Function must not reference agent_id"

    def test_install_news_ingest_timer_uses_agent_user(self) -> None:
        import inspect

        from traderbot.cli.cron import _install_news_ingest_timer

        source = inspect.getsource(_install_news_ingest_timer)
        assert "agent_user" in source, "Function must use agent_user parameter"

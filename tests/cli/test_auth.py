from __future__ import annotations

from typer.testing import CliRunner

from traderbot.cli import app

from tests.conftest import strip_ansi

runner = CliRunner()


class TestAuthHelp:
    def test_auth_help_succeeds(self) -> None:
        result = runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "Manage API credentials" in strip_ansi(result.output)

    def test_list_keys_help(self) -> None:
        result = runner.invoke(app, ["auth", "list-keys", "--help"])
        assert result.exit_code == 0
        assert "list-keys" in result.output.lower() or "List configured services" in result.output

    def test_rotate_help(self) -> None:
        result = runner.invoke(app, ["auth", "rotate", "--help"])
        assert result.exit_code == 0
        assert "rotate" in result.output.lower()

    def test_check_help(self) -> None:
        result = runner.invoke(app, ["auth", "check", "--help"])
        assert result.exit_code == 0

    def test_setup_master_password_help(self) -> None:
        result = runner.invoke(app, ["auth", "setup-master-password", "--help"])
        assert result.exit_code == 0
        assert "master" in result.output.lower()

    def test_change_master_password_help(self) -> None:
        result = runner.invoke(app, ["auth", "change-master-password", "--help"])
        assert result.exit_code == 0

    def test_check_master_password_help(self) -> None:
        result = runner.invoke(app, ["auth", "check-master-password", "--help"])
        assert result.exit_code == 0

    def test_set_kalshi_help(self) -> None:
        result = runner.invoke(app, ["auth", "set-kalshi", "--help"])
        assert result.exit_code == 0
        assert "kalshi" in result.output.lower()

    def test_migrate_help(self) -> None:
        result = runner.invoke(app, ["auth", "migrate", "--help"])
        assert result.exit_code == 0

    def test_delete_key_help(self) -> None:
        result = runner.invoke(app, ["auth", "delete-key", "--help"])
        assert result.exit_code == 0

    def test_clear_session_help(self) -> None:
        result = runner.invoke(app, ["auth", "clear-session", "--help"])
        assert result.exit_code == 0


class TestAuthListKeys:
    def test_list_keys_no_credentials(self) -> None:
        result = runner.invoke(app, ["auth", "list-keys"])
        assert result.exit_code == 0


class TestAuthCheckValidateFlag:
    """Regression: auth check must accept --validate flag.

    Bug: the --validate flag was missing from the auth check command,
    preventing credential validation against the live Kalshi API.
    """

    def test_auth_check_validate_flag_in_help(self) -> None:
        result = runner.invoke(app, ["auth", "check", "--help"])
        assert result.exit_code == 0
        assert "--validate" in strip_ansi(result.output)

    def test_auth_check_validate_json_output(self) -> None:
        result = runner.invoke(app, ["auth", "check", "--validate", "--json"])
        assert result.exit_code == 0

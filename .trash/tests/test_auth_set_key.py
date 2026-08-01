"""Tests for `traderbot auth set-key` command."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from tests.conftest import strip_ansi
from traderbot.auth import _ALL_SERVICES
from traderbot.cli import app

runner = CliRunner()


class TestSetKeyHelpAndValidation:
    def test_set_key_help(self) -> None:
        result = runner.invoke(app, ["auth", "set-key", "--help"])
        assert result.exit_code == 0
        assert "set-key" in result.output.lower()

    def test_rejects_kalshi(self) -> None:
        result = runner.invoke(app, ["auth", "set-key", "kalshi", "api_key", "--value", "dummy"])
        assert result.exit_code == 1
        assert "set-kalshi" in strip_ansi(result.output)

    def test_rejects_unknown_service(self) -> None:
        result = runner.invoke(app, ["auth", "set-key", "nonexistent", "api_key", "--value", "x"])
        assert result.exit_code == 1
        assert "Unknown service" in strip_ansi(result.output)

    def test_rejects_unknown_key_for_valid_service(self) -> None:
        result = runner.invoke(app, ["auth", "set-key", "newsapi", "ssh_key", "--value", "x"])
        assert result.exit_code == 1
        assert "Unknown key" in strip_ansi(result.output)
        assert "api_key" in strip_ansi(result.output)

    def test_tier_only_valid_for_coingecko(self) -> None:
        result = runner.invoke(
            app, ["auth", "set-key", "newsapi", "api_key", "--value", "x", "--tier", "pro"]
        )
        assert result.exit_code == 1
        assert "only valid for service 'coingecko'" in strip_ansi(result.output)

    def test_tier_only_valid_with_api_key(self) -> None:
        result = runner.invoke(
            app, ["auth", "set-key", "coingecko", "tier", "--value", "pro", "--tier", "pro"]
        )
        assert result.exit_code == 1
        assert "only valid with key 'api_key'" in strip_ansi(result.output)


class TestSetKeyNonInteractive:
    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_credential_for_newsapi(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "newsapi", "api_key", "--value", "sk-abc123"]
        )
        assert result.exit_code == 0
        mock_set.assert_any_call("newsapi", "api_key", "sk-abc123")
        assert "newsapi.api_key stored in env" in strip_ansi(result.output)

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_credential_for_voyage(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "voyage", "api_key", "--value", "voy-xyz"])
        assert result.exit_code == 0
        mock_set.assert_any_call("voyage", "api_key", "voy-xyz")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_credential_for_twitter(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "twitter", "api_key", "--value", "tw-xyz"])
        assert result.exit_code == 0
        mock_set.assert_any_call("twitter", "api_key", "tw-xyz")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_reddit_client_id(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "reddit", "client_id", "--value", "my-app-id"]
        )
        assert result.exit_code == 0
        mock_set.assert_any_call("reddit", "client_id", "my-app-id")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_reddit_client_secret(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "reddit", "client_secret", "--value", "sec-abc"]
        )
        assert result.exit_code == 0
        mock_set.assert_any_call("reddit", "client_secret", "sec-abc")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_openweathermap(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "openweathermap", "api_key", "--value", "owm-key"]
        )
        assert result.exit_code == 0
        mock_set.assert_any_call("openweathermap", "api_key", "owm-key")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_fred(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "fred", "api_key", "--value", "fred-key"])
        assert result.exit_code == 0
        mock_set.assert_any_call("fred", "api_key", "fred-key")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_coingecko_with_tier(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "coingecko", "api_key", "--value", "cg-key", "--tier", "pro"]
        )
        assert result.exit_code == 0
        mock_set.assert_any_call("coingecko", "api_key", "cg-key")
        mock_set.assert_any_call("coingecko", "tier", "pro")
        assert "coingecko.tier (pro) stored in env" in strip_ansi(result.output)

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_coingecko_with_demo_tier(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "coingecko", "api_key", "--value", "cg-key", "--tier", "demo"]
        )
        assert result.exit_code == 0
        mock_set.assert_any_call("coingecko", "tier", "demo")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_stores_coingecko_without_tier(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(
            app, ["auth", "set-key", "coingecko", "api_key", "--value", "cg-key"]
        )
        assert result.exit_code == 0
        mock_set.assert_called_once_with("coingecko", "api_key", "cg-key")

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_warns_on_non_interactive_value(self, mock_set: patch) -> None:
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "newsapi", "api_key", "--value", "key"])
        assert result.exit_code == 0
        assert "Warning" in strip_ansi(result.output)
        assert "CLI argument" in strip_ansi(result.output)

    @patch("traderbot.auth.AuthManager.set_credential")
    def test_keyring_source_reported(self, mock_set: patch) -> None:
        mock_set.return_value = "keyring"
        result = runner.invoke(app, ["auth", "set-key", "fred", "api_key", "--value", "fred-key"])
        assert result.exit_code == 0
        assert "stored in keyring" in strip_ansi(result.output)


class TestSetKeyInteractive:
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("typer.prompt")
    def test_prompts_for_api_key_with_hidden_input(
        self, mock_prompt: patch, mock_set: patch
    ) -> None:
        mock_prompt.return_value = "my-secret-key"
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "newsapi", "api_key"])
        assert result.exit_code == 0
        mock_prompt.assert_called_once()
        _, kwargs = mock_prompt.call_args
        assert kwargs["hide_input"] is True

    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("typer.prompt")
    def test_prompts_for_client_secret_with_hidden_input(
        self, mock_prompt: patch, mock_set: patch
    ) -> None:
        mock_prompt.return_value = "my-secret"
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "reddit", "client_secret"])
        assert result.exit_code == 0
        _, kwargs = mock_prompt.call_args
        assert kwargs["hide_input"] is True

    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("typer.prompt")
    def test_prompts_for_client_id_with_visible_input(
        self, mock_prompt: patch, mock_set: patch
    ) -> None:
        mock_prompt.return_value = "my-app-id"
        mock_set.return_value = "env"
        result = runner.invoke(app, ["auth", "set-key", "reddit", "client_id"])
        assert result.exit_code == 0
        _, kwargs = mock_prompt.call_args
        assert kwargs["hide_input"] is False


def test_all_services_excluding_kalshi() -> None:
    """Verify all 7 non-Kalshi services referenced by the installer are present."""
    expected = {"newsapi", "voyage", "twitter", "reddit", "coingecko", "openweathermap", "fred"}
    non_kalshi = set(_ALL_SERVICES.keys()) - {"kalshi"}
    assert non_kalshi == expected, f"Missing or extra services: {non_kalshi ^ expected}"

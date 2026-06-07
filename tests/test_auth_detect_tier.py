"""Tests for `traderbot auth detect-tier` command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tests.conftest import strip_ansi
from traderbot.cli import app

runner = CliRunner()


class TestDetectTierHelp:
    def test_detect_tier_help(self) -> None:
        result = runner.invoke(app, ["auth", "detect-tier", "--help"])
        assert result.exit_code == 0
        assert "detect-tier" in result.output.lower()
        assert "--json" in result.output
        assert "--dry-run" in result.output


class TestDetectTierNoKey:
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_no_key_configured(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        result = runner.invoke(app, ["auth", "detect-tier"])
        assert result.exit_code == 1
        assert "No CoinGecko API key configured" in strip_ansi(result.output)

    @patch("traderbot.auth.AuthManager.get_credential")
    def test_no_key_json_output(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        result = runner.invoke(app, ["auth", "detect-tier", "--json"])
        assert result.exit_code == 1
        output = json.loads(strip_ansi(result.output))
        assert "error" in output
        assert "No CoinGecko API key configured" in output["error"]


class TestDetectTierPro:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_detects_pro(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )
        mock_set.return_value = "keyring"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.return_value = mock_response

        result = runner.invoke(app, ["auth", "detect-tier"])
        assert result.exit_code == 0
        assert "pro" in strip_ansi(result.output)
        mock_set.assert_called_once_with("coingecko", "tier", "pro")


class TestDetectTierDemo:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_detects_demo(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )
        mock_set.return_value = "env"

        pro_resp = MagicMock()
        pro_resp.status_code = 401
        demo_resp = MagicMock()
        demo_resp.status_code = 200
        mock_httpx.side_effect = [pro_resp, demo_resp]

        result = runner.invoke(app, ["auth", "detect-tier"])
        assert result.exit_code == 0
        assert "demo" in strip_ansi(result.output)
        mock_set.assert_called_once_with("coingecko", "tier", "demo")


class TestDetectTierFree:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_detects_free(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )
        mock_set.return_value = "env"

        pro_resp = MagicMock()
        pro_resp.status_code = 401
        demo_resp = MagicMock()
        demo_resp.status_code = 401
        free_resp = MagicMock()
        free_resp.status_code = 200
        mock_httpx.side_effect = [pro_resp, demo_resp, free_resp]

        result = runner.invoke(app, ["auth", "detect-tier"])
        assert result.exit_code == 0
        assert "free" in strip_ansi(result.output)
        mock_set.assert_called_once_with("coingecko", "tier", "free")


class TestDetectTierAllFail:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_all_endpoints_fail(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )

        pro_resp = MagicMock()
        pro_resp.status_code = 500
        demo_resp = MagicMock()
        demo_resp.status_code = 500
        free_resp = MagicMock()
        free_resp.status_code = 500
        mock_httpx.side_effect = [pro_resp, demo_resp, free_resp]

        result = runner.invoke(app, ["auth", "detect-tier"])
        assert result.exit_code == 1
        assert "Unable to determine" in strip_ansi(result.output)
        mock_set.assert_not_called()


class TestDetectTierDryRun:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_dry_run_detects_but_does_not_store(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.return_value = mock_response

        result = runner.invoke(app, ["auth", "detect-tier", "--dry-run"])
        assert result.exit_code == 0
        assert "pro" in strip_ansi(result.output)
        assert "dry-run" in strip_ansi(result.output)
        mock_set.assert_not_called()


class TestDetectTierJsonOutput:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_json_output(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )
        mock_set.return_value = "keyring"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.return_value = mock_response

        result = runner.invoke(app, ["auth", "detect-tier", "--json"])
        assert result.exit_code == 0
        output = json.loads(strip_ansi(result.output))
        assert output["tier"] == "pro"
        assert output["stored"] is True
        assert output["source"] == "keyring"

    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_json_output_dry_run(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="env",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.return_value = mock_response

        result = runner.invoke(app, ["auth", "detect-tier", "--json", "--dry-run"])
        assert result.exit_code == 0
        output = json.loads(strip_ansi(result.output))
        assert output["tier"] == "pro"
        assert output["stored"] is False
        assert output["source"] is None


class TestDetectTierStoresTier:
    @patch("httpx.get")
    @patch("traderbot.auth.AuthManager.set_credential")
    @patch("traderbot.auth.AuthManager.get_credential")
    def test_stores_detected_tier(
        self, mock_get: MagicMock, mock_set: MagicMock, mock_httpx: MagicMock
    ) -> None:
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        mock_get.return_value = CredentialResult(
            service="coingecko",
            key="api_key",
            value=SecretStr("test-api-key"),
            source="keyring",
        )
        mock_set.return_value = "keyring"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.return_value = mock_response

        result = runner.invoke(app, ["auth", "detect-tier"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with("coingecko", "tier", "pro")
        assert "stored in keyring" in strip_ansi(result.output)

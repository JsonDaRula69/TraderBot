"""Focused tests for the Phase 4 deploy foundation CLI and config model."""

import argparse
import os
from pathlib import Path
from unittest import mock

import pytest
from pydantic import TypeAdapter, ValidationError

import traderbot.cli as cli
from traderbot.kalshi.order_models import MarketCategory


def test_deploy_config_parses_documented_shape() -> None:
    # Given: the documented non-interactive deploy payload
    from traderbot.deploy.config import DeployConfig

    payload = {
        "categories": ["weather"],
        "mode": "backtest",
        "infisical_url": "http://localhost:8080",
        "tokens": {
            "kalshi_api_key_env": "TEST_KALSHI_KEY",
            "kalshi_private_key_pem_env": "TEST_KALSHI_PEM",
        },
        "months_backfill": 6,
        "category_workspaces": {"weather": "/srv/openclaw/weather"},
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": True,
            "heartbeat_change": True,
        },
        "heartbeat_every": "0m",
    }

    # When: the external payload crosses the config boundary
    config = DeployConfig.model_validate(payload)

    # Then: category and mode values are parsed into the supported domain
    assert config.categories == ["weather"]
    assert config.mode == "backtest"
    assert config.tokens.kalshi_api_key_env == "TEST_KALSHI_KEY"


def test_deploy_config_requires_explicit_approval_and_heartbeat_fields() -> None:
    # Given: config mode omits both explicit approval-bearing fields
    from traderbot.deploy.config import DeployConfig

    # When/Then: the noninteractive trust boundary fails instead of assuming approval
    with pytest.raises(ValidationError):
        _ = DeployConfig.model_validate(
            {"categories": [MarketCategory.WEATHER], "mode": "backtest"}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("categories", ["invalid"]), ("mode", "invalid")],
)
def test_deploy_config_rejects_invalid_category_or_mode(field: str, value: str | list[str]) -> None:
    # Given: a deploy payload containing an unsupported domain value
    from traderbot.deploy.config import DeployConfig

    payload = {
        "categories": ["weather"],
        "mode": "backtest",
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": False,
            "heartbeat_change": False,
        },
        "heartbeat_every": "preserve",
        field: value,
    }

    # When/Then: Pydantic rejects the malformed boundary input
    with pytest.raises(ValidationError):
        _ = DeployConfig.model_validate(payload)


def test_profile_create_prints_deterministic_json(capsys: pytest.CaptureFixture[str]) -> None:
    # Given/When: a valid profile is created through the CLI
    exit_code = cli.main(
        ["profile", "create", "test", "--mode", "backtest", "--categories", "weather"]
    )
    output = capsys.readouterr()

    # Then: stdout is one JSON document with the requested domain values
    assert exit_code == 0
    payload = TypeAdapter(dict[str, object]).validate_json(output.out)
    assert payload["name"] == "test"
    assert payload["mode"] == "backtest"
    assert payload["enabled_categories"] == ["weather"]
    assert output.err == ""


def test_profile_create_rejects_invalid_category_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an isolated data root and an invalid market category
    data_dir = tmp_path / "data"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_dir))

    # When: argparse validates the command boundary
    with pytest.raises(SystemExit) as raised:
        _ = cli.main(["profile", "create", "test", "--mode", "backtest", "--categories", "invalid"])
    output = capsys.readouterr()

    # Then: the error is actionable and no state was created
    assert raised.value.code != 0
    assert "invalid" in output.err
    assert "category" in output.err.lower()
    assert data_dir.exists() is False


def test_auth_check_json_reports_exact_missing_token(capsys: pytest.CaptureFixture[str]) -> None:
    # Given/When: auth is checked without supplying a token
    exit_code = cli.main(["auth", "check", "--json"])
    output = capsys.readouterr()

    # Then: the documented machine-readable failure is exact
    assert exit_code == 1
    assert output.out == '{"status":"error","error":"no token"}\n'
    assert output.err == ""


@pytest.mark.parametrize(
    ("command", "handler_name"),
    [("deploy", "_cmd_deploy"), ("backfill", "_cmd_backfill")],
)
def test_foundation_stub_sets_real_auth_before_handler(
    command: str,
    handler_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: hardcoded auth enabled and an observable command handler
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")
    observed: list[str | None] = []

    def handler(_args: argparse.Namespace) -> int:
        observed.append(os.environ.get("TRADERBOT_USE_HARDCODED_AUTH"))
        return 0

    monkeypatch.setattr(cli, handler_name, handler)

    # When: the foundation subcommand is invoked
    exit_code = cli.main([command])

    # Then: real auth was selected before control reached its handler
    assert exit_code == 0
    assert observed == ["0"]


def test_deploy_cli_forwards_config_and_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an observable deploy command boundary
    config_path = tmp_path / "deploy.json"
    execute = mock.Mock(return_value=0)
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")
    monkeypatch.setattr(cli, "execute_deploy", execute, raising=False)

    # When: config and JSON mode are selected through the real parser
    code = cli.main(["deploy", "--config", str(config_path), "--json"])

    # Then: the typed path and machine-output flag reach the command layer
    assert code == 0
    execute.assert_called_once_with(config_path, True)

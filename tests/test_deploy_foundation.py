"""Focused tests for the Phase 4 deploy foundation CLI and config model."""

import argparse
import json
import os
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

import traderbot.cli as cli
from traderbot.kalshi.models import MarketCategory


def test_deploy_config_parses_documented_shape() -> None:
    # Given: the documented non-interactive deploy payload
    from traderbot.deploy.config import DeployConfig

    payload = {
        "categories": ["weather"],
        "mode": "backtest",
        "infisical_url": "http://localhost:8080",
        "kalshi_environment": "production",
        "tokens": {
            "kalshi_api_key": "example-key",
            "kalshi_private_key_pem": "example-pem",
        },
        "months_backfill": 6,
    }

    # When: the external payload crosses the config boundary
    config = DeployConfig.model_validate(payload)

    # Then: category and mode values are parsed into the supported domain
    assert config.categories == ["weather"]
    assert config.mode == "backtest"
    assert config.tokens.get("kalshi_api_key") == "example-key"


def test_deploy_config_minimal_defaults_are_isolated() -> None:
    # Given/When: two minimal documented configs are parsed
    from traderbot.deploy.config import DeployConfig

    first = DeployConfig(categories=[MarketCategory.WEATHER], mode="backtest")
    second = DeployConfig(categories=[MarketCategory.WEATHER], mode="backtest")

    # Then: optional connection data and token defaults are safe
    assert first.infisical_url is None
    assert first.tokens == second.tokens
    assert first.tokens is not second.tokens
    assert first.months_backfill == 6


@pytest.mark.parametrize(
    ("field", "value"),
    [("categories", ["invalid"]), ("mode", "invalid")],
)
def test_deploy_config_rejects_invalid_category_or_mode(field: str, value: str | list[str]) -> None:
    # Given: a deploy payload containing an unsupported domain value
    from traderbot.deploy.config import DeployConfig

    payload = {"categories": ["weather"], "mode": "backtest", field: value}

    # When/Then: Pydantic rejects the malformed boundary input
    with pytest.raises(ValidationError):
        DeployConfig.model_validate(payload)


def test_profile_create_prints_deterministic_json(capsys: pytest.CaptureFixture[str]) -> None:
    # Given/When: a valid profile is created through the CLI
    exit_code = cli.main(
        ["profile", "create", "test", "--mode", "backtest", "--categories", "weather"]
    )
    output = capsys.readouterr()

    # Then: stdout is one JSON document with the requested domain values
    assert exit_code == 0
    payload = json.loads(output.out)
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
        _ = cli.main(
            ["profile", "create", "test", "--mode", "backtest", "--categories", "invalid"]
        )
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
    [("deploy", "_cmd_deploy"), ("backfill", "_cmd_backfill"), ("verify", "_cmd_verify")],
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


@pytest.mark.parametrize("command", ["backfill", "verify"])
def test_foundation_commands_are_explicit_stubs(
    command: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given/When: a later-phase command is invoked during Todo 1
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")
    exit_code = cli.main([command])
    output = capsys.readouterr()

    # Then: it succeeds only as an explicit not-yet-implemented stub
    assert exit_code == 0
    assert output.out == f"{command}: not yet implemented\n"
    assert output.err == ""


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

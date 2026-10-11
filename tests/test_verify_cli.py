from __future__ import annotations

import argparse
import json
import os
from typing import final, override

import pytest
from pydantic import SecretStr

from traderbot.cli import main
from traderbot.deploy.verify import VerificationPorts
from traderbot.deploy.verify_command import VerificationCommandOptions, execute_verification
from traderbot.deploy.verify_models import CheckId, ProbeResult, TokenProbe, VerificationResult
from traderbot.deploy.verify_reporter import JsonReporter
from traderbot.kalshi.order_models import MarketCategory


class ReporterCanaryError(Exception):
    pass


@final
class ResultPorts(VerificationPorts):
    __slots__ = ("calls", "canary", "degraded", "failure")

    def __init__(
        self,
        failure: CheckId | None = None,
        degraded: CheckId | None = None,
        canary: str | None = None,
    ) -> None:
        self.failure = failure
        self.degraded = degraded
        self.canary = canary
        self.calls: list[CheckId] = []

    @override
    async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult:
        _ = token
        self.calls.append(check_id)
        if self.canary is not None and check_id is CheckId.GATEWAY:
            raise KeyError(self.canary)
        if check_id is self.failure:
            return ProbeResult.failed("probe_failed", "Probe failed")
        if check_id is self.degraded:
            return ProbeResult.degraded("probe_degraded", "Probe degraded")
        return ProbeResult.passed("probe_passed")

    @override
    async def tokens(self) -> TokenProbe:
        self.calls.append(CheckId.TOKENS)
        return TokenProbe(result=ProbeResult.passed("tokens_exact"), token=SecretStr("token"))


def _options(*, json_output: bool = True) -> VerificationCommandOptions:
    return VerificationCommandOptions.model_validate(
        {
            "categories": (MarketCategory.WEATHER,),
            "mode": "backtest",
            "infisical_origin": "http://localhost:8080",
            "daemon_mcp_url": "http://127.0.0.1:8765/mcp",
            "timeout_seconds": 0.5,
            "json_output": json_output,
        }
    )


def test_json_outcomes_have_one_stdout_line(capsys: pytest.CaptureFixture[str]) -> None:
    # Given
    ports = ResultPorts()

    # When
    exit_code = execute_verification(_options(), ports)

    # Then
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out)["overall"] == "ok"


def test_unexpected_exception_is_sanitized(capsys: pytest.CaptureFixture[str]) -> None:
    # Given
    ports = ResultPorts(canary="SECRET-CANARY")

    # When
    exit_code = execute_verification(_options(), ports)

    # Then
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "SECRET-CANARY" not in captured.out
    assert "SECRET-CANARY" not in captured.err
    assert "check_exception" in captured.out


def test_invalid_request_is_json_and_exit_two(capsys: pytest.CaptureFixture[str]) -> None:
    # Given
    options = _options().model_copy(update={"timeout_seconds": -1.0})

    # When
    exit_code = execute_verification(options, ResultPorts())

    # Then
    captured = capsys.readouterr()
    assert exit_code == 2
    assert len(captured.out.splitlines()) == 1
    assert "invalid_request" in captured.out


def test_cli_help_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    # Given / When
    try:
        _ = main(["verify", "--help"])
    except SystemExit as error:
        exit_code = error.code
    else:
        exit_code = 0

    # Then
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--categories" in captured.out


def test_verify_cli_forces_real_auth_before_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")

    observed: list[str | None] = []

    def handler(_args: argparse.Namespace) -> int:
        observed.append(os.environ.get("TRADERBOT_USE_HARDCODED_AUTH"))
        return 0

    monkeypatch.setattr("traderbot.cli._cmd_verify", handler)

    # When
    exit_code = main(["verify", "--categories", "weather"])

    # Then
    assert exit_code == 0
    assert observed == ["0"]


def test_argparse_failure_is_one_json_stdout_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given / When
    exit_code = main(["verify", "--json", "--categories", "invalid"])

    # Then
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out) == {"error": "invalid_request"}


def test_missing_categories_is_one_json_stdout_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given / When
    exit_code = main(["verify", "--json"])

    # Then
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert json.loads(captured.out)["checks"][0]["action"] == "invalid_request"


def test_reporter_exception_is_sanitized(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    def fail_reporter(_reporter: JsonReporter, _result: VerificationResult) -> None:
        raise ReporterCanaryError("SECRET-CANARY")

    monkeypatch.setattr("traderbot.deploy.verify_command.JsonReporter.render", fail_reporter)

    # When
    exit_code = execute_verification(_options(), ResultPorts())

    # Then
    captured = capsys.readouterr()
    assert exit_code == 1
    assert len(captured.out.splitlines()) == 1
    assert "reporter_failure" in captured.out
    assert "CANARY" not in captured.out + captured.err

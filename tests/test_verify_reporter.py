from __future__ import annotations

import json

import pytest
from rich.console import Console

from traderbot.deploy.verify_models import (
    CheckId,
    CheckResult,
    CheckStatus,
    OverallStatus,
    VerificationResult,
)
from traderbot.deploy.verify_reporter import JsonReporter, RichReporter


def _result() -> VerificationResult:
    return VerificationResult(
        overall=OverallStatus.OK,
        checks=(
            CheckResult(
                id=CheckId.GATEWAY,
                status=CheckStatus.PASS,
                required=True,
                action="healthy",
                message="healthy",
                elapsed_ms=1,
            ),
        ),
    )


def test_json_reporter_writes_exactly_one_stdout_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    reporter = JsonReporter()

    # When
    reporter.render(_result())

    # Then
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["overall"] == "ok"


def test_rich_reporter_uses_stderr_only(capsys: pytest.CaptureFixture[str]) -> None:
    # Given
    reporter = RichReporter(Console(stderr=True, force_terminal=False))

    # When
    reporter.render(_result())

    # Then
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "gateway" in captured.err

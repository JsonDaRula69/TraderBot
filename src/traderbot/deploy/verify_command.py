"""Provide the CLI execution boundary for deployment verification."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import ClassVar

import anyio
from pydantic import BaseModel, ConfigDict, ValidationError

from traderbot.deploy.verify import VerificationPorts, run_verification
from traderbot.deploy.verify_models import (
    CheckId,
    CheckResult,
    CheckStatus,
    OverallStatus,
    VerificationRequest,
    VerificationResult,
)
from traderbot.deploy.verify_ports import ProductionVerificationPorts
from traderbot.deploy.verify_reporter import JsonReporter, RichReporter
from traderbot.kalshi.order_models import MarketCategory
from traderbot.paths import get_data_dir

_ORDINARY_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)


class VerificationCommandOptions(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)
    categories: tuple[MarketCategory, ...]
    mode: str
    data_root: Path | None = None
    infisical_origin: str
    daemon_mcp_url: str
    timeout_seconds: float
    json_output: bool


def _failure(action: str = "unexpected_failure") -> VerificationResult:
    checks = tuple(
        CheckResult(
            id=check_id,
            status=CheckStatus.FAIL if check_id is CheckId.GATEWAY else CheckStatus.SKIP,
            required=check_id is not CheckId.DAEMON_SERVICE,
            action=action if check_id is CheckId.GATEWAY else "dependency_unavailable",
            message="Verification could not complete",
            elapsed_ms=0,
            dependency=None if check_id is CheckId.GATEWAY else CheckId.GATEWAY,
        )
        for check_id in CheckId
    )
    return VerificationResult(overall=OverallStatus.FAILED, checks=checks)


async def _run_owned(request: VerificationRequest) -> VerificationResult:
    ports = ProductionVerificationPorts(request)
    try:
        return await run_verification(request, ports)
    finally:
        ports.close()


def _execute_verification(
    options: VerificationCommandOptions,
    ports: VerificationPorts | None = None,
) -> int:
    try:
        request = VerificationRequest.model_validate(
            {
                "categories": options.categories,
                "mode": options.mode,
                "data_root": get_data_dir() if options.data_root is None else options.data_root,
                "infisical_origin": options.infisical_origin,
                "daemon_mcp_url": options.daemon_mcp_url,
                "timeout_seconds": options.timeout_seconds,
            }
        )
    except ValidationError:
        result = _failure("invalid_request")
        _ = _render_result(result, options.json_output)
        return 2
    try:
        result = (
            anyio.run(_run_owned, request)
            if ports is None
            else anyio.run(run_verification, request, ports)
        )
    except _ORDINARY_EXCEPTIONS:
        result = _failure()
    if not _render_result(result, options.json_output):
        return 1
    return 0 if result.overall is OverallStatus.OK else 1


def _render_result(result: VerificationResult, json_output: bool) -> bool:
    reporter = JsonReporter() if json_output else RichReporter()
    try:
        reporter.render(result)
        return True
    except _ORDINARY_EXCEPTIONS:
        fallback = _failure("reporter_failure")
        if json_output:
            _ = sys.stdout.write(fallback.model_dump_json() + "\n")
        else:
            _ = sys.stderr.write("Verification reporting failed\n")
        return False


def execute_verification(
    options: VerificationCommandOptions,
    ports: VerificationPorts | None = None,
) -> int:
    previous_logging_level = logging.root.manager.disable
    if options.json_output:
        logging.disable(logging.CRITICAL)
    try:
        return _execute_verification(options, ports)
    finally:
        logging.disable(previous_logging_level)


__all__ = ["VerificationCommandOptions", "execute_verification"]

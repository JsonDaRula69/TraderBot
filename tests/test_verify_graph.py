from __future__ import annotations

from typing import ClassVar, override

import pytest
from pydantic import SecretStr

from traderbot.deploy.verify import VerificationPorts, run_verification
from traderbot.deploy.verify_models import (
    CheckId,
    CheckStatus,
    ProbeResult,
    TokenProbe,
    VerificationRequest,
)
from traderbot.kalshi.order_models import MarketCategory


class FakePorts(VerificationPorts):
    __slots__: ClassVar[tuple[str, ...]] = ("calls", "outcomes")

    def __init__(self, outcomes: dict[CheckId, ProbeResult] | None = None) -> None:
        self.outcomes: dict[CheckId, ProbeResult] = {} if outcomes is None else outcomes
        self.calls: list[CheckId] = []

    @override
    async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult:
        _ = token
        self.calls.append(check_id)
        return self.outcomes.get(check_id, ProbeResult.passed("healthy"))

    @override
    async def tokens(self) -> TokenProbe:
        self.calls.append(CheckId.TOKENS)
        return TokenProbe(result=ProbeResult.passed("valid"), token=SecretStr("opaque-token"))


@pytest.mark.asyncio
async def test_gateway_failure_skips_only_gateway_children() -> None:
    # Given
    ports = FakePorts(
        outcomes={CheckId.GATEWAY: ProbeResult.failed("gateway_unavailable", "unavailable")}
    )
    request = VerificationRequest(categories=(MarketCategory.WEATHER,))

    # When
    result = await run_verification(request, ports)

    # Then
    indexed = {check.id: check for check in result.checks}
    assert indexed[CheckId.GATEWAY].status is CheckStatus.FAIL
    for check_id in (CheckId.AGENTS_WORKSPACES, CheckId.CRON, CheckId.HEARTBEAT):
        assert indexed[check_id].status is CheckStatus.SKIP
        assert indexed[check_id].dependency is CheckId.GATEWAY
    assert CheckId.AUTH_MODE in ports.calls
    assert result.overall == "failed"


@pytest.mark.asyncio
async def test_token_failure_skips_credential_consumers() -> None:
    # Given
    class FailedTokens(FakePorts):
        @override
        async def tokens(self) -> TokenProbe:
            self.calls.append(CheckId.TOKENS)
            return TokenProbe(result=ProbeResult.failed("token_invalid", "invalid"), token=None)

    ports = FailedTokens()

    # When
    result = await run_verification(
        VerificationRequest(categories=(MarketCategory.WEATHER,)), ports
    )

    # Then
    indexed = {check.id: check for check in result.checks}
    assert indexed[CheckId.KALSHI].dependency is CheckId.TOKENS
    assert indexed[CheckId.DAEMON_RUNTIME].dependency is CheckId.TOKENS
    assert indexed[CheckId.CHROMA].dependency is None
    assert CheckId.CHROMA in ports.calls


@pytest.mark.asyncio
async def test_daemon_runtime_failure_fails_when_required() -> None:
    # Given: a strict standalone posture and a fail-open daemon
    ports = FakePorts(
        outcomes={
            CheckId.DAEMON_RUNTIME: ProbeResult.failed(
                "daemon_websocket_inactive", "websocket is not connected"
            )
        }
    )

    # When: the graph runs with the default request posture
    result = await run_verification(
        VerificationRequest(categories=(MarketCategory.WEATHER,)), ports
    )

    # Then: the strict standalone tool fails closed on fleet health
    indexed = {check.id: check for check in result.checks}
    assert indexed[CheckId.DAEMON_RUNTIME].required is True
    assert indexed[CheckId.DAEMON_RUNTIME].status is CheckStatus.FAIL
    assert result.overall == "failed"


@pytest.mark.asyncio
async def test_daemon_runtime_failure_is_advisory_when_not_required() -> None:
    # Given: a wizard-embedded posture that does not own the daemon lifecycle
    ports = FakePorts(
        outcomes={
            CheckId.DAEMON_RUNTIME: ProbeResult.failed(
                "daemon_websocket_inactive", "websocket is not connected"
            )
        }
    )
    request = VerificationRequest(
        categories=(MarketCategory.WEATHER,),
        daemon_required=False,
    )

    # When: the graph runs the wizard-embedded posture
    result = await run_verification(request, ports)

    # Then: the divergence is advisory, visible, and non-blocking
    indexed = {check.id: check for check in result.checks}
    assert indexed[CheckId.DAEMON_RUNTIME].required is False
    assert indexed[CheckId.DAEMON_RUNTIME].status is CheckStatus.FAIL
    assert result.overall == "degraded"


@pytest.mark.asyncio
async def test_stable_order_and_optional_degraded_overall() -> None:
    # Given
    ports = FakePorts(
        outcomes={
            CheckId.DAEMON_SERVICE: ProbeResult.degraded("manager_unsupported", "unsupported")
        }
    )

    # When
    result = await run_verification(
        VerificationRequest(categories=(MarketCategory.WEATHER,)), ports
    )

    # Then
    assert tuple(check.id for check in result.checks) == tuple(CheckId)
    assert result.overall == "degraded"
    assert all(check.elapsed_ms >= 0 for check in result.checks)

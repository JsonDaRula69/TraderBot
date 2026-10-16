"""Orchestrate dependency-aware deployment verification."""

from __future__ import annotations

from time import monotonic
from typing import Protocol

from pydantic import SecretStr

from traderbot.deploy.verify_models import (
    CheckId,
    CheckResult,
    CheckStatus,
    OverallStatus,
    ProbeResult,
    TokenProbe,
    VerificationRequest,
    VerificationResult,
)


class VerificationPorts(Protocol):
    async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult: ...
    async def tokens(self) -> TokenProbe: ...


_OPTIONAL = frozenset({CheckId.DAEMON_SERVICE})
_GATEWAY_CHILDREN = frozenset({CheckId.AGENTS_WORKSPACES, CheckId.CRON, CheckId.HEARTBEAT})
# Phase 5 (todo 9): the sandbox config-reading probes depend on the agents
# check (it proves the selected fleet exists and its config is readable); a
# gateway failure cascades through the agents check automatically. The image
# probe is host-local and gated by nothing in the graph.
_AGENTS_CHILDREN = frozenset(
    {
        CheckId.SANDBOX_MODE_READBACK,
        CheckId.SANDBOX_POSTURE_CONFIG,
        CheckId.SANDBOX_OFF_NEGATIVE,
    }
)
_ORDINARY_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)


def _required(check_id: CheckId, request: VerificationRequest) -> bool:
    """Required checks assert deploy-owned state; the daemon is required only
    on a strict (standalone) posture because no wizard step installs it."""
    if check_id is CheckId.DAEMON_RUNTIME:
        return request.daemon_required
    return check_id not in _OPTIONAL


def _skip(check_id: CheckId, dependency: CheckId, request: VerificationRequest) -> CheckResult:
    return CheckResult(
        id=check_id,
        status=CheckStatus.SKIP,
        required=_required(check_id, request),
        action="dependency_unavailable",
        message="Dependency did not pass",
        elapsed_ms=0,
        dependency=dependency,
    )


def _result(
    check_id: CheckId,
    probe: ProbeResult,
    started: float,
    request: VerificationRequest,
) -> CheckResult:
    elapsed = min(300_000, max(0, round((monotonic() - started) * 1000)))
    return CheckResult(
        id=check_id,
        status=probe.status,
        required=_required(check_id, request),
        action=probe.action,
        message=probe.message,
        elapsed_ms=elapsed,
    )


def _exception_result(
    check_id: CheckId,
    started: float,
    request: VerificationRequest,
) -> CheckResult:
    return _result(
        check_id,
        ProbeResult.failed("check_exception", "Check failed unexpectedly"),
        started,
        request,
    )


def _overall(checks: tuple[CheckResult, ...]) -> OverallStatus:
    if any(check.required and check.status is CheckStatus.FAIL for check in checks):
        return OverallStatus.FAILED
    if any(
        check.status in {CheckStatus.DEGRADED, CheckStatus.SKIP}
        or (not check.required and check.status is CheckStatus.FAIL)
        for check in checks
    ):
        return OverallStatus.DEGRADED
    return OverallStatus.OK


async def run_verification(
    request: VerificationRequest,
    ports: VerificationPorts,
) -> VerificationResult:
    checks: list[CheckResult] = []
    gateway_passed = False
    agents_passed = False
    token: SecretStr | None = None
    tokens_passed = False
    for check_id in CheckId:
        if check_id in _GATEWAY_CHILDREN and not gateway_passed:
            checks.append(_skip(check_id, CheckId.GATEWAY, request))
            continue
        if check_id in _AGENTS_CHILDREN and not agents_passed:
            checks.append(_skip(check_id, CheckId.AGENTS_WORKSPACES, request))
            continue
        if check_id in {CheckId.KALSHI, CheckId.DAEMON_RUNTIME} and not tokens_passed:
            checks.append(_skip(check_id, CheckId.TOKENS, request))
            continue
        started = monotonic()
        try:
            if check_id is CheckId.TOKENS:
                token_probe = await ports.tokens()
                probe = token_probe.result
                token = token_probe.token
                tokens_passed = probe.status is CheckStatus.PASS and token is not None
            else:
                probe = await ports.probe(check_id, token)
            check = _result(check_id, probe, started, request)
        except _ORDINARY_EXCEPTIONS:
            check = _exception_result(check_id, started, request)
            if check_id is CheckId.TOKENS:
                token = None
                tokens_passed = False
        checks.append(check)
        if check_id is CheckId.GATEWAY:
            gateway_passed = check.status is CheckStatus.PASS
        if check_id is CheckId.AGENTS_WORKSPACES:
            agents_passed = check.status is CheckStatus.PASS
    frozen_checks = tuple(checks)
    return VerificationResult(overall=_overall(frozen_checks), checks=frozen_checks)


__all__ = ["VerificationPorts", "run_verification"]

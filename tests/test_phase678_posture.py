"""Phase678 adapter carries the wizard's own posture into the request.

Locks the plumbing that makes embedded verification assert exactly what
the deploy approved: dormancy only with approval, sandbox only for
created agents, daemon liveness never required on the wizard path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from traderbot.deploy import phase678_runtime
from traderbot.deploy.verify import VerificationPorts
from traderbot.deploy.verify_models import (
    OverallStatus,
    VerificationRequest,
    VerificationResult,
)
from traderbot.deploy.wizard_contracts import WizardRequest
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.order_models import MarketCategory


def _wizard_request(tmp_path: Path, heartbeat: Literal["preserve", "0m"]) -> WizardRequest:
    return WizardRequest(
        categories=(MarketCategory.WEATHER,),
        mode="backtest",
        category_workspaces={MarketCategory.WEATHER: tmp_path / "weather"},
        approvals=DeployApprovals(create_agents=True, heartbeat_change=True),
        heartbeat_every=heartbeat,
        data_root=tmp_path / "data",
    )


def _capture_adapter_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, VerificationRequest]:
    captured: dict[str, VerificationRequest] = {}

    class _CapturePorts:
        def __init__(self, request: VerificationRequest) -> None:
            captured["request"] = request

        def close(self) -> None:
            return None

    async def _capture_run(
        request: VerificationRequest,
        ports: VerificationPorts,
    ) -> VerificationResult:
        _ = ports
        captured["run"] = request
        return VerificationResult(overall=OverallStatus.OK, checks=())

    monkeypatch.setattr(phase678_runtime, "ProductionVerificationPorts", _CapturePorts)
    monkeypatch.setattr(phase678_runtime, "run_verification", _capture_run)
    return captured


def test_wizard_adapter_requires_only_approved_heartbeat_and_advisory_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an approved dormant deploy that created the weather agent
    captured = _capture_adapter_verification(monkeypatch)

    # When: the wizard path runs its embedded verification
    from traderbot.deploy.phase678_runtime import Phase678Adapter

    _ = Phase678Adapter().run_verification(_wizard_request(tmp_path, "0m"), ("weather",))

    # Then: the approved dormancy is required, created agents are threaded,
    # and the daemon the deploy does not own stays advisory
    request = captured["request"]
    assert request.heartbeat_policy == "require_0m"
    assert request.created_agents == ("weather",)
    assert request.daemon_required is False


def test_wizard_adapter_preserves_heartbeat_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a preserve-mode deploy that did not approve heartbeat changes
    captured = _capture_adapter_verification(monkeypatch)

    # When: the wizard path runs its embedded verification
    from traderbot.deploy.phase678_runtime import Phase678Adapter

    _ = Phase678Adapter().run_verification(_wizard_request(tmp_path, "preserve"), ())

    # Then: cadence is reported, not required
    request = captured["request"]
    assert request.heartbeat_policy == "preserve"
    assert request.created_agents == ()

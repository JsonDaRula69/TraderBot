from __future__ import annotations

import os

from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.deploy_state import load_deploy_state, save_deploy_state
from traderbot.deploy.verify_models import OverallStatus, VerificationResult
from traderbot.deploy.wizard_contracts import (
    DeployState,
    LatePreflightResult,
    Phase45Result,
    TokenProvisionResult,
    WizardPorts,
    WizardRequest,
)
from traderbot.deploy.wizard_runtime import OpenClawAdapter, WorkspaceInjectionAdapter
from traderbot.deploy.wizard_state import TokenMetadataState
from traderbot.profiles.models import TradingProfile


class TokenPort:
    def inspect(self, profile: TradingProfile, agent_id: str) -> TokenMetadataState:
        del profile, agent_id
        return TokenMetadataState.EXACT

    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult:
        del profile
        return TokenProvisionResult.existing(agent_id)


class Phase45:
    def provision_secrets(self, request: WizardRequest) -> Phase45Result:
        del request
        return Phase45Result.completed("ready")

    def provision_databases(self, request: WizardRequest) -> Phase45Result:
        del request
        return Phase45Result.completed("ready")


class Phase678:
    def preflight(self, request: WizardRequest) -> LatePreflightResult:
        del request
        return LatePreflightResult(valid=True, action="late_preflight_complete")

    def run_backfill(self, request: WizardRequest) -> BackfillResult:
        del request
        status = os.environ.get("TRADERBOT_TEST_BACKFILL_STATUS", "complete")
        return BackfillResult.model_validate({"status": status})

    def run_verification(self, request: WizardRequest) -> VerificationResult:
        del request
        return VerificationResult(overall=OverallStatus.OK, checks=())

    def load_state(self, request: WizardRequest) -> DeployState | None:
        return load_deploy_state(request.data_root)

    def save_state(self, request: WizardRequest, state: DeployState) -> None:
        save_deploy_state(request.data_root, state)


class Provider:
    def build(self) -> WizardPorts:
        return WizardPorts(
            OpenClawAdapter(),
            TokenPort(),
            WorkspaceInjectionAdapter(),
            Phase45(),
            Phase678(),
        )


provider = Provider()

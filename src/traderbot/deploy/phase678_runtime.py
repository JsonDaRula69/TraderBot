"""Adapt runtime dependencies for deploy wizard steps 6-8."""

from __future__ import annotations

from pathlib import Path
from typing import final

import anyio
from pydantic import ValidationError

from traderbot.deploy import sandbox_build
from traderbot.deploy.backfill import BackfillRequest, run_backfill, run_prepared_backfill
from traderbot.deploy.backfill_collector_types import (
    CollectorPathError,
    CollectorSchemaError,
    PreparedCollector,
)
from traderbot.deploy.backfill_command import OwnedBackfillDependencies
from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.deploy_state import save_deploy_state
from traderbot.deploy.verify import run_verification
from traderbot.deploy.verify_models import VerificationRequest, VerificationResult
from traderbot.deploy.verify_ports import ProductionVerificationPorts
from traderbot.deploy.wizard_contracts import DeployState, LatePreflightResult, WizardRequest
from traderbot.sandbox import DockerUnavailableError


@final
class Phase678Adapter:
    def __init__(
        self,
        prepared_collector: PreparedCollector | None = None,
        prepared_state: DeployState | None = None,
    ) -> None:
        self._prepared_collector = prepared_collector
        self._prepared_state = prepared_state

    @property
    def prepared_collector_path(self) -> Path | None:
        return None if self._prepared_collector is None else self._prepared_collector.path

    def preflight(self, request: WizardRequest) -> LatePreflightResult:
        try:
            _ = self._backfill_request(request)
            _ = self._verification_request(request)
        except (CollectorPathError, CollectorSchemaError, OSError, ValidationError):
            return LatePreflightResult(valid=False, action="late_request_invalid")
        return LatePreflightResult(valid=True, action="late_preflight_complete")

    def ensure_docker_available(self) -> bool:
        """Step-7 (todo-8) D7 presence gate: docker binary via the T7 lane.

        The live-daemon probe happens at build time (the T7 build lane
        classifies a dead daemon as cause="daemon-unavailable"); this seam
        never network-tests.
        """
        try:
            sandbox_build.ensure_docker_available()
        except DockerUnavailableError:
            return False
        return True

    def build_sandbox_image(self) -> str | None:
        """Build the sandbox image before any config write (todo-8).

        Returns the deterministic content tag on success, None on any
        failure (missing binary/daemon, missing/drifted Dockerfile,
        failed/partial build) - the caller fails closed with the typed
        step-7 remedy.
        """
        try:
            result = sandbox_build.build_sandbox_image()
        except (DockerUnavailableError, sandbox_build.SandboxBuildError):
            return None
        return result.image

    def run_backfill(self, request: WizardRequest) -> BackfillResult:
        dependencies = OwnedBackfillDependencies(
            default_collector_path=Path.home() / ".data-collector" / "collector.db",
        )
        backfill_request = self._backfill_request(request)
        if self._prepared_collector is None:
            return anyio.run(run_backfill, backfill_request, dependencies)
        return anyio.run(
            run_prepared_backfill,
            backfill_request,
            dependencies,
            self._prepared_collector,
        )

    def run_verification(
        self,
        request: WizardRequest,
        selected_agents: tuple[str, ...],
    ) -> VerificationResult:
        verification_request = self._verification_request(request, selected_agents)

        async def run_owned() -> VerificationResult:
            ports = ProductionVerificationPorts(verification_request)
            try:
                return await run_verification(verification_request, ports)
            finally:
                ports.close()

        return anyio.run(run_owned)

    def load_state(self, request: WizardRequest) -> DeployState | None:
        del request
        return self._prepared_state

    @staticmethod
    def save_state(request: WizardRequest, state: DeployState) -> None:
        save_deploy_state(request.data_root, state)

    def _backfill_request(self, request: WizardRequest) -> BackfillRequest:
        return BackfillRequest(
            months=request.months_backfill,
            target_db=request.data_root / "traderbot.db",
            collector_db=None if self._prepared_collector is not None else request.collector_db,
        )

    @staticmethod
    def _verification_request(
        request: WizardRequest,
        created_agents: tuple[str, ...] = (),
    ) -> VerificationRequest:
        # The wizard path asserts exactly the postconditions it wrote: the
        # heartbeat cadence it approved ("0m" only with explicit approval)
        # and the sandbox modes of the agents it created. Preserved posture
        # and daemon liveness are reported as advisory divergence, and no
        # wizard step installs the daemon, so the wizard never requires it.
        return VerificationRequest(
            categories=request.categories,
            mode=request.mode,
            sysadmin_workspace=request.sysadmin_workspace,
            category_workspaces=request.category_workspaces,
            data_root=request.data_root,
            infisical_origin=request.infisical_url,
            daemon_mcp_url=request.daemon_mcp_url,
            heartbeat_policy="require_0m" if request.heartbeat_every == "0m" else "preserve",
            created_agents=created_agents,
            daemon_required=False,
        )


__all__ = ["Phase678Adapter"]

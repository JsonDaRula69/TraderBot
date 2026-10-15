from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Never

from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.deploy_state import load_deploy_state, save_deploy_state
from traderbot.deploy.openclaw_models import (
    AgentInventory,
    AgentSummary,
    ConfigReadState,
    ConfigValueRead,
)
from traderbot.deploy.sandbox_build import resolve_sandbox_dockerfile
from traderbot.deploy.verify_models import OverallStatus, VerificationResult
from traderbot.deploy.wizard import DeployWizard
from traderbot.deploy.wizard_contracts import (
    DeployState,
    LatePreflightResult,
    Phase45Result,
    TokenProvisionResult,
    WizardPorts,
    WizardRequest,
)
from traderbot.deploy.wizard_state import (
    AgentConfigState,
    BootstrapCronState,
    OpenClawConfigSnapshot,
    SecretRefConfig,
    SecretRefState,
    TokenMetadataState,
)
from traderbot.profiles.injection import WorkspaceTemplate
from traderbot.profiles.models import TradingProfile
from traderbot.sandbox import sandbox_image_tag


class LateStepCanaryError(RuntimeError):
    pass


def fake_workspace(agent_id: str) -> Path:
    return Path(Path.cwd().anchor) / "fake" / agent_id


class FakeOpenClaw:
    def __init__(
        self,
        installed: bool = True,
        install_succeeds: bool = True,
        setup_succeeds: bool = True,
        gateway_succeeds: bool = True,
        agents: dict[str, Path] | None = None,
        agent_configs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.installed: bool = installed
        self.install_succeeds: bool = install_succeeds
        self.setup_succeeds: bool = setup_succeeds
        self.gateway_succeeds: bool = gateway_succeeds
        self.fail_secret_ref_for: set[str] = set()
        self.created_agents: set[str] = set()
        self.agents: dict[str, Path] = (
            agents if agents is not None else {"main": fake_workspace("main")}
        )
        self.secret_refs: dict[str, str] = {}
        self.heartbeats: dict[str, str] = {}
        self.sandboxes: dict[str, str] = {}
        self.cron_identities: set[tuple[str, str]] = set()
        self.bootstrap_state: BootstrapCronState | None = None
        self.install_calls: int = 0
        self.setup_calls: int = 0
        # Todo-8 step-7 world: a live deployed-shape config tree keyed by agent
        # id, read/written ONLY through the agents.list[i] bracket grammar
        # (insertion order of `agents` is the canonical index order, matching
        # inventory_agents()).
        self.config: dict[str, dict[str, Any]] = {
            agent_id: deepcopy(subtree) for agent_id, subtree in (agent_configs or {}).items()
        }
        for agent_id in self.agents:
            self.config.setdefault(agent_id, {})
        self.config_events: list[str] = []
        self.inventory_fails: bool = False
        # Budget knob: after N successful inventory calls the seam turns
        # unreadable (models the live inventory failing between preflight and
        # the approved step-7 apply).
        self.inventory_calls: int = 0
        self.inventory_budget: int | None = None
        self.fail_set_keys: set[str] = set()
        self.fail_unset_keys: set[str] = set()
        self.fail_read_keys: set[str] = set()
        # Induced-mismatch seam: a key re-read is corrupted EXACTLY ONCE (the
        # first read that finds it present), modeling a postcondition read
        # that disagrees with the written value. Pre-write backup reads hit
        # ABSENT and never consume the corruption.
        self.corrupt_on_read: set[str] = set()
        self.corrupt_value: Any = {"tampered": True}

    def detect(self) -> str | None:
        return "/fake/openclaw" if self.installed else None

    def install(self) -> bool:
        self.install_calls += 1
        if self.install_succeeds:
            self.installed = True
        return self.install_succeeds

    def setup(self) -> bool:
        self.setup_calls += 1
        if self.setup_succeeds:
            _ = self.agents.setdefault("main", fake_workspace("main"))
        return self.setup_succeeds

    def gateway_status(self) -> bool:
        return self.gateway_succeeds

    def inventory_agents(self) -> AgentInventory | None:
        self.inventory_calls += 1
        if self.inventory_fails:
            return None
        if self.inventory_budget is not None and self.inventory_calls > self.inventory_budget:
            return None
        return AgentInventory(
            root=[
                AgentSummary(
                    id=agent_id,
                    workspace=str(workspace),
                    agentDir=f"/fake/{agent_id}",
                    bindings=0,
                    isDefault=agent_id == "main",
                )
                for agent_id, workspace in self.agents.items()
            ]
        )

    def inspect_config(self, agent_ids: tuple[str, ...]) -> OpenClawConfigSnapshot | None:
        return OpenClawConfigSnapshot(
            agents=tuple(
                AgentConfigState(
                    agent_id=agent_id,
                    path_prefix=f"agents.entries.{agent_id}",
                    heartbeat_every=self.heartbeats.get(agent_id),
                    sandbox_mode=self.sandboxes.get(agent_id),
                )
                for agent_id in agent_ids
                if agent_id in self.agents
            ),
            secret_refs=tuple(
                SecretRefState(
                    agent_id=agent_id,
                    ref=(
                        None
                        if agent_id not in self.secret_refs
                        else SecretRefConfig(id=self.secret_refs[agent_id])
                    ),
                )
                for agent_id in agent_ids
            ),
        )

    def inspect_bootstrap_cron(self) -> BootstrapCronState:
        if self.bootstrap_state is not None:
            return self.bootstrap_state
        return (
            BootstrapCronState.EXACT
            if ("traderbot-main-at-5m", "main") in self.cron_identities
            else BootstrapCronState.MISSING
        )

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        self.created_agents.add(agent_id)
        self.agents[agent_id] = workspace
        self.config.setdefault(agent_id, {})
        return True

    def set_secret_ref(self, agent_id: str, secret_ref: SecretRefConfig) -> bool:
        if agent_id in self.fail_secret_ref_for:
            return False
        self.secret_refs[agent_id] = secret_ref.id
        return True

    def set_heartbeat(self, agent: AgentConfigState, value: str) -> bool:
        self.heartbeats[agent.agent_id] = value
        return True

    def set_sandbox(self, agent: AgentConfigState, value: str) -> bool:
        self.sandboxes[agent.agent_id] = value
        return True

    def ensure_bootstrap_cron(self, state: BootstrapCronState) -> bool:
        if state in {
            BootstrapCronState.EXACT,
            BootstrapCronState.COMPLETED_RETAINED,
            BootstrapCronState.COMPLETED_ABSENT,
        }:
            return True
        if state is not BootstrapCronState.MISSING:
            return False
        self.cron_identities.add(("traderbot-main-at-5m", "main"))
        return True

    _LIST_KEY: re.Pattern[str] = re.compile(r"^agents\.list\[(\d+)\](?:\.([A-Za-z0-9_.\-]+))?$")

    def _list_target(self, key: str) -> tuple[str, list[str]] | None:
        match = self._LIST_KEY.fullmatch(key)
        if match is None:
            return None
        index = int(match.group(1))
        ids = list(self.agents)
        if index >= len(ids):
            return None
        segments = match.group(2).split(".") if match.group(2) else []
        return ids[index], segments

    def read_config_value(self, key: str) -> ConfigValueRead:
        """Raw tri-state read mirroring openclaw_config.read_config_value."""
        self.config_events.append(f"get:{key}")
        if key in self.fail_read_keys:
            return ConfigValueRead(ConfigReadState.FAILED)
        target = self._list_target(key)
        if target is None:
            return ConfigValueRead(ConfigReadState.FAILED)
        agent_id, segments = target
        if segments == ["id"]:
            return ConfigValueRead(ConfigReadState.FOUND, agent_id)
        if segments and segments[0] == "id":
            return ConfigValueRead(ConfigReadState.FAILED)
        current: Any = self.config.get(agent_id, {})
        for segment in segments:
            if not isinstance(current, dict) or segment not in current:
                return ConfigValueRead(ConfigReadState.ABSENT)
            current = current[segment]
        if key in self.corrupt_on_read:
            self.corrupt_on_read.discard(key)  # exactly-once induced mismatch
            return ConfigValueRead(ConfigReadState.FOUND, deepcopy(self.corrupt_value))
        # Faithful to the subprocess roundtrip: every read is an independent
        # snapshot (never an alias into the live tree — otherwise step-7
        # backups would silently track writes, hiding D8 restore fidelity).
        return ConfigValueRead(ConfigReadState.FOUND, deepcopy(current))

    def set_config_json(self, key: str, json_value: str) -> bool:
        """Strict-JSON leaf write on the deployed list-shape bracket grammar."""
        target = self._list_target(key)
        if key in self.fail_set_keys or target is None or not target[1] or target[1][0] == "id":
            self.config_events.append(f"set-fail:{key}")
            return False
        try:
            value = json.loads(json_value)
        except json.JSONDecodeError:
            self.config_events.append(f"set-fail:{key}")
            return False
        agent_id, segments = target
        current: Any = self.config.setdefault(agent_id, {})
        for segment in segments[:-1]:
            child = current.get(segment)
            if not isinstance(child, dict):
                child = {}
                current[segment] = child
            current = child
        current[segments[-1]] = deepcopy(value)
        self.config_events.append(f"set:{key}")
        return True

    def unset_config(self, key: str) -> bool:
        """Leaf deletion without parent pruning (mirrors the deployed CLI's
        unsetAtPath semantics — T1 receipt: unset leaves empty parents)."""
        if key in self.fail_unset_keys:
            self.config_events.append(f"unset-fail:{key}")
            return False
        target = self._list_target(key)
        if target is None or not target[1]:
            self.config_events.append(f"unset-fail:{key}")
            return False
        agent_id, segments = target
        current: Any = self.config.get(agent_id, {})
        for segment in segments[:-1]:
            if not isinstance(current, dict) or segment not in current:
                self.config_events.append(f"unset-fail:{key}")
                return False
            current = current[segment]
        leaf = segments[-1]
        if not isinstance(current, dict) or leaf not in current:
            self.config_events.append(f"unset-fail:{key}")
            return False
        del current[leaf]
        self.config_events.append(f"unset:{key}")
        return True

    def doctor(self) -> Never:
        raise AssertionError("doctor must not run during deploy")


class FakeTokens:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for: set[str] = fail_for or set()
        self.profiles: dict[str, str] = {}
        self.created_count: dict[str, int] = {}

    def inspect(self, profile: TradingProfile, agent_id: str) -> TokenMetadataState:
        if agent_id in self.fail_for:
            return TokenMetadataState.FAILED
        existing = self.profiles.get(agent_id)
        if existing is None:
            return TokenMetadataState.MISSING
        return TokenMetadataState.EXACT if existing == profile.name else TokenMetadataState.CONFLICT

    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult:
        if agent_id in self.fail_for:
            return TokenProvisionResult.failed(agent_id, "encrypted storage failed")
        if agent_id in self.profiles:
            return TokenProvisionResult.existing(agent_id)
        self.profiles[agent_id] = profile.name
        self.created_count[agent_id] = self.created_count.get(agent_id, 0) + 1
        return TokenProvisionResult.created(agent_id)


class FakeInjector:
    def __init__(self) -> None:
        self.injected: set[tuple[Path, WorkspaceTemplate]] = set()

    def preflight(self, workspace: Path, template: WorkspaceTemplate) -> str | None:
        return f"preview:{workspace}:{template.value}"

    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str:
        self.injected.add((workspace, template))
        return f"manifest:{workspace}:{template.value}"


class FakePhase45:
    def __init__(self, fail_step: int | None = None) -> None:
        self.fail_step: int | None = fail_step
        self.calls: list[int] = []

    def provision_secrets(self, request: WizardRequest) -> Phase45Result:
        del request
        self.calls.append(4)
        if self.fail_step == 4:
            return Phase45Result.failed("secret provisioning failed")
        return Phase45Result.completed("Kalshi secrets ready in local-encrypted backend")

    def provision_databases(self, request: WizardRequest) -> Phase45Result:
        del request
        self.calls.append(5)
        if self.fail_step == 5:
            return Phase45Result.failed("database provisioning failed")
        return Phase45Result.completed("selected category databases ready")


class FakePhase678:
    def __init__(
        self,
        backfill: BackfillResult | None = None,
        verification: VerificationResult | None = None,
        *,
        docker_ready: bool = True,
        build_succeeds: bool = True,
        built_tag: str | None = None,
    ) -> None:
        self.backfill: BackfillResult = backfill or BackfillResult(status="complete")
        self.verification: VerificationResult = verification or VerificationResult(
            overall=OverallStatus.OK,
            checks=(),
        )
        self.calls: list[int] = []
        self.raise_backfill: bool = False
        self.raise_verification: bool = False
        self.verification_agents: tuple[str, ...] = ()
        self.preflight_result: LatePreflightResult = LatePreflightResult(
            valid=True,
            action="late_preflight_complete",
        )
        self.preflight_calls: int = 0
        self.state: DeployState | None = None
        # Todo-8 step-7 seams (ensure gate + build-before-write).
        self.docker_ready: bool = docker_ready
        self.build_succeeds: bool = build_succeeds
        self.built_tag: str | None = built_tag  # override -> image-drift path
        self.openclaw: FakeOpenClaw | None = None  # wired by tests for ordering
        self.docker_checks: int = 0
        self.build_calls: int = 0
        self.config_events_at_build: int | None = None

    def ensure_docker_available(self) -> bool:
        self.docker_checks += 1
        return self.docker_ready

    def build_sandbox_image(self) -> str | None:
        self.build_calls += 1
        if self.openclaw is not None:
            self.config_events_at_build = len(self.openclaw.config_events)
        if not self.build_succeeds:
            return None
        if self.built_tag is not None:
            return self.built_tag
        # Same deterministic tag the wizard computes from the pinned
        # install/docker/Dockerfile (never a default_factory image).
        return sandbox_image_tag(resolve_sandbox_dockerfile())

    def preflight(self, request: WizardRequest) -> LatePreflightResult:
        del request
        self.preflight_calls += 1
        return self.preflight_result

    def run_backfill(self, request: WizardRequest) -> BackfillResult:
        del request
        self.calls.append(6)
        if self.raise_backfill:
            raise LateStepCanaryError("SECRET-BACKFILL-CANARY")
        return self.backfill

    def run_verification(
        self,
        request: WizardRequest,
        selected_agents: tuple[str, ...] = (),
    ) -> VerificationResult:
        del request
        self.calls.append(8)
        self.verification_agents = selected_agents
        if self.raise_verification:
            raise LateStepCanaryError("SECRET-VERIFY-CANARY")
        return self.verification

    def load_state(self, request: WizardRequest) -> DeployState | None:
        return self.state if self.state is not None else load_deploy_state(request.data_root)

    def save_state(self, request: WizardRequest, state: DeployState) -> None:
        self.state = state
        save_deploy_state(request.data_root, state)


class FakeEnvironment:
    def __init__(
        self,
        openclaw: FakeOpenClaw | None = None,
        tokens: FakeTokens | None = None,
        injector: FakeInjector | None = None,
        phase45: FakePhase45 | None = None,
        phase678: FakePhase678 | None = None,
    ) -> None:
        self.openclaw: FakeOpenClaw = openclaw or FakeOpenClaw()
        self.tokens: FakeTokens = tokens or FakeTokens()
        self.injector: FakeInjector = injector or FakeInjector()
        self.phase45: FakePhase45 | None = phase45
        self.phase678: FakePhase678 | None = phase678

    def ports(self) -> WizardPorts:
        return WizardPorts(
            self.openclaw,
            self.tokens,
            self.injector,
            self.phase45,
            self.phase678,
        )

    def wizard(self) -> DeployWizard:
        return DeployWizard(self.ports())

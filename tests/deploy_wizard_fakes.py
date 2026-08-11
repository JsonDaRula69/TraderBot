from __future__ import annotations

from pathlib import Path
from typing import Never

from traderbot.deploy.openclaw_models import AgentInventory, AgentSummary
from traderbot.deploy.wizard import DeployWizard
from traderbot.deploy.wizard_contracts import (
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
        self.install_calls: int = 0
        self.setup_calls: int = 0

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
        return (
            BootstrapCronState.EXACT
            if ("traderbot-main-at-5m", "main") in self.cron_identities
            else BootstrapCronState.MISSING
        )

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        self.created_agents.add(agent_id)
        self.agents[agent_id] = workspace
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

    def ensure_bootstrap_cron(self) -> bool:
        self.cron_identities.add(("traderbot-main-at-5m", "main"))
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
        self.fail_step = fail_step
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


class FakeEnvironment:
    def __init__(
        self,
        openclaw: FakeOpenClaw | None = None,
        tokens: FakeTokens | None = None,
        injector: FakeInjector | None = None,
        phase45: FakePhase45 | None = None,
    ) -> None:
        self.openclaw: FakeOpenClaw = openclaw or FakeOpenClaw()
        self.tokens: FakeTokens = tokens or FakeTokens()
        self.injector: FakeInjector = injector or FakeInjector()
        self.phase45: FakePhase45 | None = phase45

    def ports(self) -> WizardPorts:
        return WizardPorts(self.openclaw, self.tokens, self.injector, self.phase45)

    def wizard(self) -> DeployWizard:
        return DeployWizard(self.ports())

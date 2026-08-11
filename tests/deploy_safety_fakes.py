from __future__ import annotations

from pathlib import Path
from typing import Never, final

from traderbot.deploy.openclaw_models import AgentInventory, AgentSummary
from traderbot.deploy.wizard import TokenProvisionResult, WizardPorts
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


@final
class SafetyOpenClaw:
    def __init__(self, agents: dict[str, Path], events: list[str]) -> None:
        self.agents = dict(agents)
        self.secret_refs: dict[str, SecretRefConfig] = {}
        self.heartbeats: dict[str, str] = {}
        self.sandboxes: dict[str, str] = {}
        self.events = events
        self.bootstrap_state = BootstrapCronState.MISSING
        self.partial_create: set[str] = set()
        self.fail_create: set[str] = set()
        self.installed = True
        self.setup_workspace: Path | None = None

    @property
    def mutations(self) -> tuple[str, ...]:
        prefixes = ("install", "setup", "create:", "secret:", "heartbeat:", "sandbox:", "cron:")
        return tuple(event for event in self.events if event.startswith(prefixes))

    def detect(self) -> str | None:
        self.events.append("read:detect")
        return "/fake/openclaw" if self.installed else None

    def install(self) -> bool:
        self.events.append("install")
        self.installed = True
        return True

    def setup(self) -> bool:
        self.events.append("setup")
        if self.setup_workspace is not None:
            self.agents["main"] = self.setup_workspace
        return True

    def gateway_status(self) -> bool:
        self.events.append("read:gateway")
        return True

    def inventory_agents(self) -> AgentInventory | None:
        self.events.append("read:agents")
        return AgentInventory(
            [
                AgentSummary(
                    id=agent_id,
                    workspace=str(workspace),
                    agentDir=f"/state/{agent_id}",
                    bindings=0,
                    isDefault=agent_id == "main",
                )
                for agent_id, workspace in self.agents.items()
            ]
        )

    def inspect_config(self, agent_ids: tuple[str, ...]) -> OpenClawConfigSnapshot | None:
        self.events.append("read:config")
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
                SecretRefState(agent_id=agent_id, ref=self.secret_refs.get(agent_id))
                for agent_id in agent_ids
            ),
        )

    def inspect_bootstrap_cron(self) -> BootstrapCronState:
        self.events.append("read:cron")
        return self.bootstrap_state

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        self.events.append(f"create:{agent_id}")
        if agent_id in self.partial_create:
            self.agents[agent_id] = workspace
            return False
        if agent_id in self.fail_create:
            return False
        self.agents[agent_id] = workspace
        return True

    def configure_secret_ref(self, agent_id: str, secret_id: str) -> bool:
        return self.set_secret_ref(agent_id, SecretRefConfig(id=secret_id))

    def set_secret_ref(self, agent_id: str, secret_ref: SecretRefConfig) -> bool:
        self.events.append(f"secret:{agent_id}")
        self.secret_refs[agent_id] = secret_ref
        return True

    def set_heartbeat(self, agent: AgentConfigState, value: str) -> bool:
        self.events.append(f"heartbeat:{agent.agent_id}:{value}")
        self.heartbeats[agent.agent_id] = value
        return True

    def set_sandbox(self, agent: AgentConfigState, value: str) -> bool:
        self.events.append(f"sandbox:{agent.agent_id}:{value}")
        self.sandboxes[agent.agent_id] = value
        return True

    def ensure_bootstrap_cron(self) -> bool:
        self.events.append("cron:ensure")
        if self.bootstrap_state is BootstrapCronState.CONFLICT:
            return False
        self.bootstrap_state = BootstrapCronState.EXACT
        return True

    def doctor(self) -> Never:
        raise AssertionError("deploy must not invoke doctor")


@final
class SafetyTokens:
    def __init__(self, events: list[str]) -> None:
        self.states: dict[str, TokenMetadataState] = {}
        self.created: dict[str, int] = {}
        self.events = events

    def inspect(self, profile: TradingProfile, agent_id: str) -> TokenMetadataState:
        _ = profile
        self.events.append(f"read:token:{agent_id}")
        return self.states.get(agent_id, TokenMetadataState.MISSING)

    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult:
        _ = profile
        state = self.states.get(agent_id, TokenMetadataState.MISSING)
        if state is TokenMetadataState.EXACT:
            return TokenProvisionResult.existing(agent_id)
        if state in {TokenMetadataState.CONFLICT, TokenMetadataState.FAILED}:
            return TokenProvisionResult.failed(agent_id, "identity metadata conflict")
        self.events.append(f"token:{agent_id}")
        self.states[agent_id] = TokenMetadataState.EXACT
        self.created[agent_id] = self.created.get(agent_id, 0) + 1
        return TokenProvisionResult.created(agent_id)


@final
class SafetyInjector:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.preflight_failures: set[Path] = set()

    def preflight(self, workspace: Path, template: WorkspaceTemplate) -> str | None:
        self.events.append(f"read:inject:{template.value}:{workspace}")
        return None if workspace in self.preflight_failures else f"plan-{template.value}"

    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str:
        self.events.append(f"inject:{template.value}:{workspace}")
        return f"manifest-{template.value}"


@final
class SafetyEnvironment:
    def __init__(self, agents: dict[str, Path]) -> None:
        self.events: list[str] = []
        self.openclaw = SafetyOpenClaw(agents, self.events)
        self.tokens = SafetyTokens(self.events)
        self.injector = SafetyInjector(self.events)

    @property
    def mutations(self) -> tuple[str, ...]:
        prefixes = (
            "install",
            "setup",
            "create:",
            "secret:",
            "heartbeat:",
            "sandbox:",
            "cron:",
            "token:",
            "inject:",
        )
        return tuple(event for event in self.events if event.startswith(prefixes))

    def ports(self) -> WizardPorts:
        return WizardPorts(self.openclaw, self.tokens, self.injector)

    def make_exact(self, *agent_ids: str) -> None:
        for agent_id in agent_ids:
            self.tokens.states[agent_id] = TokenMetadataState.EXACT
            self.openclaw.secret_refs[agent_id] = SecretRefConfig(id=f"{agent_id}_token")

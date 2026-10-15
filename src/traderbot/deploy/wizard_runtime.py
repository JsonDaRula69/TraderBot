"""Provide production port adapters for deploy wizard dependencies."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from traderbot.deploy import openclaw
from traderbot.deploy.bootstrap_cron import (
    BOOTSTRAP_PROMPT,
    classify_bootstrap_crons,
)
from traderbot.deploy.bootstrap_cron import (
    SysAdminBootstrapCron as SysAdminBootstrapCron,
)
from traderbot.deploy.openclaw_models import (
    AgentInventory,
)
from traderbot.deploy.wizard_contracts import (
    Phase45Port,
    ProvisionStatus,
    TokenProvisionResult,
    WizardPorts,
)
from traderbot.deploy.wizard_state import (
    AgentConfigState,
    BootstrapCronState,
    OpenClawConfigSnapshot,
    SecretRefConfig,
    TokenMetadataState,
)
from traderbot.profiles.injection import (
    WorkspaceInjectionError,
    WorkspaceTemplate,
    inject_workspace,
    preflight_workspace,
)
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.tokens import generate_token
from traderbot.secrets.local_encrypted import SecretIntegrityError
from traderbot.secrets.store import ProfileTokenEntry, SecretsStore


def resolve_agent_config_path(agent_id: str) -> str | None:
    """Resolve the deployed write prefix (``agents.list[i]`` or legacy entries)
    for a configured agent id from OBSERVED current gateway state — never cached.

    Composition of the bounded wrappers: a fresh inventory plus the entries-first
    + list-fallback read in ``openclaw_config._agent_config``. Returns None
    (fail-closed) when the agent is unconfigured or any read fails.
    """
    inventory = openclaw.inspect_agents()
    if inventory is None:
        return None
    return openclaw.agent_config_path(agent_id, inventory)


class OpenClawAdapter:
    """Map wizard operations to the bounded Todo-3 OpenClaw wrappers."""

    def detect(self) -> str | None:
        return openclaw.detect_openclaw()

    def install(self) -> bool:
        return openclaw.install_openclaw()

    def setup(self) -> bool:
        return openclaw.openclaw_setup()

    def gateway_status(self) -> bool:
        return openclaw.gateway_status()

    def inventory_agents(self) -> AgentInventory | None:
        return openclaw.inspect_agents()

    def inspect_config(self, agent_ids: tuple[str, ...]) -> OpenClawConfigSnapshot | None:
        inventory = openclaw.inspect_agents()
        return None if inventory is None else openclaw.inspect_config(agent_ids, inventory)

    def inspect_bootstrap_cron(self) -> BootstrapCronState:
        return classify_bootstrap_crons(openclaw.inspect_crons())

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        return openclaw.create_agent(agent_id, workspace)

    def set_secret_ref(self, agent_id: str, secret_ref: SecretRefConfig) -> bool:
        return openclaw.set_secret_ref(agent_id, secret_ref)

    def set_heartbeat(self, agent: AgentConfigState, value: str) -> bool:
        return openclaw.set_config(f"{agent.path_prefix}.heartbeat.every", value)

    def set_sandbox(self, agent: AgentConfigState, value: str) -> bool:
        return openclaw.set_config(f"{agent.path_prefix}.sandbox.mode", value)

    def ensure_bootstrap_cron(self, state: BootstrapCronState) -> bool:
        if state is BootstrapCronState.EXACT:
            return True
        if state in {
            BootstrapCronState.COMPLETED_RETAINED,
            BootstrapCronState.COMPLETED_ABSENT,
        }:
            return True
        if state is not BootstrapCronState.MISSING:
            return False
        added = openclaw.register_cron(
            agent="main",
            prompt=BOOTSTRAP_PROMPT,
            at="5m",
            session="isolated",
            delete_after_run=True,
        )
        if not added:
            return False
        return added and self.inspect_bootstrap_cron() is BootstrapCronState.EXACT


class SecretsTokenProvisioner:
    """Persist opaque profile identities through the SecretsStore facade."""

    def __init__(
        self,
        store: SecretsStore,
        token_factory: Callable[[], str] = generate_token,
    ) -> None:
        self._store: SecretsStore = store
        self._token_factory: Callable[[], str] = token_factory

    def inspect(self, profile: TradingProfile, agent_id: str) -> TokenMetadataState:
        try:
            existing = self._store.get_profile_token(agent_id)
            raw = self._store.get(agent_id, "token", namespace="tokens")
        except (OSError, SecretIntegrityError, ValidationError):
            return TokenMetadataState.FAILED
        if existing is None:
            return TokenMetadataState.MISSING if raw is None else TokenMetadataState.CONFLICT
        result = self._existing_result(profile, agent_id, existing)
        return (
            TokenMetadataState.EXACT
            if result.status is not ProvisionStatus.FAILED
            else TokenMetadataState.CONFLICT
        )

    def ensure(self, profile: TradingProfile, agent_id: str) -> TokenProvisionResult:
        try:
            existing = self._store.get_profile_token(agent_id)
            raw = self._store.get(agent_id, "token", namespace="tokens")
            if existing is None and raw is not None:
                return TokenProvisionResult.failed(agent_id, "stored identity is invalid")
            if existing is not None:
                return self._existing_result(profile, agent_id, existing)
            self._store.store_profile_token(
                agent_id=agent_id,
                token=self._token_factory(),
                profile=profile.name,
                categories=[category.value for category in profile.enabled_categories],
                permissions=list(profile.permissions),
            )
        except (OSError, SecretIntegrityError, ValidationError):
            return TokenProvisionResult.failed(agent_id, "encrypted identity storage failed")
        return TokenProvisionResult.created(agent_id)

    @staticmethod
    def _existing_result(
        profile: TradingProfile,
        agent_id: str,
        existing: ProfileTokenEntry,
    ) -> TokenProvisionResult:
        expected_categories = [category.value for category in profile.enabled_categories]
        if (
            existing["profile"] != profile.name
            or existing["agent_id"] != agent_id
            or existing["categories"] != expected_categories
            or existing["permissions"] != profile.permissions
        ):
            return TokenProvisionResult.failed(agent_id, "stored identity metadata conflicts")
        return TokenProvisionResult.existing(agent_id)


class WorkspaceInjectionAdapter:
    """Apply Todo-4 workspace templates and return their deterministic digest."""

    def preflight(self, workspace: Path, template: WorkspaceTemplate) -> str | None:
        try:
            return preflight_workspace(workspace, template).manifest_hash
        except (OSError, WorkspaceInjectionError):
            return None

    def inject(self, workspace: Path, template: WorkspaceTemplate) -> str:
        return inject_workspace(workspace, template).manifest_hash


def build_wizard_ports(
    store: SecretsStore,
    phase45: Phase45Port | None = None,
) -> WizardPorts:
    return WizardPorts(
        openclaw=OpenClawAdapter(),
        tokens=SecretsTokenProvisioner(store),
        injector=WorkspaceInjectionAdapter(),
        phase45=phase45,
    )

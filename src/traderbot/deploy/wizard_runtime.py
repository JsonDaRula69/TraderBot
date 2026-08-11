from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Final, Literal, Self

from infisical_sdk.infisical_requests import APIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from traderbot.deploy import openclaw
from traderbot.deploy.openclaw_models import (
    AgentInventory,
    CronAgentTurnPayload,
    CronAtSchedule,
    CronJob,
    JsonValue,
)
from traderbot.deploy.wizard_contracts import (
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

_BOOTSTRAP_NAME: Final = "traderbot-main-at-5m"
_BOOTSTRAP_DELAY_SECONDS: Final = 300.0
_BOOTSTRAP_DELAY_TOLERANCE_SECONDS: Final = 5.0
_BOOTSTRAP_PROMPT: Final = (
    "Begin the SysAdmin activation protocol: remove this bootstrap job, verify the "
    "TraderBot service and data freshness, register essential jobs, enable the SysAdmin "
    "heartbeat, then activate selected categories one at a time."
)
class SysAdminBootstrapCron(BaseModel):
    """Canonical persisted contract for TraderBot's managed SysAdmin activation job."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    id: str = Field(min_length=1)
    name: Literal["traderbot-main-at-5m"]
    agentId: Literal["main"]
    enabled: Literal[True]
    createdAtMs: int = Field(ge=0)
    updatedAtMs: int = Field(ge=0)
    schedule: CronAtSchedule
    sessionTarget: Literal["isolated"]
    wakeMode: Literal["now"]
    payload: CronAgentTurnPayload
    deleteAfterRun: Literal[True]
    state: dict[str, JsonValue]

    @model_validator(mode="after")
    def exact_schedule_and_payload(self) -> Self:
        if self.payload.message != _BOOTSTRAP_PROMPT:
            raise PydanticCustomError("bootstrap_payload", "activation payload differs")
        scheduled_at = self.schedule.at
        if scheduled_at == "5m":
            return self
        try:
            scheduled = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PydanticCustomError(
                "bootstrap_schedule",
                "one-shot schedule must be a valid absolute timestamp",
            ) from exc
        if scheduled.tzinfo is None:
            raise PydanticCustomError(
                "bootstrap_schedule",
                "one-shot schedule timestamp must include a timezone",
            )
        created = datetime.fromtimestamp(self.createdAtMs / 1000, tz=UTC)
        delay = (scheduled - created).total_seconds()
        if abs(delay - _BOOTSTRAP_DELAY_SECONDS) > _BOOTSTRAP_DELAY_TOLERANCE_SECONDS:
            raise PydanticCustomError(
                "bootstrap_schedule",
                "one-shot schedule must represent the managed five-minute delay",
            )
        return self

    @classmethod
    def is_unique_match(cls, jobs: list[CronJob]) -> bool:
        matches = [job for job in jobs if job.get("name") == _BOOTSTRAP_NAME]
        if len(matches) != 1:
            return False
        try:
            _ = cls.model_validate(matches[0])
        except ValidationError:
            return False
        return True


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
        jobs = openclaw.inspect_crons()
        if jobs is None:
            return BootstrapCronState.FAILED
        matches = [job for job in jobs if job.get("name") == _BOOTSTRAP_NAME]
        if not matches:
            return BootstrapCronState.MISSING
        return (
            BootstrapCronState.EXACT
            if SysAdminBootstrapCron.is_unique_match(matches)
            else BootstrapCronState.CONFLICT
        )

    def create_agent(self, agent_id: str, workspace: Path) -> bool:
        return openclaw.create_agent(agent_id, workspace)

    def set_secret_ref(self, agent_id: str, secret_ref: SecretRefConfig) -> bool:
        return openclaw.set_secret_ref(agent_id, secret_ref)

    def set_heartbeat(self, agent: AgentConfigState, value: str) -> bool:
        return openclaw.set_config(f"{agent.path_prefix}.heartbeat.every", value)

    def set_sandbox(self, agent: AgentConfigState, value: str) -> bool:
        return openclaw.set_config(f"{agent.path_prefix}.sandbox.mode", value)

    def ensure_bootstrap_cron(self) -> bool:
        state = self.inspect_bootstrap_cron()
        if state is BootstrapCronState.EXACT:
            return True
        if state is not BootstrapCronState.MISSING:
            return False
        added = openclaw.register_cron(
            agent="main",
            prompt=_BOOTSTRAP_PROMPT,
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
        except (APIError, OSError, SecretIntegrityError, ValidationError):
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
        except (APIError, OSError, SecretIntegrityError, ValidationError):
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


def build_wizard_ports(store: SecretsStore) -> WizardPorts:
    return WizardPorts(
        openclaw=OpenClawAdapter(),
        tokens=SecretsTokenProvisioner(store),
        injector=WorkspaceInjectionAdapter(),
    )

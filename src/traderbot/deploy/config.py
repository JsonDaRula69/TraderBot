"""Typed configuration boundary for non-interactive deployment."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from traderbot.deploy.validation import (
    SecretReconciliationApprovals,
    validate_infisical_origin,
    validate_secret_references,
)
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.order_models import MarketCategory

_REQUIRED_APPROVALS: Final[frozenset[str]] = frozenset(
    {
        "install_openclaw",
        "setup_openclaw",
        "create_agents",
        "heartbeat_change",
        # Todo-8: the step-7 docker-sandbox apply requires the SAME explicit
        # operator approval discipline as the other write lanes (ONE approval
        # mirroring the existing config-mode approval plumbing).
        "sandbox_apply",
    }
)


class DeployTokens(BaseModel):
    """Optional environment references supplied by a deploy document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kalshi_api_key_env: str | None = None
    kalshi_private_key_pem_env: str | None = None


class DeployConfig(BaseModel):
    """Validated representation of a deploy.json document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    categories: list[MarketCategory]
    mode: Literal["backtest"]
    infisical_url: str | None = None
    tokens: DeployTokens = Field(default_factory=DeployTokens)
    secret_approvals: SecretReconciliationApprovals = Field(
        default_factory=SecretReconciliationApprovals
    )
    months_backfill: Annotated[int, Field(ge=1, le=60)] = 6
    collector_db: Path | None = None
    data_root: Path | None = None
    daemon_mcp_url: str = "http://127.0.0.1:8765/mcp"
    sysadmin_workspace: Path | None = None
    category_workspaces: dict[MarketCategory, Path] = Field(default_factory=dict)
    approvals: DeployApprovals
    heartbeat_every: Literal["preserve", "0m"]

    @field_validator("mode", mode="before")
    @classmethod
    def backtest_only(cls, mode: str) -> str:
        if mode != "backtest":
            message = "paper/live mode requires Phase 7 lifecycle setup; "
            message += "deploy steps 1-5 require backtest"
            raise PydanticCustomError(
                "deploy_mode",
                message,
            )
        return mode

    @field_validator("infisical_url")
    @classmethod
    def local_infisical_origin(cls, value: str | None) -> str | None:
        return None if value is None else validate_infisical_origin(value)

    @model_validator(mode="after")
    def heartbeat_is_approved(self) -> DeployConfig:
        _ = validate_secret_references(
            self.tokens.kalshi_api_key_env,
            self.tokens.kalshi_private_key_pem_env,
        )
        if self.tokens.kalshi_api_key_env is None and (
            self.secret_approvals.reconcile_incomplete or self.secret_approvals.replace_existing
        ):
            raise PydanticCustomError(
                "deploy_secret_approval_source",
                "noninteractive secret approval requires environment references",
            )
        if frozenset(self.approvals.model_fields_set) != _REQUIRED_APPROVALS:
            raise PydanticCustomError(
                "deploy_approvals",
                "all deployment approval flags must be explicit in config mode",
            )
        if self.heartbeat_every == "0m" and not self.approvals.heartbeat_change:
            raise PydanticCustomError(
                "heartbeat_approval",
                "heartbeat_every 0m requires approvals.heartbeat_change=true",
            )
        return self

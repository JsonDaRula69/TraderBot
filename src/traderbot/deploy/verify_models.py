"""Define typed requests and results for deployment verification."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_core import PydanticCustomError

from traderbot.deploy.validation import validate_infisical_origin
from traderbot.kalshi.order_models import MarketCategory
from traderbot.paths import get_data_dir


class CheckId(StrEnum):
    GATEWAY = "gateway"
    AGENTS_WORKSPACES = "agents_workspaces"
    CRON = "cron"
    HEARTBEAT = "heartbeat"
    AUTH_MODE = "auth_mode"
    TOKENS = "tokens"
    KALSHI = "kalshi"
    DB_GLOBAL = "db_global"
    DB_DECISIONS = "db_decisions"
    DAEMON_SERVICE = "daemon_service"
    DAEMON_RUNTIME = "daemon_runtime"
    CHROMA = "chroma"
    INFISICAL = "infisical"


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    DEGRADED = "degraded"


class OverallStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class FrozenModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)


class VerificationRequest(FrozenModel):
    categories: tuple[MarketCategory, ...] = Field(min_length=1)
    mode: Literal["backtest", "paper", "live"] = "backtest"
    sysadmin_workspace: Path | None = None
    category_workspaces: dict[MarketCategory, Path] = Field(default_factory=dict)
    data_root: Path = Field(default_factory=get_data_dir)
    infisical_origin: str = "http://localhost:8080"
    daemon_mcp_url: str = "http://127.0.0.1:8765/mcp"
    timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    # Deploy-owned posture: required checks assert exactly what the deployment
    # wrote; everything else is reported as advisory divergence. Standalone
    # verification keeps its strict defaults (daemon health required, posture
    # reported), while the wizard path threads the contract it actually owes.
    heartbeat_policy: Literal["preserve", "require_0m"] = "preserve"
    created_agents: tuple[str, ...] = ()
    daemon_required: bool = True

    @field_validator("categories")
    @classmethod
    def unique_categories(
        cls, categories: tuple[MarketCategory, ...]
    ) -> tuple[MarketCategory, ...]:
        if len(set(categories)) != len(categories):
            raise PydanticCustomError("duplicate_category", "categories must be unique")
        order = {category: index for index, category in enumerate(MarketCategory)}
        return tuple(sorted(categories, key=order.__getitem__))

    @field_validator("data_root")
    @classmethod
    def absolute_data_root(cls, path: Path) -> Path:
        if not path.is_absolute():
            raise PydanticCustomError("data_root", "data root must be absolute")
        return path

    @field_validator("infisical_origin")
    @classmethod
    def loopback_infisical(cls, value: str) -> str:
        return validate_infisical_origin(value)

    @field_validator("daemon_mcp_url")
    @classmethod
    def loopback_mcp(cls, value: str) -> str:
        from urllib.parse import urlsplit

        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise PydanticCustomError("daemon_mcp_url", "daemon MCP URL is ambiguous")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.port != 8765
        ):
            raise PydanticCustomError("daemon_mcp_url", "daemon MCP URL must be loopback HTTP")
        if (
            parsed.path != "/mcp"
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise PydanticCustomError(
                "daemon_mcp_url", "daemon MCP URL must target the /mcp endpoint"
            )
        return value


class ProbeResult(FrozenModel):
    status: CheckStatus
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(min_length=1, max_length=240)

    @classmethod
    def passed(cls, action: str, message: str = "Check passed") -> ProbeResult:
        return cls(status=CheckStatus.PASS, action=action, message=message)

    @classmethod
    def failed(cls, action: str, message: str) -> ProbeResult:
        return cls(status=CheckStatus.FAIL, action=action, message=message)

    @classmethod
    def degraded(cls, action: str, message: str) -> ProbeResult:
        return cls(status=CheckStatus.DEGRADED, action=action, message=message)


class TokenProbe(FrozenModel):
    result: ProbeResult
    token: SecretStr | None


class CheckResult(FrozenModel):
    id: CheckId
    status: CheckStatus
    required: bool
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(min_length=1, max_length=240)
    elapsed_ms: int = Field(ge=0, le=300_000)
    dependency: CheckId | None = None


class VerificationResult(FrozenModel):
    overall: OverallStatus
    checks: tuple[CheckResult, ...]


__all__ = [
    "CheckId",
    "CheckResult",
    "CheckStatus",
    "OverallStatus",
    "ProbeResult",
    "TokenProbe",
    "VerificationRequest",
    "VerificationResult",
]

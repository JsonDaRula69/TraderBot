"""Typed configuration boundary for non-interactive deployment."""

from pathlib import Path
from typing import Annotated, ClassVar, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from traderbot.kalshi.models import MarketCategory


class DeployTokens(TypedDict, total=False):
    """Optional provider credentials supplied by a deploy document."""

    kalshi_api_key: str
    kalshi_private_key_pem: str


class DeployConfig(BaseModel):
    """Validated representation of a deploy.json document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    categories: list[MarketCategory]
    mode: Literal["backtest"]
    infisical_url: str | None = None
    kalshi_environment: Literal["production", "demo"] = "production"
    tokens: DeployTokens = Field(default_factory=DeployTokens)
    months_backfill: Annotated[int, Field(gt=0)] = 6
    sysadmin_workspace: Path | None = None
    category_workspaces: dict[MarketCategory, Path] = Field(default_factory=dict)

    @field_validator("mode", mode="before")
    @classmethod
    def backtest_only(cls, mode: str) -> str:
        if mode != "backtest":
            raise PydanticCustomError(
                "deploy_mode",
                "paper/live mode requires Phase 7 lifecycle setup; steps 1-3 require backtest",
            )
        return mode

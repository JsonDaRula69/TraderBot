"""Typed configuration boundary for non-interactive deployment."""

from typing import Annotated, ClassVar, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import MarketCategory


class DeployTokens(TypedDict, total=False):
    """Optional provider credentials supplied by a deploy document."""

    kalshi_api_key: str
    kalshi_private_key_pem: str


class DeployConfig(BaseModel):
    """Validated representation of a deploy.json document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    categories: list[MarketCategory]
    mode: Literal["backtest", "paper", "live"]
    infisical_url: str | None = None
    kalshi_environment: Literal["production", "demo"] = "production"
    tokens: DeployTokens = Field(default_factory=DeployTokens)
    months_backfill: Annotated[int, Field(gt=0)] = 6

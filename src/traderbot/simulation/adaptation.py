"""Bayesian adaptation data models — priors, posteriors, and strategy adjustments."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketCategory(StrEnum):
    """Market categories for per-category adaptation."""

    POLITICS = "Politics"
    ECONOMICS = "Economics"
    SCIENCE = "Science"
    SPORTS = "Sports"
    CRYPTO = "Crypto"
    CULTURE = "Culture"
    TECH = "Tech"
    WEATHER = "Weather"


class Prior(BaseModel):
    """Bayesian prior for a strategy parameter within a market category."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    mean: float
    variance: Annotated[float, Field(gt=0)]
    sample_count: Annotated[int, Field(ge=0)]
    last_updated: datetime


class Posterior(BaseModel):
    """Posterior distribution after Bayesian update with observations."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    mean: float
    variance: Annotated[float, Field(gt=0)]
    sample_count: Annotated[int, Field(ge=0)]
    last_updated: datetime
    observations: list[float]
    updated_mean: float
    updated_variance: Annotated[float, Field(gt=0)]


class AdaptationConfig(BaseModel):
    """Configuration for the Bayesian adaptation engine."""

    model_config = ConfigDict(strict=True, extra="forbid")

    learning_rate: Annotated[float, Field(gt=0, le=1.0)]
    min_observations: Annotated[int, Field(ge=1)]
    confidence_threshold: Annotated[float, Field(gt=0, le=1.0)]
    decay_rate: Annotated[float, Field(gt=0, le=1.0)]


class AdaptationResult(BaseModel):
    """Result of a single Bayesian adaptation step."""

    model_config = ConfigDict(strict=True, extra="forbid")

    category: MarketCategory
    direction: Literal["increase", "decrease", "maintain"]
    magnitude: Annotated[float, Field(gt=0)]
    confidence: Annotated[float, Field(gt=0, le=1.0)]
    reasoning: str


class StrategyAdjustment(BaseModel):
    """A concrete strategy parameter change proposed by adaptation."""

    model_config = ConfigDict(strict=True, extra="forbid")

    field_name: str
    old_value: float
    new_value: float
    justification: str
    confidence: Annotated[float, Field(gt=0, le=1.0)]

"""Pydantic v2 data models for weather-based market data and trading signals."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CityForecast(BaseModel):
    """Single-city weather forecast from a data provider.

    All temperature values are in Fahrenheit.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    city: str
    lat: float
    lon: float
    date: date
    high_temp_f: float
    low_temp_f: float
    precip_prob: float = Field(ge=0.0, le=1.0)
    wind_speed: float = Field(ge=0.0)
    detailed_forecast: str = ""
    source: Literal["nws", "open-meteo", "gfs", "ecmwf", "gem"]


class EnsembleRun(BaseModel):
    """A single model run within a multi-model ensemble forecast."""

    model_config = ConfigDict(strict=True, extra="forbid")

    model_name: str
    forecast_temp_f: float
    valid_time: datetime


class ModelConsensus(BaseModel):
    """Aggregated consensus across multiple forecast models."""

    model_config = ConfigDict(strict=True, extra="forbid")

    mean_temp: float
    std_dev: float
    spread: float
    models_used: list[str]
    agreement_score: float = Field(ge=0.0, le=1.0)


class BiasReport(BaseModel):
    """Historical accuracy report for a specific model/location combination."""

    model_config = ConfigDict(strict=True, extra="forbid")

    city: str
    model: str
    total_comparisons: int = Field(ge=0)
    mean_error: float
    mean_abs_error: float = Field(ge=0.0)
    std_error: float = Field(ge=0.0)
    last_n_days: int = Field(ge=1)


class TradingSignal(BaseModel):
    """Trading recommendation derived from weather forecast analysis."""

    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    direction: Literal["yes", "no"]
    estimated_prob: float = Field(ge=0.0, le=1.0)
    market_prob: float = Field(ge=0.0, le=1.0)
    edge: float
    confidence: float = Field(ge=0.0, le=1.0)
    model_consensus: float = Field(ge=0.0, le=1.0)
    bias_adjustment: float
    reasoning: str

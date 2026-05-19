from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MarketData:
    ticker: str
    city: str
    strike_type: str
    threshold: float
    resolution_date: str
    floor_strike: float | None = None
    ceiling_strike: float | None = None
    settlement_result: str | None = None


@dataclass(frozen=True)
class ForecastData:
    forecast_temp_f: float
    source: str
    days_before: int
    timestep: int


@dataclass(frozen=True)
class AccuracyData:
    city: str
    lead_time: int
    mae: float
    bias: float
    sample_count: int
    low_confidence: bool = False


@dataclass(frozen=True)
class PriceData:
    yes_price: float
    no_price: float
    trade_count: int
    open_interest: int
    implied_prob: float


@dataclass(frozen=True)
class TechnicalData:
    rsi: float
    bollinger_position: float
    ema5: float
    ema20: float
    signal_direction: str
    signal_confidence: float


@dataclass(frozen=True)
class PriorDecisions:
    decisions: list


@dataclass(frozen=True)
class TreatmentContext:
    market: MarketData
    forecast: ForecastData
    accuracy: AccuracyData
    prices: PriceData
    technicals: TechnicalData
    prior: PriorDecisions
    timestep: int
    remaining: int


@dataclass(frozen=True)
class TreatmentResponse:
    decision: str
    estimated_prob: float
    confidence: float
    reasoning: str


class TreatmentInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def format_prompt(self, ctx: TreatmentContext) -> str: ...

    @abstractmethod
    def validate_response(self, response: dict) -> bool: ...

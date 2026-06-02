import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketData:
    ticker: str
    strike_type: Literal["between", "less", "greater"]
    threshold: float
    expiration: datetime
    category: str


@dataclass(frozen=True)
class ForecastData:
    forecast_temp_f: float
    source: str
    days_before: int


@dataclass(frozen=True)
class AccuracyData:
    brier_score: float | None
    calibration_error: float | None
    sample_size: int


@dataclass(frozen=True)
class PriceData:
    current_yes_cents: int
    current_no_cents: int
    history: list[int]
    spread_cents: int


@dataclass(frozen=True)
class TechnicalData:
    rsi: float | None
    bb_upper: float | None
    bb_lower: float | None
    ema_short: float | None
    ema_long: float | None


@dataclass(frozen=True)
class PriorDecisions:
    decisions: list[dict]


@dataclass(frozen=True)
class TreatmentContext:
    market: MarketData
    forecast: ForecastData
    accuracy: AccuracyData
    prices: PriceData
    technical: TechnicalData
    prior: PriorDecisions
    system_context: str = ""


@dataclass(frozen=True)
class ValidatedDecision:
    decision: Literal["buy_yes", "buy_no", "skip"]
    estimated_prob: float
    confidence: float
    reasoning: str

    def __post_init__(self) -> None:
        if self.decision not in ("buy_yes", "buy_no", "skip"):
            raise ValueError(
                f"decision must be 'buy_yes', 'buy_no', or 'skip', got {self.decision!r}"
            )
        if not (0.0 <= self.estimated_prob <= 1.0):
            raise ValueError(f"estimated_prob must be in [0.0, 1.0], got {self.estimated_prob}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


class TreatmentInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def bypass_llm(self) -> bool:
        return False

    @abstractmethod
    def format_prompt(self, ctx: TreatmentContext) -> str: ...

    @abstractmethod
    def validate_response(self, response: dict) -> ValidatedDecision: ...

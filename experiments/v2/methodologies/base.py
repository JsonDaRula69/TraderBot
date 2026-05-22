from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from .db_utils import get_connection


@dataclass
class MethodologyResult:
    """Holds the output of a methodology's probability estimate."""

    estimated_prob: float
    confidence: float
    reasoning: dict = field(default_factory=dict)

    def __post_init__(self):
        # Clamp estimated_prob to [0.01, 0.99]
        if self.estimated_prob < 0.01:
            self.estimated_prob = 0.01
        elif self.estimated_prob > 0.99:
            self.estimated_prob = 0.99

        # Clamp confidence to [0.1, 1.0]
        if self.confidence < 0.1:
            self.confidence = 0.1
        elif self.confidence > 1.0:
            self.confidence = 1.0


class MethodologyInterface(ABC):
    """Abstract base class for all methodologies."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    @abstractmethod
    def estimate(
        self,
        ticker: str,
        forecast: dict,
        timestep: int,
        prior_decisions: list,
    ) -> MethodologyResult:
        """Return a probability estimate for the given ticker and forecast."""
        ...

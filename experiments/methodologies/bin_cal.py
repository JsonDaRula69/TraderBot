"""Bin Calibration methodology — uses historical calibration bins to estimate probabilities."""

from __future__ import annotations

from pathlib import Path

from .base import MethodologyInterface, MethodologyResult
from .db_utils import get_calibration_bins
from .ticker_parser import parse_weather_ticker

# Delta bins: (lower, upper, label)
# Label format matches calibration_bins table bin_label column.
_BINS: list[tuple[float, float, str]] = [
    (float("-inf"), -8, "(-inf,-8)"),
    (-8, -4, "[-8,-4)"),
    (-4, -2, "[-4,-2)"),
    (-2, 0, "[-2,0)"),
    (0, 2, "[0,2)"),
    (2, 4, "[2,4)"),
    (4, 8, "[4,8)"),
    (8, float("inf"), "[8,+inf)"),
]

_MIN_SAMPLES = 10


def _assign_bin_label(delta: float) -> str:
    """Map a delta value to its calibration bin label."""
    for lower, upper, label in _BINS:
        if lower <= delta < upper:
            return label
    # Fallback — should not happen with infinite bounds
    return _BINS[-1][2]


class BinCalMethodology(MethodologyInterface):
    """Estimate probability via bin-level historical calibration.

    For each forecast delta (distance from threshold), looks up the empirical
    accuracy of past forecasts in the same delta bin.  Falls back to a uniform
    prior (0.5, low confidence) when fewer than 10 samples exist.
    """

    NAME = "bin_cal"

    def __init__(self, db_path: Path):
        super().__init__(db_path)

    def estimate(
        self,
        ticker: str,
        forecast: dict,
        timestep: int,
        prior_decisions: list,
    ) -> MethodologyResult:
        parsed = parse_weather_ticker(ticker)
        direction = parsed["direction"]
        threshold = parsed["threshold"]

        forecast_temp = forecast.get("temp_max_f")
        if forecast_temp is None:
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={"prior_type": "uniform", "error": "no temp_max_f in forecast"},
            )

        delta = (forecast_temp - threshold) if direction == "above" else (threshold - forecast_temp)

        bin_label = _assign_bin_label(delta)

        cal_row = get_calibration_bins(self.conn, bin_label)

        # Insufficient data — uniform prior fallback
        if cal_row is None or cal_row.get("count", 0) < _MIN_SAMPLES:
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={
                    "bin_range": bin_label,
                    "sample_count": cal_row.get("count", 0) if cal_row else 0,
                    "historical_accuracy": cal_row.get("actual_rate") if cal_row else None,
                    "delta": delta,
                    "prior_type": "uniform",
                },
            )

        count = cal_row["count"]
        actual_rate = cal_row["actual_rate"]
        correct_count = round(actual_rate * count)

        # Beta posterior mean: (correct + 1) / (total + 2)
        alpha = correct_count + 1
        beta = count - correct_count + 1
        estimated_prob = alpha / (alpha + beta)

        confidence = min(1.0, count / 50.0)

        return MethodologyResult(
            estimated_prob=estimated_prob,
            confidence=confidence,
            reasoning={
                "bin_range": bin_label,
                "sample_count": count,
                "historical_accuracy": actual_rate,
                "delta": delta,
                "prior_type": "calibrated",
            },
        )

"""Kelly criterion position sizing — pure mathematical functions."""

from __future__ import annotations


def kelly_criterion(prob: float, odds: float) -> float:
    if prob <= 0 or prob >= 1 or odds <= 0:
        return 0.0
    q = 1 - prob
    f = (odds * prob - q) / odds
    return max(0.0, f)


def fractional_kelly(prob: float, odds: float, fraction: float = 0.5) -> float:
    full = kelly_criterion(prob, odds)
    if full <= 0:
        return 0.0
    clamped = max(0.1, min(0.5, fraction))
    return full * clamped


def confidence_scaled_size(kelly_fraction: float, confidence: float, bankroll_cents: int) -> int:
    if bankroll_cents <= 0 or kelly_fraction <= 0:
        return 0
    clamped_confidence = max(0.0, min(1.0, confidence))
    if clamped_confidence <= 0:
        return 0
    return int(kelly_fraction * clamped_confidence * bankroll_cents)


def sized_position_for_trade(
    prob: float,
    odds: float,
    confidence: float,
    bankroll_cents: int,
    max_position_cents: int,
) -> int:
    fk = fractional_kelly(prob, odds, 0.5)
    sized = confidence_scaled_size(fk, confidence, bankroll_cents)
    return min(sized, max_position_cents)

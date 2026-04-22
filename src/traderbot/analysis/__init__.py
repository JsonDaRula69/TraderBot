"""Statistical computation and signal generation for binary prediction markets."""

from __future__ import annotations

from traderbot.analysis.indicators import (
    BollingerBands,
    IndicatorResult,
    MovingAverageResult,
    bollinger_bands,
    ema,
    rsi,
    sma,
    volume_weighted_price,
)
from traderbot.analysis.odds import (
    EdgeEstimate,
    ImpliedProb,
    KellyInputs,
    compute_kelly_inputs,
    detect_edge,
    expected_value,
    implied_probability,
)
from traderbot.analysis.portfolio import (
    PortfolioMetrics,
    brier_score,
    calibration_curve,
    calmar_ratio,
    edge_realization,
    max_drawdown,
    sharpe_ratio,
    win_rate,
)
from traderbot.analysis.registry import (
    AnalysisRegistry,
    CategoryAnalyzer,
    CategorySignals,
    GenericAnalyzer,
)
from traderbot.analysis.signals import (
    CombinedSignal,
    SignalSource,
    combine_signals,
    default_weights,
    generate_signal,
)

__all__ = [
    "AnalysisRegistry",
    "BollingerBands",
    "CategoryAnalyzer",
    "CategorySignals",
    "CombinedSignal",
    "EdgeEstimate",
    "GenericAnalyzer",
    "ImpliedProb",
    "IndicatorResult",
    "KellyInputs",
    "MovingAverageResult",
    "PortfolioMetrics",
    "SignalSource",
    "bollinger_bands",
    "brier_score",
    "calibration_curve",
    "calmar_ratio",
    "combine_signals",
    "compute_kelly_inputs",
    "default_weights",
    "detect_edge",
    "edge_realization",
    "ema",
    "expected_value",
    "generate_signal",
    "implied_probability",
    "max_drawdown",
    "rsi",
    "sharpe_ratio",
    "sma",
    "volume_weighted_price",
    "win_rate",
]

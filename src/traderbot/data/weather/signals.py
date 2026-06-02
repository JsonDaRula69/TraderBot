"""Weather-based trading signal engine using forecast-vs-market edge detection.

Combines NWS forecast data with model consensus scoring, historical bias
adjustment, and market-implied probability comparison to produce actionable
TradingSignal instances.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from traderbot.analysis.odds import implied_probability
from traderbot.data.base_signals import BaseSignalEngine
from traderbot.data.models import CityForecast, TradingSignal
from traderbot.db import get_connection
from traderbot.db.forecast_bias import query_bias as _query_bias

if TYPE_CHECKING:
    from traderbot.experiment.shared import MarketData
    from traderbot.kalshi.models import OrderBook

logger = logging.getLogger(__name__)

_TICKER_TO_CITY: dict[str, str] = {
    "KXHIGHNY": "New York",
    "KXHIGHPHIL": "Philadelphia",
    "KXHIGHTPHX": "Phoenix",
    "KXHIGHTMIN": "Minneapolis",
    "KXHIGHTSEA": "Seattle",
    "KXHIGHTCHI": "Chicago",
    "KXHIGHTHOU": "Houston",
    "KXHIGHTLA": "Los Angeles",
    "KXHIGHTMIA": "Miami",
    "KXHIGHTDEN": "Denver",
    "KXHIGHTATL": "Atlanta",
    "KXHIGHTBOS": "Boston",
    "KXHIGHTDAL": "Dallas",
    "KXHIGHTDET": "Detroit",
    "KXHIGHTSF": "San Francisco",
}


def _estimate_prob_from_threshold(
    forecast_temp: float, threshold: float, strike_type: str
) -> float:
    import math

    sigma = 5.0
    z = (forecast_temp - threshold) / sigma

    if strike_type == "greater":
        prob = 1.0 / (1.0 + math.exp(-z))
    elif strike_type == "less":
        prob = 1.0 / (1.0 + math.exp(z))
    else:
        prob = 0.5

    logger.debug(
        "Logistic probability: forecast=%.1f threshold=%.1f strike=%s prob=%.4f",
        forecast_temp,
        threshold,
        strike_type,
        prob,
    )
    return prob


def _compute_agreement_penalty(consensus_score: float | None) -> float:
    """Convert a model-consensus agreement score into a confidence multiplier.

    When agreement is high (≥0.8), confidence is barely reduced.
    When agreement is low (<0.5), confidence is penalized heavily.
    Missing consensus data is treated as neutral (multiplier = 0.7).
    """
    if consensus_score is None:
        return 0.7
    if consensus_score < 0.3:
        return 0.3
    if consensus_score < 0.5:
        return 0.5
    if consensus_score < 0.7:
        return 0.7
    if consensus_score < 0.8:
        return 0.8
    return 0.95


class WeatherSignalEngine(BaseSignalEngine):
    """Computes trading signals by comparing weather forecasts against market odds.

    For each market that maps to a city with an available forecast, the engine:
    1. Computes an estimated probability from the forecast-vs-threshold relationship.
    2. Extracts market-implied probability from an order book (when available).
    3. Calculates the edge as the difference between estimated and market probability.
    4. Adjusts confidence using model-consensus agreement and historical forecast bias.

    Order books are passed separately via ``orderbooks`` and matched by ticker.
    """

    def __init__(self, orderbooks: dict[str, OrderBook] | None = None) -> None:
        """Create a WeatherSignalEngine.

        Args:
            orderbooks: Optional mapping of Kalshi ticker → OrderBook.
                When provided, market-implied probabilities are extracted from
                live bid data. When omitted, a neutral 0.50 is used.
        """
        self._orderbooks: dict[str, OrderBook] = orderbooks or {}

    def set_orderbooks(self, orderbooks: dict[str, OrderBook]) -> None:
        """Replace the order-book lookup used for market-probability extraction."""
        self._orderbooks = orderbooks

    def compute_signals(
        self,
        forecasts: dict[str, CityForecast],
        markets: dict[str, MarketData],
    ) -> list[TradingSignal]:
        """Compute trading signals from weather forecasts and market data.

        Matches markets to forecasts via the Kalshi ticker → city mapping,
        then generates a TradingSignal for every market that has a
        corresponding city forecast.

        Args:
            forecasts: City name → CityForecast from a data provider.
            markets: Ticker → MarketData for active Kalshi markets.

        Returns:
            List of TradingSignal recommendations, one per matched market.
        """
        city_forecasts: dict[str, CityForecast] = {}
        for fc in forecasts.values():
            city_forecasts[fc.city] = fc

        signals: list[TradingSignal] = []
        for ticker, market in markets.items():
            city = _TICKER_TO_CITY.get(ticker)
            if city is None:
                continue

            fc = city_forecasts.get(city)
            if fc is None:
                logger.debug("No forecast available for city=%s ticker=%s", city, ticker)
                continue

            try:
                signal = self._compute_one(ticker, market, fc)
                signals.append(signal)
            except Exception:
                logger.exception("Signal computation failed for ticker=%s", ticker)

        logger.info(
            "compute_signals: %d tickers processed, %d signals generated",
            len(markets),
            len(signals),
        )
        return signals

    def _compute_one(self, ticker: str, market: MarketData, fc: CityForecast) -> TradingSignal:
        forecast_temp = fc.high_temp_f

        estimated_prob = _estimate_prob_from_threshold(
            forecast_temp, market.threshold, market.strike_type
        )

        market_prob = self._get_market_prob(ticker)

        edge = estimated_prob - market_prob
        direction: str = "yes" if edge > 0.01 else "no" if edge < -0.01 else "neutral"
        if direction == "neutral":
            direction = "yes" if estimated_prob > 0.5 else "no"

        consensus_score = self._get_consensus_score(ticker)
        agreement_mult = _compute_agreement_penalty(consensus_score)

        bias_adjustment = self._query_bias_adjustment(fc.city)
        base_confidence = min(abs(edge), 0.5) / 0.5
        confidence = base_confidence * agreement_mult * (1.0 - abs(bias_adjustment))
        confidence = max(0.0, min(1.0, confidence))

        return TradingSignal(
            ticker=ticker,
            direction=direction,
            estimated_prob=round(estimated_prob, 4),
            market_prob=round(market_prob, 4),
            edge=round(edge, 4),
            confidence=round(confidence, 4),
            model_consensus=round(consensus_score, 4) if consensus_score is not None else 0.5,
            bias_adjustment=round(bias_adjustment, 4),
            reasoning=(
                f"{fc.city}: forecast={forecast_temp}°F, threshold={market.threshold}°F "
                f"({market.strike_type}), est={estimated_prob:.3f}, "
                f"market={market_prob:.3f}, edge={edge:+.3f}, "
                f"consensus={consensus_score or 'N/A'}, bias_adj={bias_adjustment:.3f}"
            ),
        )

    def _get_market_prob(self, ticker: str) -> float:
        """Extract market-implied probability from the order book for a ticker.

        Falls back to 0.50 when no order book is available.
        """
        ob = self._orderbooks.get(ticker)
        if ob is None:
            return 0.5
        try:
            return implied_probability(ob).yes_prob
        except (ValueError, AttributeError):
            return 0.5

    @staticmethod
    def _get_consensus_score(ticker: str) -> float | None:
        """Retrieve the latest cached model-consensus agreement score.

        Stub: returns None, indicating no cached consensus is available.
        In production, this would query a consensus cache populated by
        WeatherDataProvider.get_model_consensus().
        """
        return None

    @staticmethod
    def _query_bias_adjustment(city: str, model: str = "nws", days: int = 90) -> float:
        """Query the forecast_bias SQLite table and return a normalized bias adjustment.

        Returns a value in [-1, 1] where 0 = no systematic bias and
        ±1 = extreme bias. Positive bias means the model historically
        over-predicts (actual > forecast), negative = under-predicts.
        """
        try:
            with get_connection() as conn:
                stats = _query_bias(conn, city, model, days)
        except Exception:
            logger.exception("Bias query failed for city=%s model=%s", city, model)
            return 0.0

        if stats["count"] < 5:
            return 0.0

        max_error = 10.0
        norm = max(-1.0, min(1.0, stats["mean_error"] / max_error))
        logger.debug(
            "Bias adjustment for %s: mean_error=%.3f adjustment=%.4f",
            city,
            stats["mean_error"],
            norm,
        )
        return norm

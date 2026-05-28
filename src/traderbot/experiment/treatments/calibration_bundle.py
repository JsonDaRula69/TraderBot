"""Calibration bundle treatment — V3 prompt with full forecast accuracy and technical context."""

import logging

from traderbot.experiment.shared import (
    TreatmentContext,
    TreatmentInterface,
    ValidatedDecision,
)

logger = logging.getLogger(__name__)


class CalibrationBundleTreatment(TreatmentInterface):
    """Treatment that provides the LLM with a calibration-rich prompt bundle.

    Includes forecast data, accuracy metrics, market prices, technical
    indicators, prior decisions, and system context.  The LLM is asked to
    return a structured JSON decision.
    """

    _markets_processed: int = 0

    @property
    def name(self) -> str:
        return "calibration_bundle"

    @property
    def bypass_llm(self) -> bool:
        return False

    def format_prompt(self, ctx: TreatmentContext) -> str:
        self._markets_processed += 1
        logger.info("Calibration bundle: processing market %d", self._markets_processed)
        m = ctx.market
        f = ctx.forecast
        a = ctx.accuracy
        p = ctx.prices
        t = ctx.technical

        brier = f"{a.brier_score:.3f}" if a.brier_score is not None else "N/A"
        cal_err = f"{a.calibration_error:.3f}" if a.calibration_error is not None else "N/A"
        rsi = f"{t.rsi:.1f}" if t.rsi is not None else "N/A"
        bb_upper = f"{t.bb_upper:.1f}" if t.bb_upper is not None else "N/A"
        bb_lower = f"{t.bb_lower:.1f}" if t.bb_lower is not None else "N/A"
        ema_short = f"{t.ema_short:.1f}" if t.ema_short is not None else "N/A"
        ema_long = f"{t.ema_long:.1f}" if t.ema_long is not None else "N/A"

        price_trend = "rising" if len(p.history) >= 2 and p.history[-1] > p.history[0] else \
                      "falling" if len(p.history) >= 2 and p.history[-1] < p.history[0] else "flat"

        prior_lines = ""
        if ctx.prior.decisions:
            for pd in ctx.prior.decisions:
                prior_lines += f"  - {pd}\n"
        else:
            prior_lines = "  (none)\n"

        system_section = ""
        if ctx.system_context:
            system_section = f"""
SYSTEM CONTEXT
{ctx.system_context}
"""

        return f"""You are a weather prediction market analyst. Analyze the data below and make a trading decision.

MARKET PARAMETERS
  Ticker: {m.ticker}
  Strike type: {m.strike_type}
  Threshold: {m.threshold}
  Expiration: {m.expiration.isoformat()}
  Category: {m.category}

FORECAST DATA
  Forecast temperature: {f.forecast_temp_f} F
  Source model: {f.source}
  Days before expiry: {f.days_before}

ACCURACY METRICS
  Brier score: {brier}
  Calibration error: {cal_err}
  Sample size: {a.sample_size}

CURRENT PRICES
  YES price: {p.current_yes_cents} cents
  NO price: {p.current_no_cents} cents
  Spread: {p.spread_cents} cents
  Price trend: {price_trend}

TECHNICAL INDICATORS
  RSI: {rsi}
  Bollinger Upper: {bb_upper}
  Bollinger Lower: {bb_lower}
  EMA Short: {ema_short}
  EMA Long: {ema_long}

PRIOR DECISIONS
{prior_lines}
{system_section}
INSTRUCTIONS
1. Analyze whether the forecast temperature supports the market YES/NO outcome.
2. Consider the accuracy of past forecasts using the Brier score and calibration error.
3. Use the price trend, technical indicators, and current prices to gauge market sentiment.
4. Review prior decisions for consistency or new information.
5. Return a JSON object with exactly these fields:
   - "decision": one of "buy_yes", "buy_no", or "skip"
   - "estimated_prob": your estimated probability (0.0 to 1.0)
   - "confidence": your confidence in the estimate (0.0 to 1.0)
   - "reasoning": a brief explanation of your decision

Respond ONLY with the JSON object, no other text."""

    def validate_response(self, response: dict) -> ValidatedDecision:
        decision = response.get("decision")
        if decision not in ("buy_yes", "buy_no", "skip"):
            raise ValueError(
                f"response 'decision' must be 'buy_yes', 'buy_no', or 'skip', got {decision!r}"
            )

        estimated_prob = response.get("estimated_prob")
        if estimated_prob is None:
            raise ValueError("response missing 'estimated_prob'")
        if not isinstance(estimated_prob, (int, float)):
            raise ValueError(
                f"'estimated_prob' must be numeric, got {type(estimated_prob).__name__}"
            )
        if not (0.0 <= float(estimated_prob) <= 1.0):
            raise ValueError(
                f"'estimated_prob' must be in [0.0, 1.0], got {estimated_prob}"
            )

        confidence = response.get("confidence")
        if confidence is None:
            raise ValueError("response missing 'confidence'")
        if not isinstance(confidence, (int, float)):
            raise ValueError(
                f"'confidence' must be numeric, got {type(confidence).__name__}"
            )
        if not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(
                f"'confidence' must be in [0.0, 1.0], got {confidence}"
            )

        reasoning = response.get("reasoning")
        if reasoning is None:
            raise ValueError("response missing 'reasoning'")
        if not isinstance(reasoning, str):
            raise ValueError(
                f"'reasoning' must be a string, got {type(reasoning).__name__}"
            )

        return ValidatedDecision(
            decision=decision,
            estimated_prob=float(estimated_prob),
            confidence=float(confidence),
            reasoning=reasoning,
        )

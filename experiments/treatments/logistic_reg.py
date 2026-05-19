"""LogisticRegTreatment — uses logistic regression on forecast features to estimate probability."""

from __future__ import annotations

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface


def compute_delta(ctx: TreatmentContext) -> float:
    """Compute forecast delta based on strike type.

    less → threshold - forecast_temp_f
    greater → forecast_temp_f - threshold
    between → signed distance to nearest boundary
    """
    forecast_temp = ctx.forecast.forecast_temp_f
    strike_type = ctx.market.strike_type
    threshold = ctx.market.threshold

    if strike_type == "less":
        return threshold - forecast_temp
    elif strike_type == "greater":
        return forecast_temp - threshold
    else:
        floor = ctx.market.floor_strike if ctx.market.floor_strike is not None else threshold
        ceiling = ctx.market.ceiling_strike if ctx.market.ceiling_strike is not None else threshold + 1
        dist_to_floor = forecast_temp - floor
        dist_to_ceiling = ceiling - forecast_temp
        if dist_to_floor <= dist_to_ceiling:
            return -dist_to_floor
        else:
            return dist_to_ceiling


def sigmoid(z: float) -> float:
    """Numerically stable sigmoid for scalar input."""
    if z >= 0:
        return 1.0 / (1.0 + __import__("math").exp(-z))
    else:
        ez = __import__("math").exp(z)
        return ez / (1.0 + ez)


def simple_logistic_probability(
    delta: float,
    timestep: int,
    weights: dict[str, float] | None = None,
    intercept: float = 0.0,
) -> tuple[float, dict]:
    """Compute logistic regression probability estimate.

    Uses a simple sigmoid-based approach (matching V2's _SimpleLogisticRegression).
    When no weights are provided, falls back to a delta-only heuristic.
    Returns (estimated_prob, feature_dict).
    """
    if weights is None:
        z = 0.3 * delta + intercept
        prob = sigmoid(z)
        features = {
            "forecast_delta": round(delta, 2),
            "forecast_delta_squared": round(delta ** 2, 2),
            "timestep": float(timestep),
            "weight_source": "default_heuristic",
        }
        return prob, features

    feature_values = {
        "forecast_delta": delta,
        "forecast_delta_squared": delta ** 2,
        "timestep": float(timestep),
    }

    z = intercept
    for col, val in feature_values.items():
        if col in weights:
            z += weights[col] * val

    prob = sigmoid(z)
    feature_values.update({k: round(v, 4) for k, v in feature_values.items()})
    feature_values["weight_source"] = "provided_weights"

    return prob, feature_values


class LogisticRegTreatment(TreatmentInterface):
    """Estimates probability using logistic regression on forecast features.

    Reimplements V2's logistic regression approach using V3 data structures.
    Falls back to a simple delta-based heuristic when no training weights
    are provided. The prompt includes market data, features, and the
    logistic regression estimate for the LLM to reason about.
    """

    _weights: dict[str, float] | None
    _intercept: float

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        intercept: float = 0.0,
    ) -> None:
        self._weights = weights
        self._intercept = intercept

    @property
    def name(self) -> str:
        return "logistic_reg"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        sections: list[str] = []

        if ctx.system_context:
            sections.append(
                "=== PRODUCTION AGENT SYSTEM CONTEXT ===\n"
                "The following files define the production trading agent's capabilities, "
                "constraints, and decision framework. Use them as context for your decision.\n\n"
                f"{ctx.system_context}\n"
                "=== END PRODUCTION AGENT SYSTEM CONTEXT ==="
            )

        sections.append(self._build_market_section(ctx))
        sections.append(self._build_logistic_section(ctx))
        sections.append(self._build_decision_instruction())

        return "\n\n".join(sections)

    def validate_response(self, response: dict) -> bool:
        decision = response.get("decision")
        if decision not in ("buy_yes", "buy_no", "skip"):
            return False

        prob = response.get("estimated_prob")
        if not isinstance(prob, (int, float)) or prob < 0 or prob > 1:
            return False

        confidence = response.get("confidence")
        return isinstance(confidence, (int, float))

    def _build_market_section(self, ctx: TreatmentContext) -> str:
        lines = [
            "=== MARKET DATA ===",
            f"Market: {ctx.market.ticker} — {ctx.market.city}",
            f"Strike: {ctx.market.strike_type} {ctx.market.threshold}",
            f"Resolution: {ctx.market.resolution_date}",
            "",
            f"YES price: {ctx.prices.yes_price:.2f}  |  NO price: {ctx.prices.no_price:.2f}",
            f"Implied probability: {ctx.prices.implied_prob:.2f}",
            f"Trade count: {ctx.prices.trade_count}  |  Open interest: {ctx.prices.open_interest}",
            "",
            "Forecast:",
            f"  Temperature: {ctx.forecast.forecast_temp_f}°F",
            f"  Source: {ctx.forecast.source}",
            f"  Days before resolution: {ctx.forecast.days_before}",
            "",
            "Forecast accuracy:",
            f"  City: {ctx.accuracy.city}",
            f"  Lead time: {ctx.accuracy.lead_time} days",
            f"  MAE: {ctx.accuracy.mae:.1f}°F",
            f"  Bias: {ctx.accuracy.bias:+.1f}°F",
            f"  Sample count: {ctx.accuracy.sample_count}",
        ]
        if ctx.accuracy.low_confidence:
            lines.append("  ⚠ LOW CONFIDENCE — small sample size")
        return "\n".join(lines)

    def _build_logistic_section(self, ctx: TreatmentContext) -> str:
        delta = compute_delta(ctx)
        prob, features = simple_logistic_probability(
            delta, ctx.timestep, self._weights, self._intercept
        )

        clamped_prob = max(0.01, min(0.99, prob))
        confidence = max(0.1, abs(prob - 0.5) * 2)

        if self._weights is None:
            note = (
                "Note: No trained weights available — using delta-based heuristic. "
                "The logistic estimate should be treated as low confidence."
            )
        else:
            note = "Note: Logistic regression estimate using provided feature weights."

        lines = [
            "=== LOGISTIC REGRESSION METHODOLOGY ===",
            f"Forecast delta: {delta:.2f}",
            f"Delta squared: {delta ** 2:.2f}",
            f"Strike type: {ctx.market.strike_type}",
            f"Threshold: {ctx.market.threshold}",
            f"Timestep: {ctx.timestep}",
            "",
            "Feature values:",
        ]
        for key, val in features.items():
            lines.append(f"  {key}: {val}")

        lines.extend([
            "",
            f"Logistic regression probability estimate: {clamped_prob:.4f}",
            f"Estimate confidence: {confidence:.2f}",
            note,
        ])

        if ctx.accuracy.low_confidence:
            lines.append("Note: Low accuracy confidence — logistic estimate should be weighted cautiously.")

        return "\n".join(lines)

    def _build_decision_instruction(self) -> str:
        return (
            "=== DECISION ===\n"
            "Based on the market data and logistic regression probability estimate above, "
            "make a trading decision.\n\n"
            'Respond ONLY with a JSON object: {"decision": "buy_yes"|"buy_no"|"skip", '
            '"estimated_prob": float, "confidence": float, "reasoning": string}'
        )
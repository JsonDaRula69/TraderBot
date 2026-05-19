"""BinCalTreatment — uses delta-based calibration bins to estimate probability."""

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface

# Delta bins: (lower, upper, label)
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


def assign_bin(delta: float) -> str:
    """Map a delta value to its calibration bin label."""
    for lower, upper, label in _BINS:
        if lower <= delta < upper:
            return label
    return _BINS[-1][2]


def estimate_bin_probability(delta: float, calibration_data: dict | None) -> tuple[float, float, dict]:
    """Estimate probability from bin calibration data.

    Returns (estimated_prob, confidence, reasoning_dict).
    Falls back to (0.5, 0.1, uniform-prior reasoning) when < 10 samples.
    """
    bin_label = assign_bin(delta)

    if calibration_data is None or calibration_data.get("count", 0) < _MIN_SAMPLES:
        sample_count = calibration_data.get("count", 0) if calibration_data else 0
        historical_accuracy = calibration_data.get("actual_rate") if calibration_data else None
        return (
            0.5,
            0.1,
            {
                "bin_range": bin_label,
                "sample_count": sample_count,
                "historical_accuracy": historical_accuracy,
                "delta": round(delta, 2),
                "prior_type": "uniform",
            },
        )

    count = calibration_data["count"]
    actual_rate = calibration_data["actual_rate"]
    correct_count = round(actual_rate * count)

    alpha = correct_count + 1
    beta = count - correct_count + 1
    estimated_prob = alpha / (alpha + beta)
    confidence = min(1.0, count / 50.0)

    return (
        estimated_prob,
        confidence,
        {
            "bin_range": bin_label,
            "sample_count": count,
            "historical_accuracy": round(actual_rate, 4),
            "delta": round(delta, 2),
            "prior_type": "calibrated",
        },
    )


class BinCalTreatment(TreatmentInterface):
    """Uses delta-based historical calibration bins to estimate probability.

    Computes forecast delta, maps it to a calibration bin, and includes
    the bin-level historical accuracy in the prompt so the LLM can reason
    about calibrated probabilities alongside market data.
    """

    _calibration_data: dict | None

    def __init__(self, calibration_data: dict | None = None) -> None:
        self._calibration_data = calibration_data

    @property
    def name(self) -> str:
        return "bin_cal"

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
        sections.append(self._build_bin_cal_section(ctx))
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

    def _build_bin_cal_section(self, ctx: TreatmentContext) -> str:
        delta = compute_delta(ctx)
        estimated_prob, confidence, reasoning = estimate_bin_probability(
            delta, self._calibration_data
        )

        lines = [
            "=== BIN CALIBRATION METHODOLOGY ===",
            f"Forecast delta: {delta:.2f}",
            f"Delta bin: {reasoning['bin_range']}",
            f"Prior type: {reasoning['prior_type']}",
            f"Bin historical accuracy: {reasoning.get('historical_accuracy', 'N/A')}",
            f"Bin sample count: {reasoning['sample_count']}",
            f"Estimated probability (bin-calibrated): {estimated_prob:.4f}",
            f"Calibration confidence: {confidence:.2f}",
        ]
        if ctx.accuracy.low_confidence:
            lines.append("Note: Low accuracy confidence — bin estimate should be weighted cautiously.")

        return "\n".join(lines)

    def _build_decision_instruction(self) -> str:
        return (
            "=== DECISION ===\n"
            "Based on the market data and bin-calibrated probability estimate above, "
            "make a trading decision.\n\n"
            'Respond ONLY with a JSON object: {"decision": "buy_yes"|"buy_no"|"skip", '
            '"estimated_prob": float, "confidence": float, "reasoning": string}'
        )
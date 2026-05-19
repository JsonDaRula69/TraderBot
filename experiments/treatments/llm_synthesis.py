"""LLMSynthesisTreatment — uses the LLM itself to estimate probability from raw market data."""

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface


class LLMSynthesisTreatment(TreatmentInterface):
    """Asks the LLM to directly estimate probability from market data.

    This is the V2-style "let the LLM reason about the data" approach.
    The prompt presents the market data, forecast, and accuracy information,
    then asks the LLM to estimate probability and make a decision.
    Unlike the other treatments, there is no pre-computed statistical
    estimate — the LLM provides both the reasoning and the probability.
    """

    @property
    def name(self) -> str:
        return "llm_synthesis"

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
        sections.append(self._build_synthesis_instruction(ctx))
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

    def _build_synthesis_instruction(self, ctx: TreatmentContext) -> str:
        lines = [
            "=== PROBABILITY ESTIMATION TASK ===",
            "You are a weather market analyst. Estimate the probability that this prediction "
            "market resolves YES based on the market data above.",
            "",
            f"Consider the forecast temperature ({ctx.forecast.forecast_temp_f}°F) relative "
            f"to the {ctx.market.strike_type} threshold ({ctx.market.threshold}°F).",
            f"Factor in the forecast accuracy: MAE of {ctx.accuracy.mae:.1f}°F "
            f"with {'a' if ctx.accuracy.bias >= 0 else ''} bias of {ctx.accuracy.bias:+.1f}°F.",
            f"The market currently implies a {ctx.prices.implied_prob:.0%} probability.",
            "",
            "Reason step by step about whether the forecast temperature will exceed (for 'greater' "
            "strike types) or fall below (for 'less' strike types) the threshold. Consider the "
            "forecast accuracy — the actual temperature has historically been off by the MAE — "
            "and whether the forecast bias suggests systematic over- or under-prediction.",
        ]

        if ctx.accuracy.low_confidence:
            lines.append(
                "⚠ The accuracy data has LOW CONFIDENCE. Weight your estimate accordingly."
            )

        lines.extend([
            "",
            "Provide your estimated_prob (0.0 to 1.0) and confidence (0.0 to 1.0) in your response.",
        ])

        return "\n".join(lines)

    def _build_decision_instruction(self) -> str:
        return (
            "=== DECISION ===\n"
            "Based on your probability estimation above, make a trading decision.\n\n"
            'Respond ONLY with a JSON object: {"decision": "buy_yes"|"buy_no"|"skip", '
            '"estimated_prob": float, "confidence": float, "reasoning": string}'
        )
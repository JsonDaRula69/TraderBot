"""ControlTreatment — production-mirroring control with OpenClaw workspace context."""

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface


class ControlTreatment(TreatmentInterface):
    @property
    def name(self) -> str:
        return "control"

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

        lines += [
            "",
            "Technical indicators:",
            f"  RSI(14): {ctx.technicals.rsi:.1f}",
            f"  Bollinger position: {ctx.technicals.bollinger_position:.2f}",
            f"  EMA(5): {ctx.technicals.ema5:.1f}",
            f"  EMA(20): {ctx.technicals.ema20:.1f}",
            f"  Signal direction: {ctx.technicals.signal_direction}",
            f"  Signal confidence: {ctx.technicals.signal_confidence:.2f}",
        ]

        if ctx.prior.decisions:
            lines += [
                "",
                "Prior decisions on this market:",
            ]
            for d in ctx.prior.decisions:
                ts = d.get("timestep", "?")
                dec = d.get("decision", "?")
                prob = d.get("estimated_prob", 0.0)
                lines.append(f"  Timestep {ts}: {dec} (est. prob={float(prob):.2f})")
        else:
            lines += ["", "No prior decisions for this market."]

        return "\n".join(lines)

    def _build_decision_instruction(self) -> str:
        return (
            "=== DECISION ===\n"
            "Based on the production agent context and market data above, make a trading decision.\n\n"
            "Respond ONLY with a JSON object:\n"
            '{"decision": "buy_yes"|"buy_no"|"skip", '
            '"estimated_prob": 0.0-1.0, '
            '"confidence": 0.0-1.0, '
            '"reasoning": "brief explanation"}'
        )

"""LLMSynthesisTreatment — uses the LLM itself to estimate probability from raw market data.

Non-deterministic treatment: formats a V2-style prompt for the V3 harness LLM.
The harness sends the prompt to its LLM client; no internal LLM call is made.
"""

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface

_PROMPT_TEMPLATE = """\
You are a weather market analyst. Estimate the probability that the following prediction market resolves YES.

Market: {question}
Forecast (timestep {timestep}/10, {forecast_date}):
- High temp: {temp_max_f}°F
- Low temp: {temp_min_f}°F
- Humidity: {humidity_max_pct}%
- Wind: {wind_speed_max_kmh} km/h
- Precipitation: {precip_mm}mm
- Weather code: {weather_code}

Threshold: {strike_value}°F ({direction})
Current market: YES={yes_price}, NO={no_price}
{prior_decisions_summary}

Respond ONLY with a JSON object:
{{"estimated_prob": float, "confidence": float, "reasoning": string}}"""


class LLMSynthesisTreatment(TreatmentInterface):
    """Formats V2-style synthesis prompt for the V3 harness LLM.

    Non-deterministic — the harness sends the prompt through its LLM client.
    Uses V2's rich prompt template with humidity, wind, precipitation, and
    weather code data alongside temperature and market prices.
    """

    @property
    def name(self) -> str:
        return "llm_synthesis"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        direction = self._get_direction(ctx.market.strike_type)
        question = self._build_question(ctx.market)
        prior = self._format_prior(ctx.prior.decisions)

        prompt = _PROMPT_TEMPLATE.format(
            question=question,
            timestep=ctx.timestep + 1,
            forecast_date=ctx.market.resolution_date,
            temp_max_f=ctx.forecast.forecast_temp_f or "N/A",
            temp_min_f=getattr(ctx.forecast, "forecast_min_temp_f", None) or "N/A",
            humidity_max_pct=getattr(ctx.forecast, "humidity_max_pct", None) or "N/A",
            wind_speed_max_kmh=getattr(ctx.forecast, "wind_speed_max_kmh", None) or "N/A",
            precip_mm=getattr(ctx.forecast, "precip_mm", None) or "N/A",
            weather_code=getattr(ctx.forecast, "weather_code", None) or "N/A",
            strike_value=ctx.market.threshold,
            direction=direction,
            yes_price=ctx.prices.yes_price,
            no_price=ctx.prices.no_price,
            prior_decisions_summary=prior,
        )

        if ctx.system_context:
            prompt = (
                "=== PRODUCTION AGENT SYSTEM CONTEXT ===\n"
                "The following defines the production trading agent's decision framework.\n\n"
                f"{ctx.system_context}\n\n"
                "=== END SYSTEM CONTEXT ===\n\n"
                + prompt
            )

        return prompt

    def validate_response(self, response: dict) -> bool:
        decision = response.get("decision")
        if decision not in ("buy_yes", "buy_no", "skip"):
            return False

        prob = response.get("estimated_prob")
        if not isinstance(prob, (int, float)) or prob < 0 or prob > 1:
            return False

        confidence = response.get("confidence")
        return isinstance(confidence, (int, float))

    def _get_direction(self, strike_type: str) -> str:
        return strike_type

    def _build_question(self, m) -> str:
        if m.strike_type == "greater":
            return f"Will the high temperature in {m.city} on {m.resolution_date} be above {m.threshold}°F?"
        elif m.strike_type == "less":
            return f"Will the high temperature in {m.city} on {m.resolution_date} be below {m.threshold}°F?"
        else:
            between_high = int(m.ceiling_strike) if m.ceiling_strike else int(m.threshold) + 1
            return f"Will the high temperature in {m.city} on {m.resolution_date} be between {int(m.threshold)}°F and {between_high}°F?"

    def _format_prior(self, decisions: list) -> str:
        if not decisions:
            return "No prior decisions for this market."
        lines = ["Prior decisions:"]
        for d in decisions:
            ts = d.get("timestep", "?")
            dec = d.get("decision", "?")
            prob = d.get("estimated_prob", 0.0)
            lines.append(f"- timestep {ts}: {dec} (prob={float(prob):.2f})")
        return "\n".join(lines)

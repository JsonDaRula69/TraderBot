"""Adapter that brings V2 LLM Synthesis methodology prompt into V3 framework.

format_prompt returns the V2 prompt text.  The harness sends it to the LLM.
validate_response uses V2 JSON-parsing logic.
"""

from __future__ import annotations

import json
import re

import experiments.v3.treatment_interface as interface

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


class V2LlmSynthesisTreatment(interface.TreatmentInterface):

    name: str = "v2_llm_synthesis"

    def format_prompt(self, ctx: interface.TreatmentContext) -> str:
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

    def validate_response(self, response_str: str | dict) -> bool:
        try:
            if isinstance(response_str, dict):
                data = response_str
            else:
                text = _strip_code_fences(response_str.strip())
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    text = text[start:end + 1]
                data = json.loads(text)

            prob = float(data["estimated_prob"])
            conf = float(data["confidence"])

            if not (0.0 <= prob <= 1.0):
                return False
            if not (0.0 <= conf <= 1.0):
                return False

            return True
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return False

    def _get_direction(self, strike_type: str) -> str:
        return strike_type

    def _build_question(self, m: interface.MarketData) -> str:
        if m.strike_type == "greater":
            return f"Will the high temperature in {m.city} on {m.resolution_date} be above {m.threshold}°F?"
        elif m.strike_type == "less":
            return f"Will the high temperature in {m.city} on {m.resolution_date} be below {m.threshold}°F?"
        else:
            return f"Will the high temperature in {m.city} on {m.resolution_date} be between {int(m.threshold)}°F and {int(m.threshold)+1}°F?"

    def _format_prior(self, decisions: list) -> str:
        if not decisions:
            return "No prior decisions for this market."
        lines = ["Prior decisions:"]
        for d in decisions:
            ts = d.get("timestep", d.timestep if hasattr(d, "timestep") else "?")
            dec = d.get("decision", d.decision if hasattr(d, "decision") else "?")
            prob = d.get("estimated_prob", d.estimated_prob if hasattr(d, "estimated_prob") else 0.0)
            lines.append(f"- timestep {ts}: {dec} (prob={float(prob):.2f})")
        return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()

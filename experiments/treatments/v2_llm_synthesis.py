"""V2 LLM Synthesis treatment wrapper — delegates to V2 LLMSynthesisMethodology.

Translates V3 TreatmentContext into a V2-style forecast dict, calls the V2
LLMSynthesisMethodology.estimate(), and converts MethodologyResult to TreatmentResponse.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from experiments.v2.methodologies.llm_synthesis import LLMSynthesisMethodology

if TYPE_CHECKING:
    from experiments.v2.methodologies.base import MethodologyResult
from experiments.v3.treatment_interface import (
    TreatmentContext,
    TreatmentInterface,
    TreatmentResponse,
)

_DB_PATH = Path("experiments/v2/v2_experiment_data.db")

_EDGE_THRESHOLD = 0.05


def _context_to_forecast(ctx: TreatmentContext) -> dict:
    """Translate V3 TreatmentContext into a V2-style forecast dict."""
    return {
        "temp_max_f": ctx.forecast.forecast_temp_f,
        "temp_min_f": ctx.forecast.forecast_temp_f - 15,
        "humidity_max_pct": 50,
        "wind_speed_max_kmh": 10,
        "precip_mm": 0,
        "weather_code": 0,
        "forecast_date": ctx.market.resolution_date,
        "source": ctx.forecast.source,
        "days_before": ctx.forecast.days_before,
        "timestep": ctx.forecast.timestep,
    }


def _context_to_prior_decisions(ctx: TreatmentContext) -> list:
    """Convert V3 PriorDecisions to V2-style list of dicts."""
    return [
        {"timestep": d.get("timestep", 0), "decision": d.get("decision", ""), "estimated_prob": d.get("estimated_prob", 0.5)}
        if isinstance(d, dict) else {"raw": str(d)}
        for d in ctx.prior.decisions
    ]


def _result_to_response(
    result: MethodologyResult,
    yes_price: float,
) -> TreatmentResponse:
    """Convert MethodologyResult to TreatmentResponse with decision logic."""
    if result.estimated_prob > yes_price + _EDGE_THRESHOLD:
        decision = "buy_yes"
    elif result.estimated_prob < yes_price - _EDGE_THRESHOLD:
        decision = "buy_no"
    else:
        decision = "skip"

    reasoning = "; ".join(f"{k}={v}" for k, v in result.reasoning.items())

    return TreatmentResponse(
        decision=decision,
        estimated_prob=result.estimated_prob,
        confidence=result.confidence,
        reasoning=f"[llm_synthesis] {reasoning}",
    )


class V2LlmSynthesisTreatment(TreatmentInterface):
    """Wraps V2 LLMSynthesisMethodology as a V3 TreatmentInterface plug-in."""

    _methodology: LLMSynthesisMethodology

    def __init__(self, db_path: Path = _DB_PATH, ollama_url: str = "http://localhost:11434") -> None:
        self._methodology = LLMSynthesisMethodology(db_path, ollama_url)

    @property
    def name(self) -> str:
        return "v2_llm_synthesis"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        forecast = _context_to_forecast(ctx)
        prior = _context_to_prior_decisions(ctx)
        result = self._methodology.estimate(
            ticker=ctx.market.ticker,
            forecast=forecast,
            timestep=ctx.timestep,
            prior_decisions=prior,
        )
        return (
            f"LLM Synthesis estimate for {ctx.market.ticker}:\n"
            f"  estimated_prob={result.estimated_prob:.4f}\n"
            f"  confidence={result.confidence:.4f}\n"
            f"  reasoning: {result.reasoning}\n"
            f"  market yes_price={ctx.prices.yes_price:.2f}\n"
            f"  decision threshold: edge > {_EDGE_THRESHOLD}"
        )

    def validate_response(self, response: str | dict) -> bool:
        """Always valid — the V2 methodology handles LLM parsing internally."""
        return True

    def run(self, ctx: TreatmentContext) -> TreatmentResponse:
        """Execute V2 LLMSynthesisMethodology.estimate and return TreatmentResponse."""
        forecast = _context_to_forecast(ctx)
        prior = _context_to_prior_decisions(ctx)
        result = self._methodology.estimate(
            ticker=ctx.market.ticker,
            forecast=forecast,
            timestep=ctx.timestep,
            prior_decisions=prior,
        )
        return _result_to_response(result, ctx.prices.yes_price)
"""EnsembleTreatment — combines bin_cal, logistic_reg, and llm_synthesis via weighted average.

Non-deterministic treatment: formats prompts for the V3 harness LLM.
bin_cal and logistic_reg sub-methodologies can use V2 deterministic computation
when a V2 DB path is provided; otherwise they fall back to heuristic estimates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from experiments.v3.treatment_interface import TreatmentContext, TreatmentInterface

from .bin_cal import BinCalTreatment, estimate_bin_probability
from .bin_cal import compute_delta as bin_cal_delta
from .logistic_reg import LogisticRegTreatment, simple_logistic_probability
from .logistic_reg import compute_delta as logistic_delta

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_WEIGHTS = {
    "bin_cal": 0.3,
    "logistic_reg": 0.3,
    "llm_synthesis": 0.4,
}

_FALLBACK_PROB = 0.5
_FALLBACK_CONFIDENCE = 0.1


class EnsembleTreatment(TreatmentInterface):
    """Combines bin_cal + logistic_reg + llm_synthesis via weighted average.

    Instantiates the other 3 treatments internally, calls each to compute
    their probability estimates, and presents a weighted average to the LLM.
    Individual sub-treatment failures are caught and replaced with fallback
    values (0.5 prob, 0.1 confidence).
    """

    _weights: dict[str, float]
    _bin_cal: BinCalTreatment
    _logistic_reg: LogisticRegTreatment
    _llm_synthesis: _LLMSynthesisOnly
    _v2_db_path: str | Path | None

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        bin_cal_data: dict | None = None,
        logistic_weights: dict[str, float] | None = None,
        logistic_intercept: float = 0.0,
        v2_db_path: str | Path | None = None,
    ) -> None:
        self._weights = weights if weights is not None else _DEFAULT_WEIGHTS.copy()
        self._bin_cal = BinCalTreatment(calibration_data=bin_cal_data, v2_db_path=v2_db_path)
        self._logistic_reg = LogisticRegTreatment(weights=logistic_weights, intercept=logistic_intercept, v2_db_path=v2_db_path)
        self._llm_synthesis = _LLMSynthesisOnly()
        self._v2_db_path = v2_db_path

    @property
    def name(self) -> str:
        return "ensemble"

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

        estimates = self._compute_estimates(ctx)

        sections.append(self._build_market_section(ctx))
        sections.append(self._build_ensemble_section(ctx, estimates))
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

    def _compute_estimates(self, ctx: TreatmentContext) -> dict:
        """Run all sub-methodologies and collect estimates."""
        results = {}

        try:
            delta = bin_cal_delta(ctx)
            prob, conf, reasoning = estimate_bin_probability(
                delta, self._bin_cal._calibration_data
            )
            results["bin_cal"] = {
                "estimated_prob": prob,
                "confidence": conf,
                "reasoning": reasoning,
                "failed": False,
            }
        except Exception:
            results["bin_cal"] = {
                "estimated_prob": _FALLBACK_PROB,
                "confidence": _FALLBACK_CONFIDENCE,
                "reasoning": {"error": "bin_cal_estimate_failed"},
                "failed": True,
            }

        try:
            delta = logistic_delta(ctx)
            prob, features = simple_logistic_probability(
                delta, ctx.timestep, self._logistic_reg._weights, self._logistic_reg._intercept
            )
            clamped_prob = max(0.01, min(0.99, prob))
            conf = max(0.1, abs(prob - 0.5) * 2)
            results["logistic_reg"] = {
                "estimated_prob": clamped_prob,
                "confidence": conf,
                "reasoning": features,
                "failed": False,
            }
        except Exception:
            results["logistic_reg"] = {
                "estimated_prob": _FALLBACK_PROB,
                "confidence": _FALLBACK_CONFIDENCE,
                "reasoning": {"error": "logistic_reg_estimate_failed"},
                "failed": True,
            }

        # llm_synthesis — no pre-computed estimate; use implied probability as baseline
        results["llm_synthesis"] = {
            "estimated_prob": ctx.prices.implied_prob,
            "confidence": _FALLBACK_CONFIDENCE,
            "reasoning": {"note": "llm_synthesis provides estimate via LLM reasoning, not pre-computation"},
            "failed": False,
        }

        weighted_prob = sum(
            self._weights[name] * results[name]["estimated_prob"]
            for name in results
        )
        weighted_confidence = sum(
            self._weights[name] * results[name]["confidence"]
            for name in results
        )

        results["ensemble"] = {
            "estimated_prob": round(weighted_prob, 4),
            "confidence": round(weighted_confidence, 4),
            "weights": dict(self._weights),
        }

        return results

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

    def _build_ensemble_section(self, ctx: TreatmentContext, estimates: dict) -> str:
        lines = [
            "=== ENSEMBLE METHODOLOGY ===",
            f"Weights: bin_cal={self._weights['bin_cal']:.1f}, "
            f"logistic_reg={self._weights['logistic_reg']:.1f}, "
            f"llm_synthesis={self._weights['llm_synthesis']:.1f}",
            "",
            "Individual estimates:",
        ]

        for name in ("bin_cal", "logistic_reg", "llm_synthesis"):
            est = estimates[name]
            status = "⚠ FAILED (using fallback)" if est.get("failed") else "✓"
            lines.append(
                f"  {name}: prob={est['estimated_prob']:.4f}, "
                f"confidence={est['confidence']:.2f} [{status}]"
            )

        lines.extend([
            "",
            f"Ensemble weighted probability: {estimates['ensemble']['estimated_prob']:.4f}",
            f"Ensemble weighted confidence: {estimates['ensemble']['confidence']:.4f}",
        ])

        if ctx.accuracy.low_confidence:
            lines.append("Note: Low accuracy confidence — ensemble estimate should be weighted cautiously.")

        lines.append("")
        lines.append(
            "Use the ensemble estimate as your primary probability estimate, "
            "but also consider the individual methodology estimates and market data."
        )

        return "\n".join(lines)

    def _build_decision_instruction(self) -> str:
        return (
            "=== DECISION ===\n"
            "Based on the market data, individual methodology estimates, and ensemble "
            "weighted estimate above, make a trading decision.\n\n"
            'Respond ONLY with a JSON object: {"decision": "buy_yes"|"buy_no"|"skip", '
            '"estimated_prob": float, "confidence": float, "reasoning": string}'
        )


class _LLMSynthesisOnly:
    """Internal helper — placeholder for the LLM synthesis sub-component.

    The llm_synthesis sub-methodology doesn't pre-compute a probability;
    it provides its estimate via LLM reasoning. In the ensemble context,
    we use the market's implied probability as its baseline since the
    actual LLM call hasn't happened yet.
    """

    @property
    def name(self) -> str:
        return "llm_synthesis_internal"

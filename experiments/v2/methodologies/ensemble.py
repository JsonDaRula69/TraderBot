"""Ensemble methodology — combines bin_cal, logistic_reg, and llm_synthesis via weighted average."""

from __future__ import annotations

from pathlib import Path

from .base import MethodologyInterface, MethodologyResult
from .bin_cal import BinCalMethodology
from .logistic_reg import LogisticRegMethodology
from .llm_synthesis import LLMSynthesisMethodology

_DEFAULT_WEIGHTS = {
    "bin_cal": 0.3,
    "logistic_reg": 0.3,
    "llm_synthesis": 0.4,
}


class EnsembleMethodology(MethodologyInterface):
    """Combine multiple methodologies via weighted average.

    Runs all 3 sub-methodologies and computes a weighted average of their
    probability estimates and confidence scores.  Individual failures are
    caught, recorded in the combined reasoning, and replaced with fallback
    values so that the ensemble never crashes.
    """

    def __init__(
        self,
        db_path: Path,
        weights: dict | None = None,
        ollama_url: str = "http://localhost:11434",
    ):
        """
        Args:
            db_path: Path to the SQLite database.
            weights: Optional dictionary of weights for each sub-methodology.
                     Defaults to bin_cal=0.3, logistic_reg=0.3, llm_synthesis=0.4.
            ollama_url: URL for the Ollama API used by LLMSynthesisMethodology.
        """
        super().__init__(db_path)
        self.weights = weights if weights is not None else _DEFAULT_WEIGHTS.copy()
        self._bin_cal = BinCalMethodology(db_path)
        self._logistic_reg = LogisticRegMethodology(db_path)
        self._llm = LLMSynthesisMethodology(db_path, ollama_url)

    def estimate(
        self,
        ticker: str,
        forecast: dict,
        timestep: int,
        prior_decisions: list,
    ) -> MethodologyResult:
        """Compute ensemble estimate by calling all sub-methodologies.

        Args:
            ticker: The market ticker string.
            forecast: The forecast data dictionary.
            timestep: The current timestep.
            prior_decisions: List of prior decisions.

        Returns:
            A MethodologyResult containing the weighted average probability,
            weighted average confidence, and combined reasoning from all
            sub-methodologies.
        """
        sub_results = {}
        failures = set()

        for name, method in [
            ("bin_cal", self._bin_cal),
            ("logistic_reg", self._logistic_reg),
            ("llm_synthesis", self._llm),
        ]:
            try:
                sub_results[name] = method.estimate(
                    ticker, forecast, timestep, prior_decisions
                )
            except Exception as exc:
                failures.add(name)
                sub_results[name] = MethodologyResult(
                    estimated_prob=0.5,
                    confidence=0.1,
                    reasoning={"error": str(exc)},
                )

        # If every sub-methodology failed, return the special fallback.
        if len(failures) == 3:
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={"reasoning": "all_failed"},
            )

        # Weighted average of probabilities and confidence scores.
        weighted_prob = sum(
            self.weights[name] * sub_results[name].estimated_prob
            for name in sub_results
        )
        weighted_confidence = sum(
            self.weights[name] * sub_results[name].confidence
            for name in sub_results
        )

        # Merge reasoning dicts keyed by methodology name.
        combined_reasoning = {
            name: sub_results[name].reasoning for name in sub_results
        }

        return MethodologyResult(
            estimated_prob=weighted_prob,
            confidence=weighted_confidence,
            reasoning=combined_reasoning,
        )

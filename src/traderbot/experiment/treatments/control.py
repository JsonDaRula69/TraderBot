"""Control treatment: bypasses LLM and uses production decision logic."""

import logging

from traderbot.experiment.shared import TreatmentContext, TreatmentInterface, ValidatedDecision

logger = logging.getLogger(__name__)


class ControlTreatment(TreatmentInterface):
    _decision_count: int = 0

    @property
    def name(self) -> str:
        return "control"

    @property
    def bypass_llm(self) -> bool:
        return True

    def format_prompt(self, ctx: TreatmentContext) -> str:
        # Control bypasses LLM — prompt is never used
        return ""

    def validate_response(self, response: dict) -> ValidatedDecision:
        # The harness handles control decisions directly via _control_decision()
        # This method is only called if someone mistakenly calls it
        self._decision_count += 1
        return ValidatedDecision(
            decision="skip",
            estimated_prob=0.5,
            confidence=0.0,
            reasoning="Control treatment: bypass_llm=True",
        )

    def report(self) -> None:
        logger.info("Control treatment executed: %d decisions generated", self._decision_count)

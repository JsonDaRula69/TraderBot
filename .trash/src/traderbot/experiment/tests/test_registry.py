"""Tests for traderbot.experiment.registry."""


from traderbot.experiment.registry import (
    _registry,
    discover_treatments,
    get_treatment,
    list_treatments,
    register_treatment,
)
from traderbot.experiment.shared import TreatmentContext, TreatmentInterface, ValidatedDecision


class _FakeTreatment(TreatmentInterface):
    @property
    def name(self) -> str:
        return "fake"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        return ""

    def validate_response(self, response: dict) -> ValidatedDecision:
        return ValidatedDecision(decision="skip", estimated_prob=0.5, confidence=0.5, reasoning="")


def test_discover_returns_dict() -> None:
    """discover_treatments should return a dict (empty when no treatments registered)."""
    result = discover_treatments()
    assert isinstance(result, dict)


def test_register_and_get() -> None:
    """register_treatment then get_treatment should return the class."""
    _registry.clear()
    register_treatment("fake", _FakeTreatment)
    cls = get_treatment("fake")
    assert cls is _FakeTreatment
    _registry.clear()


def test_get_nonexistent_returns_none() -> None:
    """get_treatment for unregistered name should return None."""
    _registry.clear()
    assert get_treatment("does_not_exist") is None


def test_list_returns_sorted_keys() -> None:
    """list_treatments should return sorted treatment names."""
    _registry.clear()
    register_treatment("beta", _FakeTreatment)
    register_treatment("alpha", _FakeTreatment)
    register_treatment("gamma", _FakeTreatment)
    assert list_treatments() == ["alpha", "beta", "gamma"]
    _registry.clear()

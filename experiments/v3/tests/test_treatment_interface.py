"""Tests for treatment_interface — the ABC and dataclasses defining the treatment plug-in contract."""

import pytest
from experiments.v3.treatment_interface import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
    TreatmentInterface,
    TreatmentResponse,
)

# ---------------------------------------------------------------------------
# TreatmentInterface ABC
# ---------------------------------------------------------------------------


class TestTreatmentInterfaceABC:
    """Cannot instantiate the ABC directly; can instantiate a concrete subclass."""

    def test_cannot_instantiate_interface_directly(self):
        with pytest.raises(TypeError):
            TreatmentInterface()

    def test_concrete_subclass_instantiates(self):
        class MockTreatment(TreatmentInterface):
            @property
            def name(self) -> str:
                return "mock"

            def format_prompt(self, ctx: TreatmentContext) -> str:
                return f"prompt for {ctx.market.ticker}"

            def validate_response(self, response: dict) -> bool:
                return response.get("decision") in ("buy_yes", "buy_no", "skip")

        t = MockTreatment()
        assert t.name == "mock"

    def test_concrete_subclass_format_prompt(self):
        class MockTreatment(TreatmentInterface):
            @property
            def name(self) -> str:
                return "mock"

            def format_prompt(self, ctx: TreatmentContext) -> str:
                return f"Market: {ctx.market.ticker}"

            def validate_response(self, response: dict) -> bool:
                return "decision" in response

        ctx = _make_context()
        t = MockTreatment()
        prompt = t.format_prompt(ctx)
        assert "KXNYHI" in prompt

    def test_concrete_subclass_validate_response(self):
        class MockTreatment(TreatmentInterface):
            @property
            def name(self) -> str:
                return "mock"

            def format_prompt(self, ctx: TreatmentContext) -> str:
                return ""

            def validate_response(self, response: dict) -> bool:
                return response.get("decision") in ("buy_yes", "buy_no", "skip")

        t = MockTreatment()
        assert t.validate_response({"decision": "buy_yes"}) is True
        assert t.validate_response({"decision": "invalid"}) is False


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestMarketData:
    def test_required_fields(self):
        m = MarketData(
            ticker="KXNYHI",
            city="New York",
            strike_type="high",
            threshold=90.0,
            resolution_date="2025-07-01",
        )
        assert m.ticker == "KXNYHI"
        assert m.threshold == 90.0

    def test_optional_fields_default_to_none(self):
        m = MarketData(
            ticker="KXNYHI",
            city="New York",
            strike_type="high",
            threshold=90.0,
            resolution_date="2025-07-01",
        )
        assert m.floor_strike is None
        assert m.ceiling_strike is None
        assert m.settlement_result is None

    def test_optional_fields_can_be_set(self):
        m = MarketData(
            ticker="KXNYHI",
            city="New York",
            strike_type="range",
            threshold=90.0,
            floor_strike=85.0,
            ceiling_strike=95.0,
            resolution_date="2025-07-01",
            settlement_result="below",
        )
        assert m.floor_strike == 85.0
        assert m.ceiling_strike == 95.0
        assert m.settlement_result == "below"

    def test_frozen(self):
        m = MarketData(
            ticker="KXNYHI",
            city="New York",
            strike_type="high",
            threshold=90.0,
            resolution_date="2025-07-01",
        )
        with pytest.raises(AttributeError):
            m.ticker = "other"


class TestForecastData:
    def test_creation(self):
        f = ForecastData(forecast_temp_f=88.5, source="NWS", days_before=3, timestep=1)
        assert f.forecast_temp_f == 88.5
        assert f.source == "NWS"
        assert f.days_before == 3
        assert f.timestep == 1

    def test_frozen(self):
        f = ForecastData(forecast_temp_f=88.5, source="NWS", days_before=3, timestep=1)
        with pytest.raises(AttributeError):
            f.forecast_temp_f = 99.0


class TestAccuracyData:
    def test_required_fields(self):
        a = AccuracyData(city="New York", lead_time=3, mae=2.5, bias=0.3, sample_count=100)
        assert a.city == "New York"
        assert a.mae == 2.5
        assert a.low_confidence is False

    def test_low_confidence_explicit(self):
        a = AccuracyData(city="New York", lead_time=3, mae=5.0, bias=1.0, sample_count=10, low_confidence=True)
        assert a.low_confidence is True


class TestPriceData:
    def test_creation(self):
        p = PriceData(yes_price=0.65, no_price=0.35, trade_count=120, open_interest=500, implied_prob=0.65)
        assert p.yes_price == 0.65
        assert p.no_price == 0.35


class TestTechnicalData:
    def test_creation(self):
        t = TechnicalData(
            rsi=55.0, bollinger_position=0.6, ema5=90.1, ema20=88.5,
            signal_direction="bullish", signal_confidence=0.7,
        )
        assert t.signal_direction == "bullish"
        assert t.rsi == 55.0


class TestPriorDecisions:
    def test_wraps_list_of_dicts(self):
        d = PriorDecisions(decisions=[
            {"treatment": "control", "timestep": 0, "decision": "skip", "estimated_prob": 0.5, "confidence": 0.3},
            {"treatment": "momentum", "timestep": 1, "decision": "buy_yes", "estimated_prob": 0.6, "confidence": 0.8},
        ])
        assert len(d.decisions) == 2
        assert d.decisions[0]["treatment"] == "control"
        assert d.decisions[1]["decision"] == "buy_yes"

    def test_empty_decisions(self):
        d = PriorDecisions(decisions=[])
        assert d.decisions == []


# ---------------------------------------------------------------------------
# TreatmentContext
# ---------------------------------------------------------------------------


class TestTreatmentContext:
    def test_holds_all_sub_dataclasses(self):
        ctx = _make_context()
        assert isinstance(ctx.market, MarketData)
        assert isinstance(ctx.forecast, ForecastData)
        assert isinstance(ctx.accuracy, AccuracyData)
        assert isinstance(ctx.prices, PriceData)
        assert isinstance(ctx.technicals, TechnicalData)
        assert isinstance(ctx.prior, PriorDecisions)
        assert ctx.timestep == 1
        assert ctx.remaining == 9

    def test_frozen(self):
        ctx = _make_context()
        with pytest.raises(AttributeError):
            ctx.timestep = 99


# ---------------------------------------------------------------------------
# TreatmentResponse
# ---------------------------------------------------------------------------


class TestTreatmentResponse:
    def test_valid_decisions(self):
        for decision in ("buy_yes", "buy_no", "skip"):
            r = TreatmentResponse(decision=decision, estimated_prob=0.6, confidence=0.8, reasoning="test")
            assert r.decision == decision

    def test_frozen(self):
        r = TreatmentResponse(decision="skip", estimated_prob=0.5, confidence=0.3, reasoning="n/a")
        with pytest.raises(AttributeError):
            r.decision = "buy_yes"

    def test_fields(self):
        r = TreatmentResponse(decision="buy_yes", estimated_prob=0.65, confidence=0.9, reasoning="strong signal")
        assert r.estimated_prob == 0.65
        assert r.confidence == 0.9
        assert r.reasoning == "strong signal"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context() -> TreatmentContext:
    """Build a minimal TreatmentContext for tests."""
    return TreatmentContext(
        market=MarketData(
            ticker="KXNYHI",
            city="New York",
            strike_type="high",
            threshold=90.0,
            resolution_date="2025-07-01",
        ),
        forecast=ForecastData(forecast_temp_f=88.5, source="NWS", days_before=3, timestep=1),
        accuracy=AccuracyData(city="New York", lead_time=3, mae=2.5, bias=0.3, sample_count=100),
        prices=PriceData(yes_price=0.65, no_price=0.35, trade_count=120, open_interest=500, implied_prob=0.65),
        technicals=TechnicalData(
            rsi=55.0, bollinger_position=0.6, ema5=90.1, ema20=88.5,
            signal_direction="bullish", signal_confidence=0.7,
        ),
        prior=PriorDecisions(decisions=[
            {"treatment": "control", "timestep": 0, "decision": "skip", "estimated_prob": 0.5, "confidence": 0.3},
        ]),
        timestep=1,
        remaining=9,
    )

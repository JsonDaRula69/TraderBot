from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from traderbot.kalshi._normalize import _normalize_trade as normalize_trade_raw
from traderbot.kalshi.models import (
    CutoffTimestamps,
    Decision,
    Fill,
    Market,
    MarketListResponse,
    Order,
    OrderBook,
    OrderBookLevel,
    PortfolioState,
    Position,
    RiskCheckResult,
    Trade,
    TradeListResponse,
    TradeRequest,
)


def _ts(year: int = 2026, month: int = 3, day: int = 31) -> datetime:
    return datetime(year, month, day, 23, 59, 59, tzinfo=UTC)


def _normalize_market(raw: dict) -> dict:
    d = copy.deepcopy(raw)
    if isinstance(d.get("close_time"), str):
        d["close_time"] = datetime.fromisoformat(d["close_time"].replace("Z", "+00:00"))
    return d


def _normalize_trade(raw: dict) -> dict:
    d = copy.deepcopy(raw)
    if isinstance(d.get("timestamp"), int):
        d["timestamp"] = datetime.fromtimestamp(d["timestamp"], tz=UTC)
    return d


class TestOrderBookLevel:
    def test_valid(self) -> None:
        level = OrderBookLevel(price=64, size=100)
        assert level.price == 64
        assert level.size == 100

    def test_zero_price(self) -> None:
        OrderBookLevel(price=0, size=50)

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OrderBookLevel(price=-1, size=50)

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OrderBookLevel(price=10, size=-1)

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            OrderBookLevel(price=10, size=5, extra=1)

    def test_roundtrip(self) -> None:
        level = OrderBookLevel(price=64, size=100)
        data = level.model_dump()
        assert OrderBookLevel(**data) == level

    def test_json_roundtrip(self) -> None:
        level = OrderBookLevel(price=64, size=100)
        raw = level.model_dump_json()
        assert OrderBookLevel.model_validate_json(raw) == level


class TestMarket:
    def test_valid(self, sample_market_data: dict) -> None:
        m = Market(**_normalize_market(sample_market_data))
        assert m.ticker == "KXBTCD-26MAR31-T55000"
        assert m.status == "open"
        assert m.category == "crypto"

    def test_optional_fields_none(self) -> None:
        m = Market(
            ticker="KX-TEST",
            question="Test?",
            outcome_prices=["0.50", "0.50"],
            volume=0,
            open_interest=0,
            close_time=_ts(),
            status="open",
            event_ticker="KX-EVENT",
        )
        assert m.category is None
        assert m.settlement_result is None

    def test_pending_status_normalized_to_open(self) -> None:
        m = Market(
            ticker="KX-TEST",
            question="Q?",
            outcome_prices=["0.50"],
            volume=1,
            open_interest=1,
            close_time=_ts(),
            status="pending",
            event_ticker="KX-E",
        )
        assert m.status == "open"

    def test_extra_field_forbidden(self, sample_market_data: dict) -> None:
        data = {**_normalize_market(sample_market_data), "surprise": True}
        with pytest.raises(ValidationError):
            Market(**data)

    def test_serialization_roundtrip(self, sample_market_data: dict) -> None:
        m = Market(**_normalize_market(sample_market_data))
        data = m.model_dump()
        assert Market(**data) == m

    def test_json_roundtrip(self, sample_market_data: dict) -> None:
        m = Market(**_normalize_market(sample_market_data))
        raw = m.model_dump_json()
        restored = Market.model_validate_json(raw)
        assert restored == m

    def test_settled_market(self) -> None:
        m = Market(
            ticker="KX-SETTLED",
            question="Done?",
            outcome_prices=["1.00", "0.00"],
            volume=100,
            open_interest=50,
            close_time=_ts(),
            status="settled",
            event_ticker="KX-E",
            settlement_result=True,
        )
        assert m.settlement_result is True

    def test_negative_volume_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Market(
                ticker="KX-TEST",
                question="Q?",
                outcome_prices=["0.50"],
                volume=-1,
                open_interest=0,
                close_time=_ts(),
                status="open",
                event_ticker="KX-E",
            )

    def test_closed_state(self) -> None:
        m = Market(
            ticker="KX-CLOSED",
            question="Over?",
            outcome_prices=["0.90", "0.10"],
            volume=500,
            open_interest=200,
            close_time=_ts(),
            status="closed",
            event_ticker="KX-E",
        )
        assert m.status == "closed"


class TestOrderBook:
    def test_valid(self, sample_orderbook_data: dict) -> None:
        ob = OrderBook(
            yes_bids=[OrderBookLevel(**lvl) for lvl in sample_orderbook_data["yes"]],
            no_bids=[OrderBookLevel(**lvl) for lvl in sample_orderbook_data["no"]],
        )
        assert len(ob.yes_bids) == 3
        assert len(ob.no_bids) == 3

    def test_empty_lists(self) -> None:
        ob = OrderBook(yes_bids=[], no_bids=[])
        assert ob.yes_bids == []

    def test_roundtrip(self, sample_orderbook_data: dict) -> None:
        ob = OrderBook(
            yes_bids=[OrderBookLevel(**lvl) for lvl in sample_orderbook_data["yes"]],
            no_bids=[OrderBookLevel(**lvl) for lvl in sample_orderbook_data["no"]],
        )
        data = ob.model_dump()
        assert OrderBook(**data) == ob

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            OrderBook(yes_bids=[], no_bids=[], extra=True)


class TestTrade:
    def test_valid(self, sample_trade_data: dict) -> None:
        t = Trade(**_normalize_trade(sample_trade_data))
        assert t.ticker == "KXBTCD-26MAR31-T55000"
        assert t.price == 65
        assert t.side == "yes"

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Trade(
                ticker="KX-TEST",
                price=50,
                quantity=10,
                side="maybe",
                timestamp=_ts(),
            )

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Trade(
                ticker="KX-TEST",
                price=-5,
                quantity=10,
                side="yes",
                timestamp=_ts(),
            )

    def test_zero_price_accepted(self) -> None:
        Trade(ticker="KX-TEST", price=0, quantity=10, side="no", timestamp=_ts())

    def test_roundtrip(self, sample_trade_data: dict) -> None:
        t = Trade(**_normalize_trade(sample_trade_data))
        data = t.model_dump()
        assert Trade(**data) == t

    def test_json_roundtrip(self, sample_trade_data: dict) -> None:
        t = Trade(**_normalize_trade(sample_trade_data))
        raw = t.model_dump_json()
        restored = Trade.model_validate_json(raw)
        assert restored == t


class TestOrder:
    def test_valid(self) -> None:
        o = Order(
            id="ord-1",
            ticker="KX-TEST",
            side="yes",
            price=55,
            quantity=10,
            status="resting",
            created_time=_ts(),
        )
        assert o.status == "resting"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Order(
                id="ord-1",
                ticker="KX-TEST",
                side="yes",
                price=55,
                quantity=10,
                status="pending",
                created_time=_ts(),
            )

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Order(
                id="ord-1",
                ticker="KX-TEST",
                side="both",
                price=55,
                quantity=10,
                status="resting",
                created_time=_ts(),
            )

    def test_roundtrip(self) -> None:
        o = Order(
            id="ord-1",
            ticker="KX-TEST",
            side="yes",
            price=55,
            quantity=10,
            status="filled",
            created_time=_ts(),
        )
        data = o.model_dump()
        assert Order(**data) == o

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Order(
                id="ord-1",
                ticker="KX-TEST",
                side="yes",
                price=-1,
                quantity=10,
                status="resting",
                created_time=_ts(),
            )

    def test_cancelled_status(self) -> None:
        o = Order(
            id="ord-2",
            ticker="KX-TEST",
            side="no",
            price=40,
            quantity=5,
            status="cancelled",
            created_time=_ts(),
        )
        assert o.status == "cancelled"


class TestPosition:
    def test_valid(self) -> None:
        p = Position(ticker="KX-TEST", quantity=10, avg_price=55)
        assert p.avg_price == 55
        assert p.settlement_result is None

    def test_with_settlement(self) -> None:
        p = Position(ticker="KX-TEST", quantity=10, avg_price=55, settlement_result=True)
        assert p.settlement_result is True

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Position(ticker="KX-TEST", quantity=-1, avg_price=55)

    def test_negative_avg_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Position(ticker="KX-TEST", quantity=10, avg_price=-5)

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Position(ticker="KX-TEST", quantity=10, avg_price=55, extra=True)

    def test_roundtrip(self) -> None:
        p = Position(ticker="KX-TEST", quantity=10, avg_price=55)
        data = p.model_dump()
        assert Position(**data) == p

    def test_zero_quantity(self) -> None:
        p = Position(ticker="KX-TEST", quantity=0, avg_price=0)
        assert p.quantity == 0


class TestFill:
    def test_valid(self) -> None:
        f = Fill(
            order_id="ord-1",
            ticker="KX-TEST",
            side="yes",
            price=55,
            quantity=10,
            timestamp=_ts(),
        )
        assert f.order_id == "ord-1"

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Fill(
                order_id="ord-1",
                ticker="KX-TEST",
                side="both",
                price=55,
                quantity=10,
                timestamp=_ts(),
            )

    def test_roundtrip(self) -> None:
        f = Fill(
            order_id="ord-1",
            ticker="KX-TEST",
            side="no",
            price=40,
            quantity=5,
            timestamp=_ts(),
        )
        data = f.model_dump()
        assert Fill(**data) == f

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Fill(
                order_id="ord-1",
                ticker="KX-TEST",
                side="yes",
                price=-1,
                quantity=10,
                timestamp=_ts(),
            )


class TestDecision:
    def test_valid_executed(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price=55,
            signal_strength=0.8,
            confidence=0.7,
            edge_estimate=0.05,
            risk_checks={"max_position": True, "daily_loss": True},
            outcome="executed",
        )
        assert d.outcome == "executed"
        assert d.rejection_reason is None

    def test_rejected_with_reason(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="no",
            quantity=10,
            price=55,
            signal_strength=0.6,
            confidence=0.5,
            edge_estimate=0.02,
            risk_checks={"max_position": True, "daily_loss": False},
            outcome="rejected",
            rejection_reason="daily_loss_limit",
        )
        assert d.rejection_reason == "daily_loss_limit"
        assert d.risk_checks["daily_loss"] is False

    def test_neutral_direction(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="neutral",
            quantity=0,
            price=0,
            signal_strength=0.3,
            confidence=0.2,
            edge_estimate=0.01,
            risk_checks={},
            outcome="held",
        )
        assert d.direction == "neutral"

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(
                timestamp=_ts(),
                ticker="KX-TEST",
                direction="maybe",
                quantity=10,
                price=55,
                signal_strength=0.8,
                confidence=0.7,
                edge_estimate=0.05,
                risk_checks={},
                outcome="executed",
            )

    def test_invalid_outcome_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(
                timestamp=_ts(),
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price=55,
                signal_strength=0.8,
                confidence=0.7,
                edge_estimate=0.05,
                risk_checks={},
                outcome="pending",
            )

    def test_signal_strength_boundary_zero(self) -> None:
        Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="neutral",
            quantity=0,
            price=0,
            signal_strength=0.0,
            confidence=0.5,
            edge_estimate=0.0,
            risk_checks={},
            outcome="held",
        )

    def test_signal_strength_boundary_one(self) -> None:
        Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price=55,
            signal_strength=1.0,
            confidence=1.0,
            edge_estimate=0.1,
            risk_checks={},
            outcome="executed",
        )

    def test_signal_strength_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(
                timestamp=_ts(),
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price=55,
                signal_strength=1.1,
                confidence=0.7,
                edge_estimate=0.05,
                risk_checks={},
                outcome="executed",
            )

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(
                timestamp=_ts(),
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price=55,
                signal_strength=0.5,
                confidence=-0.1,
                edge_estimate=0.05,
                risk_checks={},
                outcome="executed",
            )

    def test_risk_checks_dict_str_bool(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price=55,
            signal_strength=0.8,
            confidence=0.7,
            edge_estimate=0.05,
            risk_checks={"position_limit": True, "daily_loss": False},
            outcome="rejected",
            rejection_reason="daily_loss",
        )
        assert isinstance(d.risk_checks, dict)
        for k, v in d.risk_checks.items():
            assert isinstance(k, str)
            assert isinstance(v, bool)

    def test_actual_result_mutable(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price=55,
            signal_strength=0.8,
            confidence=0.7,
            edge_estimate=0.05,
            risk_checks={},
            outcome="executed",
        )
        assert d.actual_result is None
        d.actual_result = True
        assert d.actual_result is True

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Decision(
                timestamp=_ts(),
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price=55,
                signal_strength=0.8,
                confidence=0.7,
                edge_estimate=0.05,
                risk_checks={},
                outcome="executed",
                surprise=True,
            )

    def test_roundtrip(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price=55,
            signal_strength=0.8,
            confidence=0.7,
            edge_estimate=0.05,
            risk_checks={"max_position": True},
            outcome="executed",
        )
        data = d.model_dump()
        assert Decision(**data) == d

    def test_json_roundtrip(self) -> None:
        d = Decision(
            timestamp=_ts(),
            ticker="KX-TEST",
            direction="no",
            quantity=5,
            price=40,
            signal_strength=0.6,
            confidence=0.5,
            edge_estimate=0.03,
            risk_checks={"drawdown": True},
            outcome="executed",
        )
        raw = d.model_dump_json()
        restored = Decision.model_validate_json(raw)
        assert restored == d


class TestCutoffTimestamps:
    def test_all_none(self) -> None:
        c = CutoffTimestamps()
        assert c.market_settled_ts is None
        assert c.trade_cutoff_ts is None
        assert c.order_cutoff_ts is None

    def test_all_set(self) -> None:
        c = CutoffTimestamps(
            market_settled_ts=_ts(),
            trade_cutoff_ts=_ts(),
            order_cutoff_ts=_ts(),
        )
        assert c.market_settled_ts is not None

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            CutoffTimestamps(extra=True)

    def test_roundtrip(self) -> None:
        c = CutoffTimestamps(market_settled_ts=_ts())
        data = c.model_dump()
        assert CutoffTimestamps(**data) == c


class TestMarketListResponse:
    def test_valid(self, sample_market_data: dict) -> None:
        r = MarketListResponse(
            markets=[Market(**_normalize_market(sample_market_data))], cursor="abc"
        )
        assert r.cursor == "abc"
        assert len(r.markets) == 1

    def test_empty_markets(self) -> None:
        r = MarketListResponse(markets=[])
        assert r.cursor is None

    def test_roundtrip(self, sample_market_data: dict) -> None:
        r = MarketListResponse(markets=[Market(**_normalize_market(sample_market_data))])
        data = r.model_dump()
        assert MarketListResponse(**data) == r

    def test_json_roundtrip(self, sample_market_data: dict) -> None:
        r = MarketListResponse(
            markets=[Market(**_normalize_market(sample_market_data))], cursor="xyz"
        )
        raw = r.model_dump_json()
        restored = MarketListResponse.model_validate_json(raw)
        assert restored == r

    def test_multiple_markets(self, sample_market_data: dict) -> None:
        m1 = Market(**_normalize_market(sample_market_data))
        m2 = Market(
            ticker="KX-OTHER",
            question="Other?",
            outcome_prices=["0.20", "0.80"],
            volume=500,
            open_interest=100,
            close_time=_ts(),
            status="open",
            event_ticker="KX-OTHER-E",
        )
        r = MarketListResponse(markets=[m1, m2])
        assert len(r.markets) == 2


class TestTradeListResponse:
    def test_valid(self, sample_trade_data: dict) -> None:
        r = TradeListResponse(trades=[Trade(**_normalize_trade(sample_trade_data))])
        assert len(r.trades) == 1

    def test_empty_trades(self) -> None:
        r = TradeListResponse(trades=[])
        assert r.cursor is None

    def test_roundtrip(self, sample_trade_data: dict) -> None:
        r = TradeListResponse(trades=[Trade(**_normalize_trade(sample_trade_data))], cursor="pqr")
        data = r.model_dump()
        assert TradeListResponse(**data) == r

    def test_json_roundtrip(self, sample_trade_data: dict) -> None:
        r = TradeListResponse(trades=[Trade(**_normalize_trade(sample_trade_data))], cursor="xyz")
        raw = r.model_dump_json()
        restored = TradeListResponse.model_validate_json(raw)
        assert restored == r


class TestRiskCheckResult:
    def test_pass(self) -> None:
        r = RiskCheckResult(
            passed=True,
            limit_name="max_position_per_market_pct",
            current_value=0.03,
            limit_value=0.05,
        )
        assert r.passed is True
        assert r.rejection_reason is None

    def test_fail_with_reason(self) -> None:
        r = RiskCheckResult(
            passed=False,
            limit_name="max_daily_loss_pct",
            current_value=0.025,
            limit_value=0.02,
            rejection_reason="daily_loss_exceeded",
        )
        assert r.rejection_reason == "daily_loss_exceeded"

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            RiskCheckResult(
                passed=True,
                limit_name="test",
                current_value=0.0,
                limit_value=1.0,
                extra=True,
            )

    def test_roundtrip(self) -> None:
        r = RiskCheckResult(
            passed=False,
            limit_name="daily_loss",
            current_value=0.03,
            limit_value=0.02,
            rejection_reason="exceeded",
        )
        data = r.model_dump()
        assert RiskCheckResult(**data) == r

    def test_json_roundtrip(self) -> None:
        r = RiskCheckResult(
            passed=True,
            limit_name="max_drawdown",
            current_value=0.08,
            limit_value=0.10,
        )
        raw = r.model_dump_json()
        assert RiskCheckResult(**json.loads(raw)) == r


class TestPortfolioState:
    def test_valid(self, sample_portfolio_state: dict) -> None:
        ps = PortfolioState(**sample_portfolio_state)
        assert ps.portfolio_value_cents == 100000_00
        assert ps.open_positions_count == 8

    def test_computed_field(self, sample_portfolio_state: dict) -> None:
        ps = PortfolioState(**sample_portfolio_state)
        assert ps.portfolio_value_dollars == 100000.0

    def test_zero_portfolio_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioState(
                portfolio_value_cents=0,
                peak_value_cents=100,
                current_positions_value_cents=0,
                today_realized_loss_cents=0,
                today_unrealized_loss_cents=0,
                open_positions_count=0,
            )

    def test_negative_portfolio_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioState(
                portfolio_value_cents=-1,
                peak_value_cents=100,
                current_positions_value_cents=0,
                today_realized_loss_cents=0,
                today_unrealized_loss_cents=0,
                open_positions_count=0,
            )

    def test_zero_peak_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioState(
                portfolio_value_cents=100,
                peak_value_cents=0,
                current_positions_value_cents=0,
                today_realized_loss_cents=0,
                today_unrealized_loss_cents=0,
                open_positions_count=0,
            )

    def test_zero_ge0_fields_accepted(self) -> None:
        ps = PortfolioState(
            portfolio_value_cents=1,
            peak_value_cents=1,
            current_positions_value_cents=0,
            today_realized_loss_cents=0,
            today_unrealized_loss_cents=0,
            open_positions_count=0,
        )
        assert ps.current_positions_value_cents == 0

    def test_negative_ge0_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioState(
                portfolio_value_cents=100,
                peak_value_cents=100,
                current_positions_value_cents=-1,
                today_realized_loss_cents=0,
                today_unrealized_loss_cents=0,
                open_positions_count=0,
            )

    def test_negative_open_positions_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PortfolioState(
                portfolio_value_cents=100,
                peak_value_cents=100,
                current_positions_value_cents=0,
                today_realized_loss_cents=0,
                today_unrealized_loss_cents=0,
                open_positions_count=-1,
            )

    def test_extra_field_forbidden(self, sample_portfolio_state: dict) -> None:
        data = {**sample_portfolio_state, "extra": True}
        with pytest.raises(ValidationError):
            PortfolioState(**data)

    def test_roundtrip(self, sample_portfolio_state: dict) -> None:
        ps = PortfolioState(**sample_portfolio_state)
        data = ps.model_dump(exclude_computed_fields=True)
        ps2 = PortfolioState(**data)
        assert ps2.portfolio_value_cents == ps.portfolio_value_cents

    def test_json_roundtrip(self, sample_portfolio_state: dict) -> None:
        ps = PortfolioState(**sample_portfolio_state)
        raw = ps.model_dump_json(exclude_computed_fields=True)
        restored = PortfolioState.model_validate_json(raw)
        assert restored.portfolio_value_cents == ps.portfolio_value_cents


class TestTradeRequest:
    def test_valid(self) -> None:
        tr = TradeRequest(
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=55,
            estimated_prob=0.6,
            confidence=0.8,
            edge_estimate=0.05,
            market_price_cents=50,
            market_open_interest=5000,
        )
        assert tr.quantity == 10

    def test_computed_price_dollars(self) -> None:
        tr = TradeRequest(
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=55,
            estimated_prob=0.6,
            confidence=0.8,
            edge_estimate=0.05,
            market_price_cents=50,
            market_open_interest=5000,
        )
        assert tr.price_dollars == 0.55

    def test_zero_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=0,
                price_cents=55,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
            )

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=-1,
                price_cents=55,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
            )

    def test_zero_price_cents_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price_cents=0,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
            )

    def test_zero_market_price_cents_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price_cents=55,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=0,
                market_open_interest=5000,
            )

    def test_estimated_prob_boundary_0(self) -> None:
        TradeRequest(
            ticker="KX-TEST",
            direction="no",
            quantity=10,
            price_cents=55,
            estimated_prob=0.0,
            confidence=0.8,
            edge_estimate=0.05,
            market_price_cents=50,
            market_open_interest=5000,
        )

    def test_estimated_prob_boundary_1(self) -> None:
        TradeRequest(
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=55,
            estimated_prob=1.0,
            confidence=0.8,
            edge_estimate=0.05,
            market_price_cents=50,
            market_open_interest=5000,
        )

    def test_estimated_prob_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price_cents=55,
                estimated_prob=1.1,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
            )

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price_cents=55,
                estimated_prob=0.6,
                confidence=-0.1,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
            )

    def test_negative_open_interest_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price_cents=55,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=-1,
            )

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="neutral",
                quantity=10,
                price_cents=55,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
            )

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TradeRequest(
                ticker="KX-TEST",
                direction="yes",
                quantity=10,
                price_cents=55,
                estimated_prob=0.6,
                confidence=0.8,
                edge_estimate=0.05,
                market_price_cents=50,
                market_open_interest=5000,
                extra=True,
            )

    def test_roundtrip(self) -> None:
        tr = TradeRequest(
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=55,
            estimated_prob=0.6,
            confidence=0.8,
            edge_estimate=0.05,
            market_price_cents=50,
            market_open_interest=5000,
        )
        data = tr.model_dump(exclude_computed_fields=True)
        assert TradeRequest(**data) == tr

    def test_json_roundtrip(self) -> None:
        tr = TradeRequest(
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=55,
            estimated_prob=0.6,
            confidence=0.8,
            edge_estimate=0.05,
            market_price_cents=50,
            market_open_interest=5000,
        )
        raw = tr.model_dump_json(exclude_computed_fields=True)
        restored = TradeRequest.model_validate_json(raw)
        assert restored.price_cents == tr.price_cents


class TestMarketCategoryValidator:
    def test_known_category_passes(self) -> None:
        market = Market(
            ticker="KXBTC-26MAR31-T55000",
            question="Bitcoin above 55000?",
            outcome_prices=["0.5", "0.5"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
            status="open",
            event_ticker="KXBTC-26MAR31",
            category="crypto",
        )
        assert market.category == "crypto"

    def test_unknown_category_passes_through(self) -> None:
        market = Market(
            ticker="KXBTC-26MAR31-T55000",
            question="Bitcoin above 55000?",
            outcome_prices=["0.5", "0.5"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
            status="open",
            event_ticker="KXBTC-26MAR31",
            category="unknown_category_xyz",
        )
        assert market.category == "unknown_category_xyz"

    def test_none_category_passes(self) -> None:
        market = Market(
            ticker="KXBTC-26MAR31-T55000",
            question="Bitcoin above 55000?",
            outcome_prices=["0.5", "0.5"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
            status="open",
            event_ticker="KXBTC-26MAR31",
            category=None,
        )
        assert market.category is None


class TestNormalizeTrade:
    def test_price_dollars_fixed_point_to_cents(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_dollars": "0.5500",
            "count_fp": "10",
            "side": "yes",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.price == 55
        assert trade.quantity == 10
        assert trade.side == "yes"
        assert trade.ticker == "KX-TEST"

    def test_price_fp_fallback(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_fp": "0.4500",
            "count_fp": "5",
            "side": "no",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.price == 45
        assert trade.side == "no"

    def test_missing_price_defaults_to_zero(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "count_fp": "10",
            "side": "yes",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.price == 0

    def test_missing_count_defaults_to_zero(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_dollars": "0.5500",
            "side": "yes",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.quantity == 0

    def test_missing_side_defaults_to_yes(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_dollars": "0.5500",
            "count_fp": "10",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.side == "yes"

    def test_timestamp_int_converted_to_datetime(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_dollars": "0.5500",
            "count_fp": "10",
            "side": "yes",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.timestamp == datetime(2025, 4, 20, 12, 0, 0, tzinfo=UTC)

    def test_created_time_fallback_for_missing_timestamp(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_dollars": "0.5500",
            "count_fp": "10",
            "side": "yes",
            "created_time": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.timestamp is not None

    def test_price_fp_overrides_price_dollars_when_both_none(self) -> None:
        raw = {
            "ticker": "KX-TEST",
            "price_dollars": "0.0000",
            "price_fp": None,
            "count_fp": "10",
            "side": "yes",
            "timestamp": 1745150400,
        }
        trade = normalize_trade_raw(raw)
        assert trade.price == 0

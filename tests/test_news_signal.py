"""Tests for generate_signal() sentiment integration and default_weights()."""

from traderbot.analysis.signals import CombinedSignal, default_weights, generate_signal


def _make_orderbook(best_yes: int = 50, best_no: int = 50) -> object:
    from traderbot.kalshi.models import OrderBook, OrderBookLevel

    return OrderBook(
        yes_bids=[OrderBookLevel(price=best_yes, size=100)],
        no_bids=[OrderBookLevel(price=best_no, size=100)],
    )


def _make_trades(count: int = 20, price: int = 50) -> list:
    from datetime import UTC, datetime, timedelta
    from traderbot.kalshi.models import Trade

    now = datetime.now(UTC)
    return [
        Trade(ticker="KX_TEST", price=price, quantity=10, side="yes", timestamp=now - timedelta(minutes=i))
        for i in range(count)
    ]


class TestDefaultWeights:
    """default_weights returns 3 or 4 entries based on include_sentiment."""

    def test_without_sentiment(self) -> None:
        w = default_weights(include_sentiment=False)
        assert len(w) == 3
        assert "sentiment" not in w
        assert "indicators" in w
        assert "odds" in w
        assert "momentum" in w

    def test_with_sentiment(self) -> None:
        w = default_weights(include_sentiment=True)
        assert len(w) == 4
        assert "sentiment" in w

    def test_weights_sum(self) -> None:
        assert abs(sum(default_weights(False).values()) - 1.0) < 1e-9
        assert abs(sum(default_weights(True).values()) - 1.0) < 1e-9


class TestGenerateSignalWithoutSentiment:
    """generate_signal without news_sentiment returns 3 sources (backward compat)."""

    def test_three_sources_when_no_sentiment(self) -> None:
        prices = list(range(40, 60))
        trades = _make_trades()
        ob = _make_orderbook()
        signal = generate_signal("KX_TEST", prices, trades, ob, 0.55)
        assert isinstance(signal, CombinedSignal)
        assert len(signal.sources) == 3
        names = [s.name for s in signal.sources]
        assert "sentiment" not in names
        assert "indicators" in names
        assert "odds" in names
        assert "momentum" in names


class TestGenerateSignalWithSentiment:
    """generate_signal with news_sentiment returns 4 sources including 'sentiment'."""

    def test_four_sources_with_positive_sentiment(self) -> None:
        prices = list(range(40, 60))
        trades = _make_trades()
        ob = _make_orderbook()
        signal = generate_signal("KX_TEST", prices, trades, ob, 0.55, news_sentiment=0.5)
        assert len(signal.sources) == 4
        names = [s.name for s in signal.sources]
        assert "sentiment" in names

    def test_negative_sentiment_direction(self) -> None:
        prices = list(range(40, 60))
        trades = _make_trades()
        ob = _make_orderbook()
        signal = generate_signal("KX_TEST", prices, trades, ob, 0.55, news_sentiment=-0.3)
        sent = next(s for s in signal.sources if s.name == "sentiment")
        assert sent.direction == "no"

    def test_small_sentiment_direction_neutral(self) -> None:
        prices = list(range(40, 60))
        trades = _make_trades()
        ob = _make_orderbook()
        signal = generate_signal("KX_TEST", prices, trades, ob, 0.55, news_sentiment=0.05)
        sent = next(s for s in signal.sources if s.name == "sentiment")
        assert sent.direction == "neutral"

    def test_positive_sentiment_direction_yes(self) -> None:
        prices = list(range(40, 60))
        trades = _make_trades()
        ob = _make_orderbook()
        signal = generate_signal("KX_TEST", prices, trades, ob, 0.55, news_sentiment=0.5)
        sent = next(s for s in signal.sources if s.name == "sentiment")
        assert sent.direction == "yes"
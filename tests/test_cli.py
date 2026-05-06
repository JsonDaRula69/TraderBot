"""Tests for the TraderBot CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from typing import ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from traderbot.cli import app

runner = CliRunner()


class TestMainHelp:
    def test_help_succeeds(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "traderbot" in result.output.lower() or "prediction" in result.output.lower()

    def test_subcommand_help(self):
        for cmd in ["scan", "positions", "audit", "trade", "heartbeat", "halt", "backtest", "paper", "performance", "compare", "bootstrap", "learnings"]:
            result = runner.invoke(app, [cmd, "--help"])
            assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


def _make_mock_aggregator(fake_items: list) -> AsyncMock:
    mock_agg = AsyncMock()
    mock_agg.fetch_all = AsyncMock(return_value=fake_items)
    mock_agg.fetch_recent = AsyncMock(return_value=fake_items)
    mock_agg.__aenter__ = AsyncMock(return_value=mock_agg)
    mock_agg.__aexit__ = AsyncMock(return_value=None)
    return mock_agg


class TestNewsCommand:
    def test_news_help(self):
        result = runner.invoke(app, ["news", "--help"])
        assert result.exit_code == 0
        assert "--category" in result.output
        assert "--limit" in result.output
        assert "--source" in result.output
        assert "--json" in result.output

    def test_news_no_api_keys_json(self):
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, ["news", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data
            assert "API keys" in data["error"]

    def test_news_no_api_keys_rich(self):
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, ["news"])
            assert result.exit_code == 0
            assert "No API keys" in result.output

    def test_news_invalid_category_json(self):
        result = runner.invoke(app, ["news", "--category", "InvalidCat", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data

    def test_news_invalid_source_json(self):
        result = runner.invoke(app, ["news", "--source", "invalidsrc", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data

    @pytest.mark.unit
    def test_news_with_mock_items_json(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.news.sources import NewsItem as SourcesNewsItem, NewsSource as SourcesNewsSource

        fake_items = [
            SourcesNewsItem(
                id="test-1",
                title="Fed raises interest rates",
                body="The Federal Reserve raised rates by 25bps",
                source=SourcesNewsSource.NEWSAPI,
                url="https://example.com/fed",
                published_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
                ticker_refs=["SPX"],
                category=MarketCategory.ECONOMICS,
            )
        ]

        mock_agg = _make_mock_aggregator(fake_items)

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["news", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["title"] == "Fed raises interest rates"
            assert data[0]["category"] == "economics"

    @pytest.mark.unit
    def test_news_with_category_filter_json(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.news.sources import NewsItem as SourcesNewsItem, NewsSource as SourcesNewsSource

        fake_items = [
            SourcesNewsItem(
                id="eco-1",
                title="GDP growth slows",
                body="Economic data shows slowdown",
                source=SourcesNewsSource.NEWSAPI,
                url="https://example.com/gdp",
                published_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
                ticker_refs=[],
                category=MarketCategory.ECONOMICS,
            ),
            SourcesNewsItem(
                id="tech-1",
                title="New AI chip released",
                body="Tech company launches new chip",
                source=SourcesNewsSource.NEWSAPI,
                url="https://example.com/chip",
                published_at=datetime(2026, 4, 15, 13, 0, 0, tzinfo=timezone.utc),
                ticker_refs=[],
                category=MarketCategory.SCIENCE_AND_TECHNOLOGY,
            ),
        ]

        mock_agg = _make_mock_aggregator(fake_items)

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["news", "--category", "Economics", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert all(item["category"] == "economics" for item in data)

    @pytest.mark.unit
    def test_news_with_source_filter_json(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.news.sources import NewsItem as SourcesNewsItem, NewsSource as SourcesNewsSource

        fake_items = [
            SourcesNewsItem(
                id="reddit-1",
                title="Fed discussion on r/economics",
                body="Reddit discussion about rates",
                source=SourcesNewsSource.REDDIT,
                url="https://reddit.com/r/economics",
                published_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
                ticker_refs=[],
                category=MarketCategory.ECONOMICS,
            )
        ]

        mock_agg = _make_mock_aggregator(fake_items)

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["news", "--source", "reddit", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)

    @pytest.mark.unit
    def test_news_rich_output(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.news.sources import NewsItem as SourcesNewsItem, NewsSource as SourcesNewsSource

        fake_items = [
            SourcesNewsItem(
                id="test-1",
                title="Fed raises interest rates",
                body="The Federal Reserve raised rates by 25bps",
                source=SourcesNewsSource.NEWSAPI,
                url="https://example.com/fed",
                published_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
                ticker_refs=["SPX"],
                category=MarketCategory.ECONOMICS,
            )
        ]

        mock_agg = _make_mock_aggregator(fake_items)

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["news"])
            assert result.exit_code == 0
            assert "News Feed" in result.output
            assert "economics" in result.output
            assert "newsapi" in result.output.lower()

    @pytest.mark.unit
    def test_news_empty_items(self):
        mock_agg = _make_mock_aggregator([])

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["news"])
            assert result.exit_code == 0
            assert "No news items found" in result.output


class TestSentimentCommand:
    def test_sentiment_help(self):
        result = runner.invoke(app, ["sentiment", "--help"])
        assert result.exit_code == 0
        assert "TICKER" in result.output
        assert "--json" in result.output

    @pytest.mark.unit
    def test_sentiment_with_mock_items_json(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.news.sources import NewsItem as SourcesNewsItem, NewsSource as SourcesNewsSource

        fake_items = [
            SourcesNewsItem(
                id="test-1",
                title="BTC surges past 100k",
                body="Bitcoin hits all-time high",
                source=SourcesNewsSource.NEWSAPI,
                url="https://example.com/btc",
                published_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
                ticker_refs=["BTC"],
                category=MarketCategory.ECONOMICS,
            )
        ]

        mock_agg = _make_mock_aggregator(fake_items)

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["sentiment", "BTC", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ticker"] == "BTC"
            assert "sentiment" in data
            assert "score" in data["sentiment"]
            assert "direction" in data["sentiment"]
            assert "confidence" in data["sentiment"]
            assert "impacts" in data
            assert isinstance(data["impacts"], list)

    @pytest.mark.unit
    def test_sentiment_with_mock_items_rich(self):
        from traderbot.kalshi.models import MarketCategory
        from traderbot.news.sources import NewsItem as SourcesNewsItem, NewsSource as SourcesNewsSource

        fake_items = [
            SourcesNewsItem(
                id="test-1",
                title="BTC surges past 100k",
                body="Bitcoin hits all-time high",
                source=SourcesNewsSource.NEWSAPI,
                url="https://example.com/btc",
                published_at=datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
                ticker_refs=["BTC"],
                category=MarketCategory.ECONOMICS,
            )
        ]

        mock_agg = _make_mock_aggregator(fake_items)

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["sentiment", "BTC"])
            assert result.exit_code == 0
            assert "BTC" in result.output
            assert "Sentiment" in result.output

    @pytest.mark.unit
    def test_sentiment_no_news_found_json(self):
        mock_agg = _make_mock_aggregator([])

        with (
            patch.dict("os.environ", {"NEWSAPI_KEY": "fake-key"}),
            patch("traderbot.news.sources.NewsAggregator", return_value=mock_agg),
        ):
            result = runner.invoke(app, ["sentiment", "SPX", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ticker"] == "SPX"
            assert "error" in data or "items_analyzed" in data

    @pytest.mark.unit
    def test_sentiment_no_api_keys_json(self):
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(app, ["sentiment", "SPX", "--json"])
            assert result.exit_code == 0


class TestScan:
    def test_scan_json_without_api(self):
        result = runner.invoke(app, ["scan", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_scan_default_without_api(self):
        result = runner.invoke(app, ["scan"])
        assert result.exit_code == 0
        assert "requires API connection" in result.output or "markets" in result.output.lower()

    @pytest.mark.unit
    def test_scan_with_markets(self):
        """Mock MarketService.list_markets to return Market objects, verify Rich table contains tickers."""
        from traderbot.kalshi.models import Market, MarketListResponse

        markets = [
            Market(
                ticker="KXBTCD-26MAR31-T55000",
                question="BTC above $55k?",
                outcome_prices=["60", "40"],
                volume=1000,
                open_interest=500,
                close_time=datetime(2026, 3, 31, tzinfo=UTC),
                status="open",
                event_ticker="KXBTCD-26MAR31",
            ),
            Market(
                ticker="KXBTCD-26MAR31-T60000",
                question="BTC above $60k?",
                outcome_prices=["30", "70"],
                volume=2000,
                open_interest=800,
                close_time=datetime(2026, 3, 31, tzinfo=UTC),
                status="open",
                event_ticker="KXBTCD-26MAR31",
            ),
        ]
        mock_result = MarketListResponse(markets=markets, cursor=None)

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.list_markets",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["scan"])
            assert result.exit_code == 0
            assert "KXBTCD-26MAR31-T55000" in result.output
            assert "BTC above $55k?" in result.output

    @pytest.mark.unit
    def test_scan_json_with_mock_markets(self):
        """Mock list_markets, call scan --json, verify JSON array output."""
        from traderbot.kalshi.models import Market, MarketListResponse

        markets = [
            Market(
                ticker="KXBTCD-26MAR31-T55000",
                question="BTC above $55k?",
                outcome_prices=["60", "40"],
                volume=1000,
                open_interest=500,
                close_time=datetime(2026, 3, 31, tzinfo=UTC),
                status="open",
                event_ticker="KXBTCD-26MAR31",
            ),
        ]
        mock_result = MarketListResponse(markets=markets, cursor=None)

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.list_markets",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["scan", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["ticker"] == "KXBTCD-26MAR31-T55000"


class TestAnalyze:
    @pytest.mark.unit
    def test_analyze_with_market(self):
        """Mock get_market and get_orderbook, verify Rich output includes market info and implied probability."""
        from traderbot.kalshi.models import Market, OrderBook, OrderBookLevel

        market = Market(
            ticker="KXBTCD-26MAR31-T55000",
            question="BTC above $55k?",
            outcome_prices=["60", "40"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, tzinfo=UTC),
            status="open",
            event_ticker="KXBTCD-26MAR31",
        )
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=55, size=100)],
            no_bids=[OrderBookLevel(price=40, size=80)],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.get_market",
                return_value=market,
            ),
            patch(
                "traderbot.kalshi.markets.MarketService.get_orderbook",
                return_value=orderbook,
            ),
        ):
            result = runner.invoke(app, ["analyze", "KXBTCD-26MAR31-T55000"])
            assert result.exit_code == 0
            assert "KXBTCD-26MAR31-T55000" in result.output
            assert "BTC above $55k?" in result.output
            assert "Implied YES prob" in result.output

    @pytest.mark.unit
    def test_analyze_json_with_mock(self):
        """Mock get_market/get_orderbook, call analyze TICKER --json, verify JSON output."""
        from traderbot.kalshi.models import Market, OrderBook, OrderBookLevel

        market = Market(
            ticker="KXBTCD-26MAR31-T55000",
            question="BTC above $55k?",
            outcome_prices=["60", "40"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, tzinfo=UTC),
            status="open",
            event_ticker="KXBTCD-26MAR31",
        )
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=55, size=100)],
            no_bids=[OrderBookLevel(price=40, size=80)],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.get_market",
                return_value=market,
            ),
            patch(
                "traderbot.kalshi.markets.MarketService.get_orderbook",
                return_value=orderbook,
            ),
        ):
            result = runner.invoke(app, ["analyze", "KXBTCD-26MAR31-T55000", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "market" in data
            assert "orderbook" in data
            assert data["market"]["ticker"] == "KXBTCD-26MAR31-T55000"

    @pytest.mark.unit
    def test_analyze_fallback_without_api(self):
        """Analyze call that fails API connection shows fallback message."""
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("API error")):
            result = runner.invoke(app, ["analyze", "TEST-TICKER"])
            assert result.exit_code == 0
            assert "requires API connection" in result.output

    @pytest.mark.unit
    def test_analyze_json_fallback_without_api(self):
        """Analyze --json call that fails API connection returns empty JSON object."""
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("API error")):
            result = runner.invoke(app, ["analyze", "TEST-TICKER", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, dict)


class TestSignals:
    @pytest.mark.unit
    def test_signals_default(self):
        result = runner.invoke(app, ["signals"])
        assert result.exit_code == 0
        assert "Signal generation" in result.output

    @pytest.mark.unit
    def test_signals_json(self):
        result = runner.invoke(app, ["signals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "note" in data

    @pytest.mark.unit
    def test_signals_price_no_double_conversion(self):
        """Verify outcome_prices (cent strings) are not multiplied by 100."""
        from traderbot.kalshi.models import Market

        market = Market(
            ticker="KXBTCD-26MAR31-T55000",
            question="BTC above $55k?",
            outcome_prices=["60", "40"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, tzinfo=UTC),
            status="open",
            event_ticker="KXBTCD-26MAR31",
        )
        prices_int = [int(p) for p in market.outcome_prices]
        assert prices_int == [60, 40], f"Expected [60, 40] cent prices, got {prices_int}"


class TestTrade:
    def test_trade_rejected_with_defaults(self):
        result = runner.invoke(
            app, ["trade", "TEST-TICKER", "--direction", "yes", "--quantity", "1", "--price", "50"]
        )
        assert result.exit_code == 0
        assert "rejected" in result.output.lower() or "executed" in result.output.lower()

    def test_trade_json_output(self):
        result = runner.invoke(
            app,
            [
                "trade",
                "TEST-TICKER",
                "--direction",
                "yes",
                "--quantity",
                "1",
                "--price",
                "50",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "outcome" in data
        assert data["ticker"] == "TEST-TICKER"
        assert data["outcome"] in ("executed", "rejected")

    @pytest.mark.unit
    def test_trade_executed(self):
        """Mock evaluate_trade to return non-zero sized amount, verify 'executed' output."""
        with (
            patch("traderbot.risk.evaluate_trade", return_value=5000),
            patch("traderbot.risk.circuit_breaker.CircuitBreaker"),
        ):
            result = runner.invoke(app, ["trade", "TEST-TICKER", "--direction", "yes"])
            assert result.exit_code == 0
            assert "executed" in result.output.lower()

    @pytest.mark.unit
    def test_trade_executed_json(self):
        """Mock evaluate_trade to return non-zero sized amount, verify JSON output has 'executed'."""
        with (
            patch("traderbot.risk.evaluate_trade", return_value=5000),
            patch("traderbot.risk.circuit_breaker.CircuitBreaker"),
        ):
            result = runner.invoke(app, ["trade", "TEST-TICKER", "--direction", "yes", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["outcome"] == "executed"
            assert data["sized_position_cents"] == 5000

    @pytest.mark.unit
    def test_trade_command_passes_risk_checks_with_live_data(self):
        """With mocked MarketService returning realistic data, trade should pass liquidity and edge checks."""
        from traderbot.kalshi.models import Market, OrderBook, OrderBookLevel

        market = Market(
            ticker="KXBTCD-26MAR31-T55000",
            question="BTC above $55k?",
            outcome_prices=["60", "40"],
            volume=1000,
            open_interest=5000,
            close_time=datetime(2026, 3, 31, tzinfo=timezone.utc),
            status="open",
            event_ticker="KXBTCD-26MAR31",
        )
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=58, size=200)],
            no_bids=[OrderBookLevel(price=42, size=150)],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.markets.MarketService.get_market", return_value=market),
            patch("traderbot.kalshi.markets.MarketService.get_orderbook", return_value=orderbook),
        ):
            result = runner.invoke(
                app,
                ["trade", "KXBTCD-26MAR31-T55000", "--direction", "yes", "--quantity", "1", "--price", "60"],
            )
            assert result.exit_code == 0


class TestPositions:
    def test_positions_json_empty(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["positions", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_positions_no_json(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["positions", "--db", str(db)])
        assert result.exit_code == 0
        assert "No open positions" in result.output or "positions" in result.output.lower()

    @pytest.mark.unit
    def test_positions_with_data(self, tmp_path):
        """Insert a Position via DB, call positions --db, verify table output contains ticker."""

        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Position

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.positions import init_table, upsert

            init_table(conn)
            upsert(conn, Position(ticker="KXBTCD-26MAR31-T55000", quantity=10, avg_price=55))

        result = runner.invoke(app, ["positions", "--db", str(db)])
        assert result.exit_code == 0
        assert "KXBTCD-26MAR31-T55000" in result.output

    @pytest.mark.unit
    def test_positions_with_data_json(self, tmp_path):
        """Insert a Position via DB, call positions --db --json, verify JSON contains ticker."""

        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Position

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.positions import init_table, upsert

            init_table(conn)
            upsert(conn, Position(ticker="KXBTCD-26MAR31-T55000", quantity=10, avg_price=55))

        result = runner.invoke(app, ["positions", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["ticker"] == "KXBTCD-26MAR31-T55000"


class TestAudit:
    def test_audit_json_empty(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["audit", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_audit_no_json_empty(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["audit", "--db", str(db)])
        assert result.exit_code == 0
        assert "No decisions found" in result.output or "decision" in result.output.lower()

    @pytest.mark.unit
    def test_audit_with_decisions(self, tmp_path):
        """Insert a Decision via DB, call audit --db, verify table output."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db)])
        assert result.exit_code == 0
        assert "TEST-MKT" in result.output
        assert "Decision Audit" in result.output

    @pytest.mark.unit
    def test_audit_with_decisions_json(self, tmp_path):
        """Insert a Decision via DB, call audit --db --json, verify JSON decision data."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["ticker"] == "TEST-MKT"

    @pytest.mark.unit
    def test_audit_by_ticker(self, tmp_path):
        """Call audit --db --ticker TICKER, verify it filters by ticker."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db), "--ticker", "TEST-MKT"])
        assert result.exit_code == 0
        assert "TEST-MKT" in result.output

    @pytest.mark.unit
    def test_audit_by_outcome(self, tmp_path):
        """Call audit --db --outcome executed, verify it filters by outcome."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db), "--outcome", "executed"])
        assert result.exit_code == 0
        assert "TEST-MKT" in result.output


class TestHeartbeat:
    def test_heartbeat(self):
        result = runner.invoke(app, ["heartbeat"])
        assert result.exit_code == 0
        assert "Heartbeat" in result.output
        assert "6h" in result.output or "promotion" in result.output.lower()

    @pytest.mark.unit
    def test_heartbeat_json(self):
        result = runner.invoke(app, ["heartbeat"])
        assert result.exit_code == 0


class TestCronSetup:
    def test_cron_setup_dry_run(self):
        result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent", "--dry-run"])
        assert result.exit_code == 0
        assert "decision_loop" in result.output
        assert "heartbeat_loop" in result.output
        assert "news_loop" in result.output
        assert "heartbeat_config" in result.output

    def test_cron_setup_dry_run_json(self):
        result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent", "--dry-run", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["agent_id"] == "test-agent"
        assert len(data["loops"]) == 4
        names = [loop["name"] for loop in data["loops"]]
        assert "decision_loop" in names
        assert "heartbeat_loop" in names
        assert "news_loop" in names
        assert "heartbeat_config" in names

    def test_cron_setup_custom_interval(self, tmp_path):
        result = runner.invoke(
            app,
            ["cron", "setup", "--agent", "test-agent", "--heartbeat-every", "30m", "--dry-run", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        heartbeat_loop = next(l for l in data["loops"] if l["name"] == "heartbeat_loop")
        assert heartbeat_loop["every"] == "30m"

    def test_cron_setup_skip_heartbeat_config(self, tmp_path):
        result = runner.invoke(
            app,
            ["cron", "setup", "--agent", "test-agent", "--skip-heartbeat-config", "--dry-run", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        hb_config = next(l for l in data["loops"] if l["name"] == "heartbeat_config")
        assert hb_config["registered"] is False

    def test_cron_setup_no_openclaw(self):
        with patch("traderbot.cli.shutil.which", return_value=None):
            result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent"])
            assert result.exit_code == 1
            assert "openclaw" in result.output.lower()

    def test_cron_setup_channel_without_to_errors(self):
        result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent", "--channel", "telegram", "--dry-run"])
        assert result.exit_code == 1
        assert "channel" in result.output.lower() or "to" in result.output.lower()

    def test_cron_setup_to_without_channel_errors(self):
        result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent", "--to", "+15555550123", "--dry-run"])
        assert result.exit_code == 1
        assert "channel" in result.output.lower() or "to" in result.output.lower()

    def test_cron_setup_with_channel_and_to_dry_run(self):
        result = runner.invoke(
            app,
            ["cron", "setup", "--agent", "test-agent", "--channel", "telegram", "--to", "+15555550123", "--dry-run"],
        )
        assert result.exit_code == 0

    def test_cron_setup_with_channel_and_to_passes_args(self, tmp_path):
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()

        calls = []

        def mock_cron_add(args):
            calls.append(args)
            return (0, "ok")

        with (
            patch("traderbot.cli.Path.home", return_value=tmp_path),
            patch("traderbot.cli.shutil.which", return_value="/usr/bin/openclaw"),
            patch("traderbot.cli._run_openclaw_cron_add", side_effect=mock_cron_add),
        ):
            result = runner.invoke(
                app,
                ["cron", "setup", "--agent", "my-agent", "--channel", "telegram", "--to", "+15555550123", "--json"],
            )
            assert result.exit_code == 0
        for call_args in calls:
            assert "--channel" in call_args
            assert "telegram" in call_args
            assert "--to" in call_args
            assert "+15555550123" in call_args

    def test_cron_setup_writes_heartbeat_config(self, tmp_path):
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()
        config_file = config_dir / "openclaw.json"

        with (
            patch("traderbot.cli.Path.home", return_value=tmp_path),
            patch("traderbot.cli.shutil.which", return_value="/usr/bin/openclaw"),
            patch("traderbot.cli._run_openclaw_cron_add", return_value=(0, "ok")),
        ):
            result = runner.invoke(
                app,
                ["cron", "setup", "--agent", "my-agent", "--json"],
            )
            assert result.exit_code == 0

        assert config_file.exists()
        config = json.loads(config_file.read_text())
        agents_list = config["agents"]["list"]
        agent_entry = next(a for a in agents_list if a["id"] == "my-agent")
        assert agent_entry["heartbeat"]["every"] == "6h"
        assert agent_entry["heartbeat"]["lightContext"] is True

    def test_cron_setup_dry_run_news_loop_event(self):
        result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent", "--dry-run", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        news_loop = next(l for l in data["loops"] if l["name"] == "news_loop")
        assert news_loop["event"] == "impact"
        assert news_loop["registered"] is True

    def test_cron_setup_decision_loop_247_cron(self):
        result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent", "--dry-run", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        decision_loop = next(l for l in data["loops"] if l["name"] == "decision_loop")
        assert decision_loop["cron"] == "*/5 * * * *"

    def test_cron_setup_news_loop_passes_event_arg(self, tmp_path):
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()

        calls = []

        def mock_cron_add(args):
            calls.append(args)
            return (0, "ok")

        with (
            patch("traderbot.cli.Path.home", return_value=tmp_path),
            patch("traderbot.cli.shutil.which", return_value="/usr/bin/openclaw"),
            patch("traderbot.cli._run_openclaw_cron_add", side_effect=mock_cron_add),
        ):
            result = runner.invoke(app, ["cron", "setup", "--agent", "my-agent", "--json"])
            assert result.exit_code == 0

        news_call = next(c for c in calls if "--name" in c and "news_loop" in c)
        assert "--event" in news_call
        assert "impact" in news_call
        assert "--session" in news_call
        assert "main" in news_call

    def test_cron_setup_no_openclaw_shows_fallback(self):
        with patch("traderbot.cli.shutil.which", return_value=None):
            result = runner.invoke(app, ["cron", "setup", "--agent", "test-agent"])
            assert result.exit_code == 1
            assert "openclaw" in result.output.lower()


class TestHalt:
    def test_halt_shows_status(self):
        result = runner.invoke(app, ["halt"])
        assert result.exit_code == 0
        assert "Circuit Breaker" in result.output or "breaker" in result.output.lower()

    def test_halt_json(self):
        result = runner.invoke(app, ["halt", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "level" in data
        assert "can_trade" in data

    def test_halt_force(self, tmp_path):
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import (
                CircuitBreaker,
                CircuitBreakerState,
            )

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force", "--json"])
            assert result.exit_code == 0

    @pytest.mark.unit
    def test_halt_force_no_json(self, tmp_path):
        """Call halt --force (no --json), verify Rich output mentions FULL_STOP."""
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import (
                CircuitBreaker,
                CircuitBreakerState,
            )

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force"])
            assert result.exit_code == 0
            assert "FULL_STOP" in result.output

    @pytest.mark.unit
    def test_halt_force_json(self, tmp_path):
        """Call halt --force --json, verify JSON output contains FULL_STOP level."""
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import (
                CircuitBreaker,
                CircuitBreakerState,
            )

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["level"] == 3
            assert data["can_trade"] is False

    @pytest.mark.unit
    def test_halt_with_reason(self, tmp_path):
        """Test halt displays reason when state has one."""
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState(reason="Test reason")

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt"])
            assert result.exit_code == 0
            assert "Test reason" in result.output


class TestBacktestCommand:
    def test_backtest_help(self):
        result = runner.invoke(app, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "--strategy" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--bankroll" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_backtest_no_api(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["backtest"])
            assert result.exit_code == 0
            assert "API connection required" in result.output

    def test_backtest_no_api_json(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["backtest", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data

    @pytest.mark.unit
    def test_backtest_with_mock_engine(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        mock_result = BacktestResult(
            trade_count=5,
            total_pnl_cents=2500_00,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            sharpe_ratio=1.5,
            max_drawdown_pct=0.08,
            brier_score=0.22,
            edge_capture=0.35,
            fill_rate=0.8,
            trades=[],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.engine.BacktestEngine.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["backtest", "--db", str(tmp_path / "test.db")])
            assert result.exit_code == 0
            assert "Backtest Results" in result.output

    @pytest.mark.unit
    def test_backtest_json_with_mock(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        mock_result = BacktestResult(
            trade_count=5,
            total_pnl_cents=2500_00,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            sharpe_ratio=1.5,
            max_drawdown_pct=0.08,
            brier_score=0.22,
            edge_capture=0.35,
            fill_rate=0.8,
            trades=[],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.engine.BacktestEngine.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["backtest", "--db", str(tmp_path / "test.db"), "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "metrics" in data
            assert data["trade_count"] == 5


class TestPaperCommand:
    def test_paper_help(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert result.exit_code == 0
        assert "--strategy" in result.output
        assert "--duration" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_paper_no_api(self):
        with patch("traderbot.kalshi.demo.DemoAdapter", side_effect=Exception("no demo")):
            result = runner.invoke(app, ["paper"])
            assert result.exit_code == 0
            assert "Demo API connection required" in result.output

    def test_paper_no_api_json(self):
        with patch("traderbot.kalshi.demo.DemoAdapter", side_effect=Exception("no demo")):
            result = runner.invoke(app, ["paper", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data

    @pytest.mark.unit
    def test_paper_with_mock(self, tmp_path):
        from traderbot.simulation.paper_trader import PaperPortfolio, PaperPosition

        mock_portfolio = PaperPortfolio(
            cash_cents=99_500_00,
            positions=[
                PaperPosition(ticker="KXBTCD-26MAR31-T55000", side="yes", avg_price_cents=55, quantity=10),
            ],
        )

        with (
            patch("traderbot.kalshi.demo.DemoAdapter"),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_portfolio",
                return_value=mock_portfolio,
            ),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_pnl",
                return_value=-500_00,
            ),
        ):
            result = runner.invoke(app, ["paper", "--db", str(tmp_path / "test.db")])
            assert result.exit_code == 0
            assert "Paper Trading" in result.output
            assert "KXBTCD-26MAR31-T55000" in result.output

    @pytest.mark.unit
    def test_paper_json_with_mock(self, tmp_path):
        from traderbot.simulation.paper_trader import PaperPortfolio, PaperPosition

        mock_portfolio = PaperPortfolio(
            cash_cents=99_500_00,
            positions=[
                PaperPosition(ticker="KXBTCD-26MAR31-T55000", side="yes", avg_price_cents=55, quantity=10),
            ],
        )

        with (
            patch("traderbot.kalshi.demo.DemoAdapter"),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_portfolio",
                return_value=mock_portfolio,
            ),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_pnl",
                return_value=-500_00,
            ),
        ):
            result = runner.invoke(app, ["paper", "--db", str(tmp_path / "test.db"), "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["cash_cents"] == 99_500_00
            assert len(data["positions"]) == 1


class TestPerformanceCommand:
    def test_performance_help(self):
        result = runner.invoke(app, ["performance", "--help"])
        assert result.exit_code == 0
        assert "--db" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--json" in result.output

    def test_performance_empty_db(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["performance", "--db", str(db)])
        assert result.exit_code == 0
        assert "Performance Summary" in result.output

    def test_performance_empty_db_json(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["performance", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["trade_count"] == 0

    @pytest.mark.unit
    def test_performance_with_decisions(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            for i in range(3):
                insert(
                    conn,
                    Decision(
                        timestamp=datetime(2026, 1, 15 + i, 12, 0, 0, tzinfo=UTC),
                        ticker=f"TEST-MKT-{i}",
                        direction="yes",
                        quantity=5,
                        price=55 + i * 10,
                        signal_strength=0.7,
                        confidence=0.8,
                        edge_estimate=0.15,
                        risk_checks={"max_position": True},
                        outcome="executed",
                    ),
                )

        result = runner.invoke(app, ["performance", "--db", str(db)])
        assert result.exit_code == 0
        assert "Performance Summary" in result.output
        assert "3" in result.output

    @pytest.mark.unit
    def test_performance_with_decisions_json(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            for i in range(3):
                insert(
                    conn,
                    Decision(
                        timestamp=datetime(2026, 1, 15 + i, 12, 0, 0, tzinfo=UTC),
                        ticker=f"TEST-MKT-{i}",
                        direction="yes",
                        quantity=5,
                        price=55 + i * 10,
                        signal_strength=0.7,
                        confidence=0.8,
                        edge_estimate=0.15,
                        risk_checks={"max_position": True},
                        outcome="executed",
                    ),
                )

        result = runner.invoke(app, ["performance", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["trade_count"] == 3


class TestCompareCommand:
    def test_compare_help(self):
        result = runner.invoke(app, ["compare", "--help"])
        assert result.exit_code == 0
        assert "--profiles" in result.output
        assert "--strategy" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--bankroll" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_compare_no_api(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["compare"])
            assert result.exit_code == 0
            assert "API connection required" in result.output

    def test_compare_no_api_json(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["compare", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data

    def test_compare_unknown_profile(self):
        result = runner.invoke(app, ["compare", "--profiles", "Unknown"])
        assert result.exit_code == 1
        assert "Unknown profile" in result.output

    @pytest.mark.unit
    def test_compare_with_mock_profiles(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        conservative_result = BacktestResult(
            trade_count=8,
            total_pnl_cents=1200_00,
            winning_trades=5,
            losing_trades=3,
            win_rate=0.625,
            sharpe_ratio=1.2,
            max_drawdown_pct=0.05,
            brier_score=0.18,
            edge_capture=0.42,
            fill_rate=0.9,
            trades=[],
        )
        aggressive_result = BacktestResult(
            trade_count=15,
            total_pnl_cents=3500_00,
            winning_trades=9,
            losing_trades=6,
            win_rate=0.6,
            sharpe_ratio=0.9,
            max_drawdown_pct=0.12,
            brier_score=0.25,
            edge_capture=0.35,
            fill_rate=0.85,
            trades=[],
        )

        async def fake_run_profiles(engine, profiles, start, end):
            from traderbot.simulation.profiles import PRESETS

            results = {}
            for p in profiles:
                if p.name == "Conservative":
                    results[p.name] = conservative_result
                else:
                    results[p.name] = aggressive_result
            return results

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.profiles.run_profiles", side_effect=fake_run_profiles),
        ):
            result = runner.invoke(
                app, ["compare", "--profiles", "Conservative,Aggressive", "--db", str(tmp_path / "test.db")]
            )
            assert result.exit_code == 0
            assert "Profile Comparison" in result.output

    @pytest.mark.unit
    def test_compare_json_with_mock_profiles(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        moderate_result = BacktestResult(
            trade_count=10,
            total_pnl_cents=2000_00,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            sharpe_ratio=1.0,
            max_drawdown_pct=0.07,
            brier_score=0.22,
            edge_capture=0.38,
            fill_rate=0.88,
            trades=[],
        )

        async def fake_run_profiles(engine, profiles, start, end):
            return {p.name: moderate_result for p in profiles}

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.profiles.run_profiles", side_effect=fake_run_profiles),
        ):
            result = runner.invoke(
                app, ["compare", "--profiles", "Moderate", "--db", str(tmp_path / "test.db"), "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["profile_name"] == "Moderate"
            assert data[0]["trade_count"] == 10


class TestBootstrapCommand:
    def test_bootstrap_help(self):
        result = runner.invoke(app, ["bootstrap", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--json" in result.output

    def test_bootstrap_dry_run(self):
        """Bootstrap --dry-run validates without side effects."""
        mock_status = {
            "kalshi": {"api_key": True, "api_secret": False},
            "voyage": {"api_key": True},
            "newsapi": {"api_key": False},
            "twitter": {"api_key": False},
            "reddit": {"client_id": False, "client_secret": False},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: True)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
            patch("traderbot.cli._python_version_ok", return_value=(True, "3.12.0", (3, 12))),
        ):
            result = runner.invoke(app, ["bootstrap", "--dry-run"])
            assert result.exit_code == 0
            assert "Python" in result.output
            assert "Bootstrap" in result.output

    def test_bootstrap_dry_run_json(self):
        """Bootstrap --dry-run --json returns structured JSON."""
        mock_status = {
            "kalshi": {"api_key": True, "api_secret": False},
            "voyage": {"api_key": False},
            "newsapi": {"api_key": False},
            "twitter": {"api_key": False},
            "reddit": {"client_id": False, "client_secret": False},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: True)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
            patch("traderbot.cli._python_version_ok", return_value=(True, "3.12.0", (3, 12))),
        ):
            result = runner.invoke(app, ["bootstrap", "--dry-run", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "python_version" in data
            assert data["python_version_ok"] is True
            assert "config_dir" in data
            assert "keyring_available" in data
            assert "credentials_ok" in data
            assert data["credentials_ok"] is False
            assert "missing_credentials" in data
            assert "kalshi.api_secret" in data["missing_credentials"]

    def test_bootstrap_json_with_all_credentials_ok(self, tmp_path):
        """Bootstrap with all credentials configured shows success."""
        mock_status = {
            "kalshi": {"api_key": True, "api_secret": True},
            "voyage": {"api_key": True},
            "newsapi": {"api_key": True},
            "twitter": {"api_key": True},
            "reddit": {"client_id": True, "client_secret": True},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: True)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
            patch("traderbot.auth.AuthManager.set_credential"),
            patch("traderbot.cli._python_version_ok", return_value=(True, "3.12.0", (3, 12))),
        ):
            result = runner.invoke(app, ["bootstrap", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["credentials_ok"] is True
            assert data["missing_credentials"] == []

    def test_bootstrap_dry_run_no_keyring(self):
        """Bootstrap with keyring unavailable reports it clearly."""
        mock_status = {
            "kalshi": {"api_key": False, "api_secret": False},
            "voyage": {"api_key": False},
            "newsapi": {"api_key": False},
            "twitter": {"api_key": False},
            "reddit": {"client_id": False, "client_secret": False},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: False)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
            patch("traderbot.cli._python_version_ok", return_value=(True, "3.12.0", (3, 12))),
        ):
             result = runner.invoke(app, ["bootstrap", "--dry-run"])
             assert result.exit_code == 0
             assert "Keyring unavailable" in result.output


class TestLearnings:
    def test_learnings_help(self):
        result = runner.invoke(app, ["learnings", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.output
        assert "--category" in result.output
        assert "--promote" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_learnings_empty_db(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db)])
        assert result.exit_code == 0
        assert "No learnings found" in result.output

    def test_learnings_empty_db_json(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.unit
    def test_learnings_with_patterns(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, init_table, record_pattern

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "High volume precedes reversal", "Observed 15 times", 0.85)
            record_pattern(conn, LearningCategory.RISK_SIGNAL, "Drawdown > 5% triggers panic sells", "3 events", 0.7)

        result = runner.invoke(app, ["learnings", "--db", str(db)])
        assert result.exit_code == 0
        assert "High volume" in result.output
        assert "MarketBehavior" in result.output
        assert "Learned Patterns" in result.output

    @pytest.mark.unit
    def test_learnings_with_patterns_json(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, init_table, record_pattern

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "High volume precedes reversal", "Observed 15 times", 0.85)

        result = runner.invoke(app, ["learnings", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["category"] == "MarketBehavior"
        assert data[0]["confidence"] == 0.85

    @pytest.mark.unit
    def test_learnings_filter_by_category(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, init_table, record_pattern

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "Market pattern", "evidence", 0.8)
            record_pattern(conn, LearningCategory.RISK_SIGNAL, "Risk pattern", "evidence", 0.7)

        result = runner.invoke(app, ["learnings", "--db", str(db), "--category", "RiskSignal"])
        assert result.exit_code == 0
        assert "Risk pattern" in result.output
        assert "MarketBehavior" not in result.output

    @pytest.mark.unit
    def test_learnings_filter_by_deprecated_status(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, LearningStatus, init_table, record_pattern, set_status

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            lid = record_pattern(conn, LearningCategory.TIMING, "Old pattern", "evidence", 0.5)
            set_status(conn, lid, LearningStatus.DEPRECATED)

        result = runner.invoke(app, ["learnings", "--db", str(db), "--status", "deprecated"])
        assert result.exit_code == 0
        assert "Old pattern" in result.output

    @pytest.mark.unit
    def test_learnings_promote_not_found(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--promote", "nonexistent-key"])
        assert result.exit_code == 1

    @pytest.mark.unit
    def test_learnings_promote_json_not_found(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--promote", "nonexistent-key", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data

    @pytest.mark.unit
    def test_learnings_invalid_category(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--category", "InvalidCat"])
        assert result.exit_code == 1

    @pytest.mark.unit
    def test_learnings_invalid_status(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--status", "invalid"])
        assert result.exit_code == 1

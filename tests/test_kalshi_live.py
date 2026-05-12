"""Live integration tests against the Kalshi V2 demo API.

These tests hit the real demo API with authenticated requests.
Run with: pytest tests/test_kalshi_live.py -v
Skip with default run: pytest tests/ -v --ignore=tests/test_kalshi_live.py
Or mark: pytest tests/ -v -m "not live"
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

# Skip entire module if no credentials configured
DEMO_API_KEY = os.environ.get("KALSHI_API_KEY", "")
DEMO_KEY_FILE = Path.home() / ".traderbot" / ".env"
pytestmark = pytest.mark.live


def _load_demo_creds() -> tuple[str, str]:
    """Load Kalshi demo credentials from ~/.traderbot/.env or env vars."""
    api_key = os.environ.get("KALSHI_API_KEY", "")
    private_key_pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")

    if not api_key and DEMO_KEY_FILE.exists():
        for line in DEMO_KEY_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("KALSHI_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("KALSHI_PRIVATE_KEY_PEM="):
                raw = line.split("=", 1)[1].strip()
                if raw.startswith('"') and raw.endswith('"'):
                    raw = raw[1:-1]
                private_key_pem = raw.replace("\\n", "\n")

    if not api_key or not private_key_pem:
        pytest.skip("Kalshi demo credentials not configured (set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PEM)")

    return api_key, private_key_pem


@pytest.fixture
def api_key() -> str:
    key, _ = _load_demo_creds()
    return key


@pytest.fixture
def private_key_pem() -> str:
    _, pem = _load_demo_creds()
    return pem


@pytest.fixture
async def client(api_key: str, private_key_pem: str):
    """Create a live KalshiClient connected to the demo API."""
    from pydantic import SecretStr

    from traderbot.kalshi.client import KalshiClient, KalshiConfig

    config = KalshiConfig(
        api_key=SecretStr(api_key),
        private_key_pem=SecretStr(private_key_pem),
        demo_mode=True,
    )
    c = KalshiClient(config=config)
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_auth_succeeds(client: KalshiClient) -> None:
    """RSA-PSS auth headers are accepted by demo API."""
    resp = await client.get("/portfolio/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert "balance" in data


@pytest.mark.asyncio
async def test_balance_in_cents(client: KalshiClient) -> None:
    """Portfolio balance is returned as int cents."""
    resp = await client.get("/portfolio/balance")
    data = resp.json()
    balance = data["balance"]
    assert isinstance(balance, int)
    assert balance > 0


@pytest.mark.asyncio
async def test_markets_list(client: KalshiClient) -> None:
    """GET /markets returns valid V2 market data."""
    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets(limit=5)
    assert len(result.markets) > 0
    m = result.markets[0]
    assert m.ticker is not None
    assert m.status in ("open", "active", "closed", "finalized", "settled")
    assert isinstance(m.volume, int)
    assert isinstance(m.open_interest, int)


@pytest.mark.asyncio
async def test_market_has_v2_price_fields(client: KalshiClient) -> None:
    """V2 markets have last_price_cents and bid/ask fields (not outcome_prices)."""
    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets(limit=10)
    open_markets = [m for m in result.markets if m.status in ("open", "active")]
    if not open_markets:
        pytest.skip("No open markets on demo API")

    for m in open_markets[:3]:
        # outcome_prices must be None (V2 does not have this field)
        assert m.outcome_prices is None, f"{m.ticker}: outcome_prices should be None in V2"

        # V2 price fields must be int cents
        if m.last_price_cents is not None:
            assert isinstance(m.last_price_cents, int)
            assert 1 <= m.last_price_cents <= 99

        if m.yes_bid_cents is not None:
            assert isinstance(m.yes_bid_cents, int)
            assert 0 <= m.yes_bid_cents <= 99

        if m.yes_ask_cents is not None:
            assert isinstance(m.yes_ask_cents, int)
            assert 1 <= m.yes_ask_cents <= 99


@pytest.mark.asyncio
async def test_market_title_not_question(client: KalshiClient) -> None:
    """V2 markets use 'title' field (validation_alias='question' for backward compat)."""
    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets(limit=5)
    for m in result.markets:
        assert m.question is not None
        assert len(m.question) > 0


@pytest.mark.asyncio
async def test_markets_volume_fp_is_int(client: KalshiClient) -> None:
    """V2 volume_fp and open_interest_fp are converted to int via _to_count."""
    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets(limit=10)
    for m in result.markets:
        assert isinstance(m.volume, int), f"{m.ticker}: volume must be int, got {type(m.volume)}"
        assert isinstance(m.open_interest, int), f"{m.ticker}: open_interest must be int, got {type(m.open_interest)}"
        # Volume and OI are contract counts (FP count), not cent amounts
        assert m.volume >= 0
        assert m.open_interest >= 0


@pytest.mark.asyncio
async def test_series_by_category(client: KalshiClient) -> None:
    """GET /series?category=Mentions returns series with correct category."""
    from traderbot.kalshi.events import EventsService
    from traderbot.kalshi.models import CATEGORY_API_NAMES

    svc = EventsService(client)
    api_name = CATEGORY_API_NAMES["mentions"]
    result = await svc.list_series(category=api_name)
    assert result is not None
    series_list = result.series if result.series else []
    assert len(series_list) > 0, "Mentions category should have series on demo API"
    for s in series_list[:3]:
        assert s.ticker is not None
        assert len(s.ticker) > 0


@pytest.mark.asyncio
async def test_events_by_series(client: KalshiClient) -> None:
    """GET /events?series_ticker=X returns events with nested markets."""
    from traderbot.kalshi.events import EventsService
    from traderbot.kalshi.models import CATEGORY_API_NAMES

    svc = EventsService(client)
    api_name = CATEGORY_API_NAMES["mentions"]
    series_result = await svc.list_series(category=api_name)
    series_list = series_result.series if series_result.series else []
    if not series_list:
        pytest.skip("No Mentions series on demo API")

    ticker = series_list[0].ticker
    result = await svc.list_events(series_ticker=ticker, with_nested_markets=True)
    assert result is not None
    events = result.events if result.events else []
    assert len(events) > 0

    event = events[0]
    assert event.ticker is not None
    assert event.category is not None
    # Events have no state/status in V2
    assert event.state is None


@pytest.mark.asyncio
async def test_markets_by_category(client: KalshiClient) -> None:
    """list_markets_by_category('mentions') returns only open/active mentions markets."""
    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets_by_category("mentions", max_series=5)
    for m in result.markets:
        assert m.status in ("open", "active"), f"{m.ticker}: expected open/active, got {m.status}"


@pytest.mark.asyncio
async def test_orderbook_v2_format(client: KalshiClient) -> None:
    """V2 orderbook uses yes_dollars/no_dollars under orderbook_fp."""
    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets(limit=10)
    open_markets = [m for m in result.markets if m.status in ("open", "active")]
    if not open_markets:
        pytest.skip("No open markets on demo API")

    ob = await svc.get_orderbook(open_markets[0].ticker)
    assert ob is not None
    assert len(ob.yes) > 0 or len(ob.no) > 0

    for level in ob.yes[:3]:
        assert isinstance(level.price, int)
        assert isinstance(level.size, int)
        assert 1 <= level.price <= 99


@pytest.mark.asyncio
async def test_portfolio_positions(client: KalshiClient) -> None:
    """GET /portfolio/positions returns V2 position data with quantity_fp/avg_price_fp."""
    from traderbot.kalshi.portfolio import PortfolioService

    svc = PortfolioService(client)
    positions = await svc.get_positions()
    # Demo account may have 0 positions — that's OK
    assert isinstance(positions, list)


@pytest.mark.asyncio
async def test_portfolio_fills(client: KalshiClient) -> None:
    """GET /portfolio/fills returns V2 fill data with yes_price_dollars/count_fp."""
    from traderbot.kalshi.portfolio import PortfolioService

    svc = PortfolioService(client)
    fills = await svc.get_fills()
    # Demo account may have 0 fills
    assert isinstance(fills, list)


@pytest.mark.asyncio
async def test_close_time_is_datetime(client: KalshiClient) -> None:
    """V2 close_time is parsed from ISO 8601 string to datetime object."""
    from datetime import datetime

    from traderbot.kalshi.markets import MarketService

    svc = MarketService(client)
    result = await svc.list_markets(limit=5)
    for m in result.markets:
        assert isinstance(m.close_time, datetime), f"{m.ticker}: close_time must be datetime, got {type(m.close_time)}"
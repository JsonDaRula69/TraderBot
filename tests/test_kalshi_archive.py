from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest

from tests.kalshi_rest_fixtures import install_transport, market_payload
from traderbot.kalshi.client import KalshiClient


@pytest.mark.asyncio
async def test_historical_cutoff_parses_official_fields_without_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "market_settled_ts": "2026-02-11T12:34:56.123456Z",
                "trades_created_ts": "2026-02-10T00:00:00Z",
                "orders_updated_ts": "2026-02-09T00:00:00Z",
                "market_positions_last_updated_ts": "2026-02-08T00:00:00Z",
            },
        )

    client = KalshiClient(api_key="unused", private_key_pem="unused")
    await install_transport(client, handler)
    try:
        with patch("traderbot.kalshi._transport.auth_headers") as signer:
            result = await client.get_historical_cutoff()
    finally:
        await client.close()

    assert result.market_settled_ts == datetime(2026, 2, 11, 12, 34, 56, 123456, tzinfo=UTC)
    assert result.market_positions_last_updated_ts == datetime(2026, 2, 8, tzinfo=UTC)
    assert requests[0].url.path.endswith("/historical/cutoff")
    signer.assert_not_called()


@pytest.mark.asyncio
async def test_historical_markets_encodes_one_selector_and_cursor_without_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [market_payload()], "cursor": "next"})

    client = KalshiClient(api_key="unused", private_key_pem="unused")
    await install_transport(client, handler)
    try:
        with patch("traderbot.kalshi._transport.auth_headers") as signer:
            result = await client.get_historical_markets(
                limit=1000,
                cursor="opaque-cursor",
                series_ticker="KXHIGHNY",
            )
    finally:
        await client.close()

    assert result.markets[0].ticker == "KXHIGHNY-26AUG11-T80"
    assert result.cursor == "next"
    assert dict(requests[0].url.params) == {
        "limit": "1000",
        "cursor": "opaque-cursor",
        "series_ticker": "KXHIGHNY",
    }
    signer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments"),
    [
        {"limit": True},
        {"limit": -1},
        {"limit": 1001},
        {"cursor": " "},
        {"series_ticker": "KX", "event_ticker": "KX-EVENT"},
        {"series_ticker": "KX", "tickers": "KX-MARKET"},
        {"mve_filter": "include"},
    ],
)
async def test_historical_markets_rejects_invalid_filters_before_transport(
    arguments: dict[str, str | int | bool],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        method = getattr(client, "get_historical_markets")
        with pytest.raises(ValueError):
            _ = await method(**arguments)
    finally:
        await client.close()

    assert requests == []


@pytest.mark.asyncio
async def test_historical_cutoff_rejects_stale_field_names() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "market_settled_timestamp": "2026-02-11T00:00:00Z",
                "trades_created_ts": "2026-02-10T00:00:00Z",
                "orders_updated_ts": "2026-02-09T00:00:00Z",
            },
        )

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        with pytest.raises(ValueError):
            _ = await client.get_historical_cutoff()
    finally:
        await client.close()

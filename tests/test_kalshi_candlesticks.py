from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from tests.kalshi_rest_fixtures import (
    historical_candle_payload,
    install_transport,
    live_candle_payload,
    market_payload,
)
from traderbot.kalshi.client import KalshiClient


@pytest.mark.asyncio
async def test_live_and_historical_candles_keep_distinct_official_shapes() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.startswith("/trade-api/v2/series/"):
            return httpx.Response(
                200,
                json={
                    "ticker": "KXHIGHNY-26AUG11-T80",
                    "candlesticks": [live_candle_payload()],
                },
            )
        return httpx.Response(
            200,
            json={
                "ticker": "KXHIGHNY-25AUG11-T80",
                "candlesticks": [historical_candle_payload()],
            },
        )

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        live = await client.get_candlesticks(
            "KXHIGHNY", "KXHIGHNY-26AUG11-T80", 1786406400, 1786492800, 60
        )
        historical = await client.get_historical_candlesticks(
            "KXHIGHNY-25AUG11-T80", 1754870400, 1754956800, 60
        )
    finally:
        await client.close()

    assert live.candlesticks[0].yes_bid.open_dollars == "0.123456"
    assert live.candlesticks[0].volume_fp == "9007199254740993.50"
    assert historical.candlesticks[0].yes_bid.open == "0.220000"
    assert historical.candlesticks[0].volume == "99999999999999999999.99"
    assert requests[0].url.path == (
        "/trade-api/v2/series/KXHIGHNY/markets/KXHIGHNY-26AUG11-T80/candlesticks"
    )
    assert requests[1].url.path == (
        "/trade-api/v2/historical/markets/KXHIGHNY-25AUG11-T80/candlesticks"
    )


@pytest.mark.asyncio
async def test_forecast_history_explodes_percentiles_and_signs_path_without_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "forecast_history": [
                    {
                        "event_ticker": "KXHIGHNY-26AUG11",
                        "end_period_ts": 1786492800,
                        "period_interval": 60,
                        "percentile_points": [
                            {
                                "percentile": 5000,
                                "raw_numerical_forecast": 80.125,
                                "numerical_forecast": 80.1,
                                "formatted_forecast": "80.1°F",
                            }
                        ],
                    }
                ]
            },
        )

    client = KalshiClient(api_key="key-id", private_key_pem="private-key")
    await install_transport(client, handler)
    headers = {
        "KALSHI-ACCESS-KEY": "key-id",
        "KALSHI-ACCESS-SIGNATURE": "signature",
        "KALSHI-ACCESS-TIMESTAMP": "1",
    }
    try:
        with patch("traderbot.kalshi._transport.auth_headers", return_value=headers) as signer:
            result = await client.get_forecast_percentile_history(
                "KXHIGHNY",
                "KXHIGHNY-26AUG11",
                1786406400,
                1786492800,
                [1000, 5000, 9000],
                60,
            )
    finally:
        await client.close()

    assert result.forecast_history[0].percentile_points[0].raw_numerical_forecast == Decimal(
        "80.125"
    )
    assert requests[0].url.params.get_list("percentiles") == ["1000", "5000", "9000"]
    signer.assert_called_once_with(
        "key-id",
        "private-key",
        "GET",
        "/trade-api/v2/series/KXHIGHNY/events/KXHIGHNY-26AUG11/forecast_percentile_history",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["", "../escape", "A/B", "A?cursor=x", "A\nB"])
async def test_path_identifiers_fail_before_transport(ticker: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ticker": ticker, "candlesticks": []})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        with pytest.raises(ValueError):
            _ = await client.get_historical_candlesticks(ticker, 1, 2, 60)
    finally:
        await client.close()

    assert requests == []


@pytest.mark.asyncio
async def test_query_validation_fails_before_transport() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        with pytest.raises(ValueError):
            _ = await client.get_markets(status="active")
        with pytest.raises(ValueError):
            _ = await client.get_markets(limit=1001)
        with pytest.raises(ValueError):
            _ = await client.get_markets(limit=True)
        with pytest.raises(ValueError):
            _ = await client.get_markets(min_created_ts=2, max_created_ts=1)
        with pytest.raises(ValueError):
            _ = await client.get_candlesticks("SER", "MARKET", 2, 1, 60)
        with pytest.raises(ValueError):
            _ = await client.get_forecast_percentile_history("SER", "EVENT", 1, 2, [5000, 5000], 60)
    finally:
        await client.close()

    assert requests == []


@pytest.mark.asyncio
async def test_misleading_success_envelope_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"markets": [], "cursor": "", "error": "denied"})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        with pytest.raises(ValidationError):
            _ = await client.get_markets(status="settled")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_malformed_fixed_point_response_returns_no_partial_results() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        market = market_payload()
        market["volume_fp"] = "not-a-fixed-point"
        return httpx.Response(200, json={"markets": [market], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        with pytest.raises(ValidationError):
            _ = await client.get_markets(status="settled")
    finally:
        await client.close()

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from tests.kalshi_rest_fixtures import install_transport, market_payload
from traderbot.kalshi.client import (
    ConfigurationError,
    KalshiAPIError,
    KalshiClient,
    RateLimitError,
)
from traderbot.kalshi.models import MarketCategory


@pytest.mark.asyncio
async def test_public_request_skips_auth_without_credentials() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        response = await client.get("/markets", status="settled")
    finally:
        await client.close()

    assert response.status_code == 200
    assert dict(requests[0].url.params) == {"status": "settled"}
    assert "KALSHI-ACCESS-KEY" not in requests[0].headers


@pytest.mark.asyncio
async def test_private_request_signs_full_api_path_without_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = KalshiClient(api_key="key-id", private_key_pem="private-key")
    await install_transport(client, handler)
    signed_headers = {
        "KALSHI-ACCESS-KEY": "key-id",
        "KALSHI-ACCESS-SIGNATURE": "signature",
        "KALSHI-ACCESS-TIMESTAMP": "1",
    }
    try:
        with patch(
            "traderbot.kalshi._transport.auth_headers", return_value=signed_headers
        ) as signer:
            response = await client.get("/portfolio/balance", cursor="next page")
    finally:
        await client.close()

    assert response.status_code == 200
    signer.assert_called_once_with(
        "key-id", "private-key", "GET", "/trade-api/v2/portfolio/balance"
    )
    assert dict(requests[0].url.params) == {"cursor": "next page"}
    assert requests[0].headers["KALSHI-ACCESS-KEY"] == "key-id"


@pytest.mark.asyncio
async def test_retry_budget_remains_bounded_for_rate_limits() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={"code": "too_many_requests"})

    client = KalshiClient(max_retries=2, retry_base_delay=0)
    await install_transport(client, handler)
    try:
        with patch("traderbot.kalshi._transport.random.uniform", return_value=0):
            with pytest.raises(RateLimitError):
                _ = await client.get("/markets")
    finally:
        await client.close()

    assert attempts == 3


@pytest.mark.asyncio
async def test_client_error_is_not_retried() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"code": "bad_request"})

    client = KalshiClient(max_retries=3)
    await install_transport(client, handler)
    try:
        with pytest.raises(KalshiAPIError):
            _ = await client.get("/markets")
    finally:
        await client.close()

    assert attempts == 1


@pytest.mark.asyncio
async def test_server_error_uses_existing_retry_budget() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"code": "unavailable"})

    client = KalshiClient(max_retries=2, retry_base_delay=0)
    await install_transport(client, handler)
    try:
        with patch("traderbot.kalshi._transport.random.uniform", return_value=0):
            with pytest.raises(KalshiAPIError):
                _ = await client.get("/markets")
    finally:
        await client.close()

    assert attempts == 3


@pytest.mark.asyncio
async def test_nonexistent_legacy_candlestick_path_is_not_public() -> None:
    client = KalshiClient()
    try:
        with pytest.raises(ConfigurationError):
            _ = await client.get("/markets/KXHIGHNY-26AUG11-T80/candlesticks")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_series_uses_lowercase_category_and_typed_envelope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "series": [
                    {
                        "ticker": "KXHIGHNY",
                        "frequency": "daily",
                        "title": "NYC daily high temperature",
                        "category": "Weather",
                        "tags": ["temperature"],
                        "settlement_sources": [{"name": "NWS", "url": "https://weather.gov"}],
                        "contract_url": "https://kalshi.com/contracts/KXHIGHNY",
                        "contract_terms_url": "https://kalshi.com/terms/KXHIGHNY",
                        "fee_type": "quadratic",
                        "fee_multiplier": 1.0,
                        "additional_prohibitions": [],
                        "harmless_future_field": "accepted",
                    }
                ]
            },
        )

    client = KalshiClient(api_key="unused", private_key_pem="unused")
    await install_transport(client, handler)
    try:
        with patch("traderbot.kalshi._transport.auth_headers") as signer:
            result = await client.get_series(MarketCategory.WEATHER)
    finally:
        await client.close()

    assert result.series[0].ticker == "KXHIGHNY"
    assert dict(requests[0].url.params) == {"category": "weather"}
    signer.assert_not_called()


@pytest.mark.asyncio
async def test_get_markets_encodes_cursor_filters_and_preserves_fixed_points() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [market_payload()], "cursor": "next-cursor"})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        result = await client.get_markets(
            status="settled",
            limit=250,
            cursor="cursor one",
            event_ticker="KXHIGHNY-26AUG11",
            series_ticker="KXHIGHNY",
            min_settled_ts=1786406400,
            max_settled_ts=1786492800,
        )
    finally:
        await client.close()

    assert result.cursor == "next-cursor"
    assert result.markets[0].volume_fp == "12345678901234567890.25"
    assert result.markets[0].open_interest_fp == "9007199254740993.50"
    assert len(requests) == 1
    assert dict(requests[0].url.params) == {
        "status": "settled",
        "limit": "250",
        "cursor": "cursor one",
        "event_ticker": "KXHIGHNY-26AUG11",
        "series_ticker": "KXHIGHNY",
        "min_settled_ts": "1786406400",
        "max_settled_ts": "1786492800",
    }


@pytest.mark.asyncio
async def test_get_markets_omits_none_cursor() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        result = await client.get_markets(cursor=None)
    finally:
        await client.close()

    assert result.cursor == ""
    assert len(requests) == 1
    assert "cursor" not in requests[0].url.params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [object(), 7, True, "", " ", "\t", "\n", " leading", "trailing ", "opaque\x00cursor"],
    ids=[
        "object",
        "integer",
        "boolean",
        "empty",
        "space-only",
        "tab-only",
        "newline-only",
        "leading-space",
        "trailing-space",
        "embedded-control",
    ],
)
async def test_get_markets_rejects_invalid_cursor_before_transport(
    cursor: str | int | bool,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        get_markets = getattr(client, "get_markets")
        with pytest.raises(ValueError):
            _ = await get_markets(cursor=cursor)
    finally:
        await client.close()

    assert requests == []


@pytest.mark.asyncio
async def test_get_markets_preserves_opaque_cursor_exactly() -> None:
    requests: list[httpx.Request] = []
    opaque_cursor = "AbC_09-.~eyJwYWdlIjoyfQ"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = KalshiClient()
    await install_transport(client, handler)
    try:
        result = await client.get_markets(cursor=opaque_cursor)
    finally:
        await client.close()

    assert result.cursor == ""
    assert len(requests) == 1
    assert requests[0].url.params["cursor"] == opaque_cursor

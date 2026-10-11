from __future__ import annotations

from collections.abc import Callable

import httpx

from traderbot.kalshi.client import KalshiClient

type Handler = Callable[[httpx.Request], httpx.Response]


async def install_transport(client: KalshiClient, handler: Handler) -> None:
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://external-api.kalshi.com/trade-api/v2",
        transport=httpx.MockTransport(handler),
    )


def market_payload() -> dict[str, str | int | bool | list[dict[str, str]]]:
    return {
        "ticker": "KXHIGHNY-26AUG11-T80",
        "event_ticker": "KXHIGHNY-26AUG11",
        "market_type": "binary",
        "yes_sub_title": "80° or above",
        "no_sub_title": "Below 80°",
        "created_time": "2026-08-01T00:00:00Z",
        "updated_time": "2026-08-10T12:00:00Z",
        "open_time": "2026-08-01T00:00:00Z",
        "close_time": "2026-08-11T23:59:00Z",
        "latest_expiration_time": "2026-08-12T12:00:00Z",
        "settlement_timer_seconds": 3600,
        "status": "finalized",
        "notional_value_dollars": "1.000000",
        "yes_bid_dollars": "0.123456",
        "yes_ask_dollars": "0.130000",
        "no_bid_dollars": "0.870000",
        "no_ask_dollars": "0.876544",
        "yes_bid_size_fp": "10.00",
        "yes_ask_size_fp": "11.00",
        "last_price_dollars": "0.125000",
        "previous_yes_bid_dollars": "0.100000",
        "previous_yes_ask_dollars": "0.110000",
        "previous_price_dollars": "0.105000",
        "volume_fp": "12345678901234567890.25",
        "volume_24h_fp": "25.50",
        "open_interest_fp": "9007199254740993.50",
        "result": "yes",
        "can_close_early": False,
        "expiration_value": "80.4",
        "rules_primary": "Official station reading.",
        "rules_secondary": "Kalshi rules apply.",
        "price_level_structure": "deci_cent",
        "price_ranges": [{"start": "0.000000", "end": "1.000000", "step": "0.001000"}],
    }


def live_candle_payload() -> dict[str, int | str | dict[str, str | None]]:
    return {
        "end_period_ts": 1786492800,
        "yes_bid": {
            "open_dollars": "0.123456",
            "low_dollars": "0.120000",
            "high_dollars": "0.130000",
            "close_dollars": "0.125000",
        },
        "yes_ask": {
            "open_dollars": "0.133456",
            "low_dollars": "0.130000",
            "high_dollars": "0.140000",
            "close_dollars": "0.135000",
        },
        "price": {
            "open_dollars": "0.124000",
            "low_dollars": "0.121000",
            "high_dollars": "0.131000",
            "close_dollars": "0.126000",
            "mean_dollars": "0.125500",
            "previous_dollars": None,
            "min_dollars": "0.121000",
            "max_dollars": "0.131000",
        },
        "volume_fp": "9007199254740993.50",
        "open_interest_fp": "12345678901234567890.25",
    }


def historical_candle_payload() -> dict[str, int | str | dict[str, str | None]]:
    return {
        "end_period_ts": 1754956800,
        "yes_bid": {
            "open": "0.220000",
            "low": "0.210000",
            "high": "0.230000",
            "close": "0.225000",
        },
        "yes_ask": {
            "open": "0.240000",
            "low": "0.230000",
            "high": "0.250000",
            "close": "0.245000",
        },
        "price": {
            "open": "0.230000",
            "low": "0.220000",
            "high": "0.240000",
            "close": "0.235000",
            "mean": "0.232500",
            "previous": None,
        },
        "volume": "99999999999999999999.99",
        "open_interest": "88888888888888888888.88",
    }

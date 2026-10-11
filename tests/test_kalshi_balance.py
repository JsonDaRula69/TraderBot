from __future__ import annotations

from typing import final, override

import httpx
import pytest

from traderbot.kalshi.client import KalshiClient


@final
class MockKalshiClient(KalshiClient):
    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        super().__init__(api_key="key", private_key_pem="pem", max_retries=0)
        self._transport = transport

    async def start(self) -> None:
        await self._client.aclose()
        self._client = httpx.AsyncClient(
            base_url="https://example.test/trade-api/v2", transport=self._transport
        )

    @override
    def _build_auth_headers(self, method: str, path: str) -> dict[str, str]:
        _ = method, path
        return {
            "KALSHI-ACCESS-KEY": "key",
            "KALSHI-ACCESS-SIGNATURE": "signature",
            "KALSHI-ACCESS-TIMESTAMP": "1",
        }


@pytest.mark.asyncio
async def test_balance_uses_signed_private_endpoint() -> None:
    # Given
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            json={
                "balance": 123,
                "balance_dollars": "1.230000",
                "portfolio_value": 456,
                "updated_ts": 1_786_406_400,
            },
        )

    client = MockKalshiClient(httpx.MockTransport(handler))
    await client.start()

    # When
    result = await client.get_balance(timeout=0.5)
    await client.close()

    # Then
    assert result.balance_dollars == "1.230000"
    assert observed[0].url.path == "/trade-api/v2/portfolio/balance"
    assert observed[0].headers["KALSHI-ACCESS-SIGNATURE"] == "signature"

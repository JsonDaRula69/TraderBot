"""Live Kalshi authentication integration tests.

Verifies that real credentials can authenticate with the Kalshi V2 API,
and that invalid credentials are correctly rejected.
"""

from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

from traderbot.kalshi.client import AuthenticationError, KalshiClient, KalshiConfig

pytestmark = pytest.mark.integration


@pytest.mark.live
async def test_client_authenticates(live_client: KalshiClient) -> None:
    response = await live_client.get("/markets", limit=1, status="open")
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}: {response.text[:200]}"
    )
    data = response.json()
    assert "markets" in data, f"Response missing 'markets' key: {list(data.keys())}"


@pytest.mark.live
async def test_auth_failure_with_bad_key(temp_traderbot_env) -> None:  # noqa: ARG001
    bad_config = KalshiConfig(
        api_key=SecretStr("00000000-0000-0000-0000-000000000000"),
        private_key_pem=SecretStr(os.environ["KALSHI_PRIVATE_KEY_PEM"]),
    )
    async with KalshiClient(config=bad_config) as client:
        with pytest.raises(AuthenticationError, match="Auth failure"):
            await client.get("/markets", limit=1)
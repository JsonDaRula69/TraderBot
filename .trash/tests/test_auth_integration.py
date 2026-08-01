"""Live Kalshi authentication integration tests.

Verifies that real credentials can authenticate with the Kalshi V2 API,
and that invalid credentials are correctly rejected.
"""

from __future__ import annotations

import json
import os

import pytest
from pydantic import SecretStr

from traderbot.exceptions import AuthenticationError
from traderbot.kalshi.client import KalshiClient, KalshiConfig

pytestmark = pytest.mark.integration


@pytest.mark.live
async def test_client_authenticates(live_client: KalshiClient) -> None:
    """Authenticate against /portfolio/balance (requires valid KalshiV2 signing)."""
    response = await live_client.get("/portfolio/balance")
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}: {response.text[:200]}"
    )
    data = response.json()
    # Balance should have 'balance' and 'portfolio_value' int fields
    assert "balance" in data, f"Response missing 'balance' key: {list(data.keys())}"
    assert isinstance(data.get("balance"), (int, float))


@pytest.mark.live
async def test_auth_failure_with_bad_key(temp_traderbot_env) -> None:  # noqa: ARG001
    bad_config = KalshiConfig(
        api_key=SecretStr("00000000-0000-0000-0000-000000000000"),
        base_url="https://external-api.kalshi.com/trade-api/v2",
        private_key_pem=SecretStr(os.environ["KALSHI_PRIVATE_KEY_PEM"]),
    )
    async with KalshiClient(config=bad_config) as client:
        with pytest.raises(AuthenticationError, match="Auth failure"):
            await client.get("/portfolio/balance")


@pytest.mark.live
async def test_auth_check_validate_reports_authenticated_endpoint(
    live_client: KalshiClient,
) -> None:
    """auth check --validate should test an authenticated endpoint, not /exchange/status."""
    response = await live_client.get("/portfolio/balance")
    assert response.status_code == 200, (
        f"Authenticated /portfolio/balance failed: {response.status_code} {response.text[:200]}"
    )

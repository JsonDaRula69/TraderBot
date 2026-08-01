"""Live Kalshi settlement integration tests.

Verifies SettlementVerifier does not crash on startup with real API data
and a mock PaperTrader.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.provider import ProdDataProvider
from traderbot.simulation.settlement import SettlementVerifier

pytestmark = pytest.mark.integration


@pytest.mark.live
async def test_startup_check_does_not_crash(
    live_client: KalshiClient,
    live_provider: ProdDataProvider,
) -> None:
    """SettlementVerifier.check_settlements_on_startup should not crash with a mock PaperTrader."""
    mock_trader = MagicMock()
    mock_trader.get_positions.return_value = []  # No open positions

    verifier = SettlementVerifier(
        provider=live_provider,
        paper_trader=mock_trader,
    )

    # Should complete without error (no open positions = no API calls)
    await verifier.check_settlements_on_startup()

    mock_trader.get_positions.assert_called_once()
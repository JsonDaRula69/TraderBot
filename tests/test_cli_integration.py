"""Integration tests for CLI paper command imports and help output."""

from __future__ import annotations

import subprocess

from tests.conftest import strip_ansi

import pytest

pytestmark = pytest.mark.integration


def test_cli_paper_imports() -> None:
    from traderbot.cli import app
    from traderbot.kalshi.cache import MarketDataCache
    from traderbot.kalshi.provider import ProdDataProvider
    from traderbot.simulation.paper_trader import DEFAULT_INITIAL_BALANCE_CENTS, PaperTrader
    from traderbot.simulation.settlement import SettlementVerifier

    assert app is not None
    assert ProdDataProvider is not None
    assert MarketDataCache is not None
    assert SettlementVerifier is not None
    assert PaperTrader is not None
    assert DEFAULT_INITIAL_BALANCE_CENTS == 10_000


def test_cli_paper_help_shows_flags() -> None:
    result = subprocess.run(
        ["uv", "run", "traderbot", "paper", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"CLI --help failed: {result.stderr}"
    assert "--initial-balance" in strip_ansi(result.stdout)
    assert "--reconcile" in strip_ansi(result.stdout)

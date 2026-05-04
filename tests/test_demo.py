"""Tests for the Kalshi demo adapter module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from traderbot.kalshi.demo import DemoAdapter
from traderbot.kalshi.history import HistoryService
from traderbot.kalshi.markets import MarketService


def _mock_demo_config() -> MagicMock:
    cfg = MagicMock()
    cfg.demo_mode = True
    cfg.demo_url = "https://demo-api.kalshi.co/trade-api/v2"
    cfg.active_url = "https://demo-api.kalshi.co/trade-api/v2"
    return cfg


def _mock_demo_client(config: MagicMock) -> MagicMock:
    client = MagicMock()
    client._config = config
    client._client = MagicMock()  # httpx.AsyncClient mock
    return client


class TestDemoAdapterConfig:
    def test_default_config_is_demo_mode(self) -> None:
        mock_config = _mock_demo_config()
        mock_client = _mock_demo_client(mock_config)

        with (
            patch("traderbot.kalshi.client.KalshiConfig", return_value=mock_config),
            patch("traderbot.kalshi.client.KalshiClient", return_value=mock_client),
        ):
            adapter = DemoAdapter()

        assert adapter.is_demo is True

    def test_forces_demo_mode_when_config_has_demo_false(self) -> None:
        from pydantic import SecretStr

        from traderbot.kalshi.client import KalshiConfig

        prod_config = KalshiConfig(
            api_key=SecretStr("key"),
            api_secret="secret",
            demo_mode=False,
        )

        with patch("traderbot.kalshi.client.KalshiClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            adapter = DemoAdapter(config=prod_config)

        assert adapter.is_demo is True

    def test_none_config_creates_demo(self) -> None:
        mock_config = _mock_demo_config()
        mock_client = _mock_demo_client(mock_config)

        with (
            patch("traderbot.kalshi.client.KalshiConfig", return_value=mock_config),
            patch("traderbot.kalshi.client.KalshiClient", return_value=mock_client),
        ):
            adapter = DemoAdapter()

        assert adapter.is_demo is True


class TestDemoAdapterProperties:
    def _make_adapter(self) -> DemoAdapter:
        mock_config = _mock_demo_config()
        mock_client = _mock_demo_client(mock_config)

        with (
            patch("traderbot.kalshi.client.KalshiConfig", return_value=mock_config),
            patch("traderbot.kalshi.client.KalshiClient", return_value=mock_client),
        ):
            return DemoAdapter()

    def test_is_demo_always_true(self) -> None:
        adapter = self._make_adapter()
        assert adapter.is_demo is True

    def test_base_url_is_demo_url(self) -> None:
        adapter = self._make_adapter()
        assert adapter.base_url == "https://demo-api.kalshi.co/trade-api/v2"

    def test_base_url_not_production(self) -> None:
        adapter = self._make_adapter()
        assert "demo-api" in adapter.base_url

    def test_accepts_config_with_demo_mode_true(self) -> None:
        demo_config = _mock_demo_config()
        mock_client = _mock_demo_client(demo_config)

        config = MagicMock()
        config.demo_mode = True

        with (
            patch("traderbot.kalshi.demo.KalshiConfig", return_value=demo_config),
            patch("traderbot.kalshi.demo.KalshiClient", return_value=mock_client),
        ):
            adapter = DemoAdapter(config=config)

        assert adapter.is_demo is True

    def test_client_property_returns_kalshi_client(self) -> None:
        adapter = self._make_adapter()
        assert adapter.client is not None


class TestDemoAdapterServices:
    def _make_adapter_with_client(self) -> tuple[DemoAdapter, MagicMock]:
        mock_config = _mock_demo_config()
        mock_client = _mock_demo_client(mock_config)

        with (
            patch("traderbot.kalshi.client.KalshiConfig", return_value=mock_config),
            patch("traderbot.kalshi.client.KalshiClient", return_value=mock_client),
        ):
            return DemoAdapter(), mock_client

    def test_get_market_service_has_market_methods(self) -> None:
        adapter, _ = self._make_adapter_with_client()
        service = adapter.get_market_service()
        assert hasattr(service, "list_markets")
        assert hasattr(service, "get_orderbook")

    def test_get_history_service_has_history_methods(self) -> None:
        adapter, _ = self._make_adapter_with_client()
        service = adapter.get_history_service()
        assert hasattr(service, "get_cutoffs")
        assert hasattr(service, "get_historical_trades")

    def test_market_service_uses_demo_client(self) -> None:
        adapter, _mock_client = self._make_adapter_with_client()
        service = adapter.get_market_service()
        assert isinstance(service, MarketService)

    def test_history_service_uses_demo_client(self) -> None:
        adapter, _mock_client = self._make_adapter_with_client()
        service = adapter.get_history_service()
        assert isinstance(service, HistoryService)

"""Demo adapter that ensures all services target the Kalshi demo API endpoint."""

from __future__ import annotations

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.history import HistoryService
from traderbot.kalshi.markets import MarketService


class DemoAdapter:
    """Factory that produces services configured against the Kalshi demo API."""

    def __init__(self, config: KalshiConfig | None = None) -> None:
        if config is not None:
            if not config.demo_mode:
                override = config.model_dump()
                override["demo_mode"] = True
                self._config = self._rebuild_config(override)
            else:
                self._config = config
        else:
            self._config = KalshiConfig(
                api_key="demo",
                api_secret="demo",
                demo_mode=True,
            )

        self._client = KalshiClient(self._config)

    @staticmethod
    def _rebuild_config(override: dict) -> KalshiConfig:
        return KalshiConfig(**override)

    @property
    def is_demo(self) -> bool:
        return True

    @property
    def base_url(self) -> str:
        return self._config.demo_url

    @property
    def client(self) -> KalshiClient:
        return self._client

    def get_market_service(self) -> MarketService:
        return MarketService(self._client)

    def get_history_service(self) -> HistoryService:
        return HistoryService(self._client)

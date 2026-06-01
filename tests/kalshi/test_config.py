from __future__ import annotations

import os
from pathlib import Path

import pytest

from traderbot.kalshi.config import EnvKalshiConfig

_HAS_KALSHI_CREDS = bool(
    os.environ.get("KALSHI_API_KEY")
    or (Path.home() / ".traderbot" / ".env").exists()
)


class TestEnvKalshiConfig:
    def test_defaults(self) -> None:
        config = EnvKalshiConfig()
        assert config.base_url == "https://api.elections.kalshi.com/trade-api/v2"
        assert config.rate_limit_rps == 20.0
        assert config.max_retries == 3
        assert config.retry_base_delay == 1.0

    @pytest.mark.skipif(_HAS_KALSHI_CREDS, reason="KALSHI_API_KEY set in env")
    def test_api_key_none_when_not_configured(self) -> None:
        config = EnvKalshiConfig()
        assert config.api_key is None
        assert config.private_key_pem is None
        assert config.resolve_api_key() is None
        assert config.resolve_private_key() is None

    @pytest.mark.skipif(
        not os.environ.get("KALSHI_API_KEY"),
        reason="KALSHI_API_KEY not set",
    )
    def test_loads_api_key_from_env(self) -> None:
        config = EnvKalshiConfig()
        api_key = config.resolve_api_key()
        assert api_key is not None
        assert len(api_key) > 0

    def test_rate_limit_validation(self) -> None:
        config = EnvKalshiConfig(rate_limit_rps=-1)
        assert config.rate_limit_rps == 20.0
        config = EnvKalshiConfig(rate_limit_rps=0)
        assert config.rate_limit_rps == 20.0

    def test_resolve_api_key_from_init(self) -> None:
        config = EnvKalshiConfig(api_key="test-key-123")
        assert config.resolve_api_key() == "test-key-123"

    def test_extra_fields_ignored(self) -> None:
        config = EnvKalshiConfig(unknown_field="x")  # type: ignore[call-arg]
        assert not hasattr(config, "unknown_field")

    @pytest.mark.live
    def test_loads_from_env_when_configured(self) -> None:
        config = EnvKalshiConfig()
        api_key = config.resolve_api_key()
        assert api_key is not None

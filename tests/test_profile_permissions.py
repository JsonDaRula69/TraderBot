"""Unit tests for TradingProfile permissions, backtest mode, and is_tool_permitted()."""

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.dev_liaison import create_dev_liaison_profile
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.sysadmin import create_sysadmin_profile


def _make_profile(name: str = "test", mode: str = "paper", permissions: list[str] | None = None, **kwargs) -> TradingProfile:
    defaults = dict(
        description="test profile",
        enabled_categories=[],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.1,
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.1,
        max_open_positions=10,
        min_liquidity_threshold=100,
        min_edge_pct=5.0,
    )
    defaults.update(kwargs)
    return TradingProfile(name=name, mode=mode, permissions=permissions or [], **defaults)


class TestBacktestMode:
    def test_backtest_mode_accepted(self):
        p = _make_profile(mode="backtest")
        assert p.mode == "backtest"
        assert p.paper_mode is False

    def test_paper_mode_accepted(self):
        p = _make_profile(mode="paper")
        assert p.mode == "paper"
        assert p.paper_mode is True

    def test_live_mode_accepted(self):
        p = _make_profile(mode="live")
        assert p.mode == "live"

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            _make_profile(mode="invalid")


class TestPermissions:
    def test_empty_permissions_allows_all(self):
        p = _make_profile(permissions=[])
        assert p.is_tool_permitted("traderbot__trade") is True
        assert p.is_tool_permitted("traderbot__health") is True
        assert p.is_tool_permitted("traderbot__anything") is True

    def test_deny_rule_blocks_tool(self):
        p = _make_profile(permissions=["deny:traderbot__trade"])
        assert p.is_tool_permitted("traderbot__trade") is False
        assert p.is_tool_permitted("traderbot__health") is True

    def test_deny_wildcard_blocks_all_traderbot_tools(self):
        p = _make_profile(permissions=["deny:traderbot__*"])
        assert p.is_tool_permitted("traderbot__trade") is False
        assert p.is_tool_permitted("traderbot__health") is False
        assert p.is_tool_permitted("traderbot__weather_forecast") is False

    def test_deny_weather_wildcard(self):
        p = _make_profile(permissions=["deny:traderbot__weather_*"])
        assert p.is_tool_permitted("traderbot__weather_forecast") is False
        assert p.is_tool_permitted("traderbot__health") is True

    def test_allow_list_only_permits_listed(self):
        p = _make_profile(permissions=["traderbot__health", "traderbot__auth_check"])
        assert p.is_tool_permitted("traderbot__health") is True
        assert p.is_tool_permitted("traderbot__auth_check") is True
        assert p.is_tool_permitted("traderbot__trade") is False

    def test_allow_wildcard_permits_all_traderbot(self):
        p = _make_profile(permissions=["traderbot__*"])
        assert p.is_tool_permitted("traderbot__trade") is True
        assert p.is_tool_permitted("traderbot__health") is True

    def test_deny_takes_precedence_over_allow(self):
        p = _make_profile(permissions=["traderbot__*", "deny:traderbot__trade"])
        assert p.is_tool_permitted("traderbot__trade") is False
        assert p.is_tool_permitted("traderbot__health") is True

    def test_deny_only_mode_permits_unlisted(self):
        p = _make_profile(permissions=["deny:traderbot__trade"])
        assert p.is_tool_permitted("traderbot__health") is True
        assert p.is_tool_permitted("traderbot__anything") is True


class TestSysAdminProfile:
    def test_sysadmin_cannot_trade(self):
        p = create_sysadmin_profile()
        assert p.is_tool_permitted("traderbot__trade") is False
        assert p.is_tool_permitted("traderbot__scan") is False
        assert p.is_tool_permitted("traderbot__analyze") is False
        assert p.is_tool_permitted("traderbot__market_edge") is False
        assert p.is_tool_permitted("traderbot__market_prices") is False

    def test_sysadmin_cannot_use_weather(self):
        p = create_sysadmin_profile()
        assert p.is_tool_permitted("traderbot__weather_forecast_prob") is False

    def test_sysadmin_can_use_health_and_reference(self):
        p = create_sysadmin_profile()
        assert p.is_tool_permitted("traderbot__health") is True
        assert p.is_tool_permitted("traderbot__auth_check") is True
        assert p.is_tool_permitted("traderbot__profile_list") is True

    def test_sysadmin_mode_is_paper(self):
        p = create_sysadmin_profile()
        assert p.mode == "paper"
        assert p.paper_mode is True


class TestDevLiaisonProfile:
    def test_dev_liaison_cannot_trade(self):
        p = create_dev_liaison_profile()
        assert p.is_tool_permitted("traderbot__trade") is False

    def test_dev_liaison_can_use_allowed_tools(self):
        p = create_dev_liaison_profile()
        assert p.is_tool_permitted("traderbot__reference") is True
        assert p.is_tool_permitted("traderbot__health") is True
        assert p.is_tool_permitted("traderbot__auth_check") is True
        assert p.is_tool_permitted("traderbot__profile_list") is True

    def test_dev_liaison_cannot_use_denied_tools(self):
        p = create_dev_liaison_profile()
        assert p.is_tool_permitted("traderbot__scan") is False
        assert p.is_tool_permitted("traderbot__analyze") is False
        assert p.is_tool_permitted("traderbot__market_edge") is False

    def test_dev_liaison_mode_is_paper(self):
        p = create_dev_liaison_profile()
        assert p.mode == "paper"

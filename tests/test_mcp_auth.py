import pytest

from traderbot.mcp.auth import check_category_access
from traderbot.mcp.tools import _check_permissions
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.profiles.weather import create_weather_profile


def test_category_allowed() -> None:
    result = check_category_access(
        create_weather_profile(), "weather-agent", "weather", "traderbot__market_edge"
    )

    assert result is None


def test_category_denied() -> None:
    result = check_category_access(
        create_weather_profile(), "weather-agent", "economics", "traderbot__market_edge"
    )

    assert result == {"error": "Category 'economics' not enabled for agent 'weather-agent'"}


def test_invalid_category_string() -> None:
    result = check_category_access(
        create_weather_profile(), "weather-agent", "bogus", "traderbot__market_edge"
    )

    assert result == {"error": "Unknown category: bogus"}


def test_category_none_allowed() -> None:
    result = check_category_access(
        create_weather_profile(), "weather-agent", None, "traderbot__health"
    )

    assert result is None


def test_sysadmin_all_categories() -> None:
    profile = create_sysadmin_profile().model_copy(update={"enabled_categories": []})

    assert check_category_access(profile, "sysadmin", "economics", "traderbot__audit") is None


def test_check_permissions_category_denied_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADERBOT_USE_HARDCODED_AUTH", raising=False)

    profile, agent_id, error = _check_permissions(
        "weather-test-token", "market_edge", category="economics"
    )

    assert profile is not None
    assert agent_id == "weather"
    assert error == {"error": "Category 'economics' not enabled for agent 'weather'"}

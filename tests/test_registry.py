import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles import ProfileRegistry
from traderbot.profiles.models import TradingProfile


def test_get_profile_returns_profile() -> None:
    profile = ProfileRegistry().get_profile("sysadmin")

    assert isinstance(profile, TradingProfile)
    assert profile.name == "sysadmin"


@pytest.mark.parametrize("profile_name", ["sysadmin", "dev-liaison", "weather"])
def test_get_profile_each_factory(profile_name: str) -> None:
    profile = ProfileRegistry().get_profile(profile_name)

    assert isinstance(profile, TradingProfile)
    assert profile.name == profile_name


def test_get_profile_unknown_returns_none() -> None:
    assert ProfileRegistry().get_profile("unknown") is None


def test_list_profiles_correctness() -> None:
    profiles = ProfileRegistry().list_profiles()

    assert set(profiles) == {"sysadmin", "dev-liaison", "weather"}
    assert all(
        set(summary) == {"mode", "categories", "permissions"} for summary in profiles.values()
    )
    assert all(summary["mode"] == "paper" for summary in profiles.values())
    assert profiles["sysadmin"]["categories"] == [category.value for category in MarketCategory]
    assert profiles["dev-liaison"]["categories"] == ["all"]
    assert profiles["weather"]["categories"] == ["weather"]
    assert "traderbot__weather_forecast_prob" in profiles["weather"]["permissions"]

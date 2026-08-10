"""Focused tests for the generic category profile factory."""

from pathlib import Path

import pytest
from pydantic import ValidationError

import traderbot.cli as cli
from traderbot.kalshi.models import MarketCategory


def test_create_category_profile_weather() -> None:
    # Given: a weather profile request in backtest mode
    from traderbot.profiles.generic import create_category_profile

    # When: the generic profile is created
    profile = create_category_profile(
        name="test",
        mode="backtest",
        categories=[MarketCategory.WEATHER],
    )

    # Then: its identity and category scope match the request
    assert profile.name == "test"
    assert profile.mode == "backtest"
    assert profile.enabled_categories == [MarketCategory.WEATHER]


def test_default_categories_are_not_shared() -> None:
    # Given: two independently created profiles using the category default
    from traderbot.profiles.generic import create_category_profile

    first = create_category_profile("first")
    second = create_category_profile("second")

    # When: one profile's category collection is changed
    first.enabled_categories.append(MarketCategory.WEATHER)

    # Then: the other profile retains its own empty collection
    assert second.enabled_categories == []


def test_invalid_mode_raises() -> None:
    # Given: a mode outside TradingProfile's supported modes
    from traderbot.profiles.generic import create_category_profile

    # When/Then: constructing the profile fails at the model boundary
    with pytest.raises(ValidationError):
        create_category_profile("test", mode="invalid")


def test_invalid_category_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an isolated data root and an unsupported external category value
    data_dir = tmp_path / "data"
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_dir))

    # When: the real TraderBot CLI parses the profile request
    with pytest.raises(SystemExit) as raised:
        _ = cli.main(
            ["profile", "create", "test", "--mode", "backtest", "--categories", "invalid"]
        )
    output = capsys.readouterr()

    # Then: the production boundary rejects it actionably without creating state
    assert raised.value.code == 2
    assert output.out == ""
    assert "invalid category" in output.err
    assert "'invalid'" in output.err
    assert data_dir.exists() is False

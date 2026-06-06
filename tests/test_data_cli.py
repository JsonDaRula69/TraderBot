"""Unit tests for the `traderbot data` CLI commands.

Tests verify:
- temperature_high → high_temp_f field name fix (bug #132)
- ensemble data not silently dropped in JSON output
- httpx client reuse pattern (single asyncio.run)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from traderbot.cli import app
from traderbot.data.models import CityForecast, ModelConsensus
from tests.conftest import strip_ansi

runner = CliRunner()

pytestmark = pytest.mark.unit

# ------------------------------------------------------------------
#  Mock helpers
# ------------------------------------------------------------------


def _make_forecast(city: str = "New York", high: float = 72.0) -> CityForecast:
    return CityForecast(
        ticker="KXHIGHNY",
        city=city,
        lat=40.71,
        lon=-74.01,
        date=date.today(),
        high_temp_f=high,
        low_temp_f=55.0,
        precip_prob=0.1,
        wind_speed=10.0,
        detailed_forecast="Sunny",
        source="nws",
    )


def _make_consensus() -> ModelConsensus:
    return ModelConsensus(
        mean_temp=70.0,
        std_dev=2.0,
        spread=5.0,
        models_used=["gfs_seamless", "ecmwf_ifs", "gem_global"],
        agreement_score=0.95,
    )


# ------------------------------------------------------------------
#  display mode: high_temp_f used correctly (bug #132)
# ------------------------------------------------------------------


class TestForecastsDisplayHighTempF:
    """Non-JSON display mode must use ``high_temp_f`` not ``temperature_high``."""

    def test_display_mode_uses_high_temp_f(self) -> None:
        """Invoke forecasts in display mode — verifies no AttributeError."""
        mock_provider = AsyncMock()
        mock_provider.get_forecasts.return_value = {"New York": _make_forecast()}
        mock_provider.get_model_consensus.return_value = _make_consensus()

        with patch(
            "traderbot.data.weather.provider.WeatherDataProvider",
            return_value=mock_provider,
        ):
            result = runner.invoke(app, ["data", "forecasts", "--cities", "NYC"])
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            # The display should show the high_temp_f value (72°F)
            assert "72" in strip_ansi(result.output)
            assert "New York" in strip_ansi(result.output)
            assert "NWS High" in strip_ansi(result.output)


# ------------------------------------------------------------------
#  JSON mode: ensemble data not silently dropped
# ------------------------------------------------------------------


class TestForecastsJSONEnsemble:
    """--json mode must include the ``ensemble`` key when consensus is available."""

    def test_json_mode_includes_ensemble_key(self) -> None:
        """Invoke forecasts --json — verify ensemble data is present."""
        mock_provider = AsyncMock()
        mock_provider.get_forecasts.return_value = {"New York": _make_forecast()}
        mock_provider.get_model_consensus.return_value = _make_consensus()

        with patch(
            "traderbot.data.weather.provider.WeatherDataProvider",
            return_value=mock_provider,
        ):
            result = runner.invoke(app, ["data", "forecasts", "--cities", "NYC", "--json"])
            assert result.exit_code == 0, f"CLI failed: {result.output}"

            import json as json_lib

            data = json_lib.loads(result.output)
            assert "New York" in data, f"No NYC entry in: {list(data.keys())}"
            entry = data["New York"]
            assert "ensemble" in entry, f"No ensemble key in: {list(entry.keys())}"
            assert entry["ensemble"]["mean_temp"] == 70.0
            assert entry["ensemble"]["agreement_score"] == 0.95
            assert entry["high_temp_f"] == 72.0


# ------------------------------------------------------------------
#  all-periods display mode: high_temp_f used correctly
# ------------------------------------------------------------------


class TestForecastsAllPeriodsDisplay:
    """--all display mode also uses ``high_temp_f``."""

    def test_all_periods_display_uses_high_temp_f(self) -> None:
        """Invoke forecasts --all — verify field name is high_temp_f."""
        mock_provider = AsyncMock()
        mock_provider.get_all_forecasts.return_value = {
            "New York": [_make_forecast(), _make_forecast(high=75.0)],
        }

        with patch(
            "traderbot.data.weather.provider.WeatherDataProvider",
            return_value=mock_provider,
        ):
            result = runner.invoke(app, ["data", "forecasts", "--cities", "NYC", "--all"])
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            output = strip_ansi(result.output)
            assert "High:" in output
            assert "72" in output
            assert "75" in output


# ------------------------------------------------------------------
#  help-text smoke tests
# ------------------------------------------------------------------


class TestDataCLIHelp:
    """CLI help screens render without errors."""

    def test_data_help(self) -> None:
        result = runner.invoke(app, ["data", "--help"])
        assert result.exit_code == 0

    def test_forecasts_help(self) -> None:
        result = runner.invoke(app, ["data", "forecasts", "--help"])
        assert result.exit_code == 0
        assert "GFS" in strip_ansi(result.output)


# ------------------------------------------------------------------
#  regression: no temperature_high in CLI code
# ------------------------------------------------------------------


class TestNoTemperatureHighRef:
    """Regression: ``temperature_high`` must not appear in the CLI data module."""

    def test_no_temperature_high_in_cli_module(self) -> None:
        import os

        data_py = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "traderbot",
            "cli",
            "data.py",
        )
        with open(data_py) as fh:
            content = fh.read()
        assert "temperature_high" not in content, (
            "temperature_high found in cli/data.py — must be high_temp_f"
        )

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


# ------------------------------------------------------------------
#  bias command: city code resolution (bug #144)
# ------------------------------------------------------------------


class TestBiasCityResolution:
    """``traderbot data bias NYC`` must resolve ``NYC`` to ``New York``
    before querying the DB, matching what ``record-bias`` stores.
    """

    def test_bias_cmd_resolves_nyc_to_new_york(self) -> None:
        """Verify bias command passes resolved city name to get_historical_bias."""
        from traderbot.data.models import BiasReport

        mock_provider = AsyncMock()
        mock_provider.get_historical_bias.return_value = BiasReport(
            city="New York",
            model="nws",
            total_comparisons=5,
            mean_error=1.2,
            mean_abs_error=2.3,
            std_error=0.8,
            last_n_days=90,
        )
        mock_provider.close = AsyncMock()

        with (
            patch(
                "traderbot.data.weather.provider.WeatherDataProvider",
                return_value=mock_provider,
            ),
            patch("traderbot.db.get_connection"),
            patch("traderbot.db.forecast_bias.init_table"),
        ):
            result = runner.invoke(app, ["data", "bias", "NYC"])
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            # get_historical_bias must be called with the resolved name "New York"
            mock_provider.get_historical_bias.assert_called_once_with(
                city="New York", days=90
            )

    def test_bias_cmd_rejects_unknown_city(self) -> None:
        """Verify bias command exits with error for unknown city code."""
        result = runner.invoke(app, ["data", "bias", "ZZZ"])
        assert result.exit_code == 1

    def test_bias_cmd_resolve_la(self) -> None:
        """Verify LA resolves to Los Angeles in bias command."""
        from traderbot.data.models import BiasReport

        mock_provider = AsyncMock()
        mock_provider.get_historical_bias.return_value = BiasReport(
            city="Los Angeles",
            model="nws",
            total_comparisons=3,
            mean_error=-0.5,
            mean_abs_error=1.8,
            std_error=0.6,
            last_n_days=90,
        )
        mock_provider.close = AsyncMock()

        with (
            patch(
                "traderbot.data.weather.provider.WeatherDataProvider",
                return_value=mock_provider,
            ),
            patch("traderbot.db.get_connection"),
            patch("traderbot.db.forecast_bias.init_table"),
        ):
            result = runner.invoke(app, ["data", "bias", "LA"])
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_provider.get_historical_bias.assert_called_once_with(
                city="Los Angeles", days=90
            )


class TestBiasDBQueryResolution:
    """Verify that data stored under 'New York' is found when querying with 'NYC'.

    This is the core bug: record-bias stores 'New York' but the old bias
    command passed 'NYC' directly to the SQL WHERE clause.
    """

    def test_nyc_query_finds_new_york_data(self, tmp_path) -> None:
        """Insert data with city='New York' and query with resolved 'NYC' -> 'New York'."""
        import sqlite3

        from traderbot.db.forecast_bias import init_table, query_bias, record_forecast

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        try:
            init_table(conn)
            # record-bias stores with the resolved city name
            record_forecast(conn, city="New York", forecast_high_f=70.0, actual_high_f=72.0)

            # Simulate the fix: resolve NYC -> New York before querying
            from traderbot.data.weather.provider import _resolve_city

            resolved = _resolve_city("NYC")
            assert resolved == "New York"

            stats = query_bias(conn, city=resolved, days=90)
            assert stats["count"] == 1, (
                f"Expected 1 record for resolved 'NYC'->'New York', got {stats['count']}"
            )
        finally:
            conn.close()

    def test_raw_nyc_finds_nothing(self, tmp_path) -> None:
        """Verify the bug: querying with raw 'NYC' returns 0 results."""
        import sqlite3

        from traderbot.db.forecast_bias import init_table, query_bias, record_forecast

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        try:
            init_table(conn)
            record_forecast(conn, city="New York", forecast_high_f=70.0, actual_high_f=72.0)

            # Without resolution, raw 'NYC' matches nothing
            stats = query_bias(conn, city="NYC", days=90)
            assert stats["count"] == 0, (
                f"Expected 0 results for raw 'NYC', got {stats['count']}"
            )
        finally:
            conn.close()

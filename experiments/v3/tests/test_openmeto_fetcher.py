import sqlite3
from unittest.mock import MagicMock, patch

from experiments.v3.data_sources.openmeto_fetcher import (
    fetch_city_forecast_series,
    fetch_forecast_series,
    fetch_historical_forecast,
    save_forecasts,
)
from experiments.v3.db_schema import create_tables


def _make_api_response(temp_c: float) -> dict:
    """Build a minimal Open-Meteo previous-runs API response."""
    return {
        "daily": {
            "time": ["2026-05-10"],
            "temperature_2m_max": [temp_c],
        }
    }


class TestFetchHistoricalForecast:
    """Test 1 & 2: API extraction + date arithmetic."""

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_extracts_temperature_fahrenheit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response(25.0)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=3)

        assert result["forecast_temp_f"] == 77.0
        assert result["source"] == "open-meteo-previous"

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_zero_celsius_to_fahrenheit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response(0.0)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=3)

        assert result["forecast_temp_f"] == 32.0

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_thirty_celsius_to_fahrenheit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response(30.0)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=3)

        assert result["forecast_temp_f"] == 86.0

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_date_arithmetic_lead_days(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response(20.0)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=4)

        assert result["days_before"] == 4
        assert result["forecast_date_raw"] == "2026-05-06"

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_lead_days_zero_same_day(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response(30.0)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=0)

        assert result["days_before"] == 0
        assert result["forecast_date_raw"] == "2026-05-10"

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_url_uses_previous_runs_api(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_api_response(22.0)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=2)

        call_url = mock_get.call_args[0][0]
        assert "previous-runs-api.open-meteo.com" in call_url


class TestFetchForecastSeries:
    """Test 3: Series returns 5 forecasts with correct lead times."""

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_returns_five_forecasts(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        temps = [18.0, 19.0, 20.0, 21.0, 22.0]
        mock_resp.json.side_effect = [
            _make_api_response(t) for t in temps
        ]
        mock_get.return_value = mock_resp

        results = fetch_forecast_series(40.7, -74.0, "2026-05-10")

        assert len(results) == 5
        lead_times = [r["days_before"] for r in results]
        assert lead_times == [4, 3, 2, 1, 0]

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_forecast_dates_correct(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = [_make_api_response(20.0)] * 5
        mock_get.return_value = mock_resp

        results = fetch_forecast_series(40.7, -74.0, "2026-05-10")

        expected_dates = [
            "2026-05-06",
            "2026-05-07",
            "2026-05-08",
            "2026-05-09",
            "2026-05-10",
        ]
        actual_dates = [r["forecast_date_raw"] for r in results]
        assert actual_dates == expected_dates


class TestSaveForecasts:
    """Test 4: Writes to forecast_snapshots table correctly."""

    def test_inserts_rows(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)

        forecasts = [
            {
                "forecast_temp_f": 77.0,
                "source": "open-meteo-previous",
                "days_before": 4,
                "forecast_date_raw": "2026-05-06",
            },
            {
                "forecast_temp_f": 78.8,
                "source": "open-meteo-previous",
                "days_before": 0,
                "forecast_date_raw": "2026-05-10",
            },
        ]

        save_forecasts(conn, "KXHIGHNY-26MAY10-T80", forecasts, timestep=1)

        rows = conn.execute(
            "SELECT ticker, timestep, days_before, forecast_temp_f, source, forecast_date_raw "
            "FROM forecast_snapshots ORDER BY days_before DESC"
        ).fetchall()

        assert len(rows) == 2
        assert rows[0][0] == "KXHIGHNY-26MAY10-T80"
        assert rows[0][1] == 1
        assert rows[0][2] == 4
        assert rows[0][5] == "2026-05-06"
        assert rows[1][2] == 0
        conn.close()


class TestErrorHandling:
    """Test 5: Graceful handling of API errors."""

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_http_error_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = Exception("Not Found")
        mock_get.return_value = mock_resp

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=2)

        assert result is None

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_timeout_returns_none(self, mock_get):
        mock_get.side_effect = Exception("Connection timed out")

        result = fetch_historical_forecast(40.7, -74.0, "2026-05-10", lead_days=2)

        assert result is None

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    def test_series_skips_failed_fetches(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_api_response(20.0)

        # First call fails, rest succeed
        mock_get.side_effect = [
            Exception("timeout"),
            mock_resp,
            mock_resp,
            mock_resp,
            mock_resp,
        ]

        results = fetch_forecast_series(40.7, -74.0, "2026-05-10")

        assert len(results) == 4


class TestFetchCityForecastSeries:
    """Test batch fetch for multiple target dates."""

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    @patch("experiments.v3.data_sources.openmeto_fetcher.time.sleep")
    def test_returns_dict_by_date(self, mock_sleep, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_api_response(22.0)
        mock_get.return_value = mock_resp

        result = fetch_city_forecast_series(
            "New York", 40.7, -74.0, ["2026-05-10", "2026-05-11"]
        )

        assert "2026-05-10" in result
        assert "2026-05-11" in result
        assert len(result["2026-05-10"]) == 5
        assert len(result["2026-05-11"]) == 5

    @patch("experiments.v3.data_sources.openmeto_fetcher.httpx.get")
    @patch("experiments.v3.data_sources.openmeto_fetcher.time.sleep")
    def test_rate_limits_between_dates(self, mock_sleep, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_api_response(22.0)
        mock_get.return_value = mock_resp

        fetch_city_forecast_series(
            "New York", 40.7, -74.0, ["2026-05-10", "2026-05-11"]
        )

        # sleep called between dates (not within fetch_forecast_series internally)
        assert mock_sleep.call_count >= 1

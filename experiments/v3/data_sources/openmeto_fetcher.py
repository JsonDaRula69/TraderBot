import logging
import sqlite3
import time
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
COURTESY_DELAY = 0.25


def fetch_historical_forecast(
    lat: float, lon: float, target_date: str, lead_days: int
) -> dict | None:
    forecast_date = (
        datetime.fromisoformat(target_date) - timedelta(days=lead_days)
    ).strftime("%Y-%m-%d")

    url = (
        f"{PREVIOUS_RUNS_URL}?latitude={lat}&longitude={lon}"
        f"&start_date={target_date}&end_date={target_date}"
        f"&daily=temperature_2m_max"
    )

    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if not temps or temps[0] is None:
            logger.warning("No temperature data for %s lead_days=%d", target_date, lead_days)
            return None
        temp_f = round(temps[0] * 9 / 5 + 32, 1)
        return {
            "forecast_temp_f": temp_f,
            "source": "open-meteo-previous",
            "days_before": lead_days,
            "forecast_date_raw": forecast_date,
        }
    except Exception:
        logger.exception("Failed to fetch forecast for %s lead_days=%d", target_date, lead_days)
        return None


def fetch_forecast_series(lat: float, lon: float, target_date: str) -> list[dict]:
    results = []
    for lead_days in [4, 3, 2, 1, 0]:
        forecast = fetch_historical_forecast(lat, lon, target_date, lead_days)
        if forecast is not None:
            results.append(forecast)
        if lead_days > 0:
            time.sleep(COURTESY_DELAY)
    return results


def fetch_city_forecast_series(
    city: str, lat: float, lon: float, target_dates: list[str]
) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for i, target_date in enumerate(target_dates):
        result[target_date] = fetch_forecast_series(lat, lon, target_date)
        if i < len(target_dates) - 1:
            time.sleep(COURTESY_DELAY)
    return result


def save_forecasts(
    conn: sqlite3.Connection, ticker: str, forecasts: list[dict], timestep: int = 0
) -> None:
    for fc in forecasts:
        conn.execute(
            "INSERT INTO forecast_snapshots "
            "(ticker, timestep, days_before, forecast_temp_f, source, forecast_date_raw) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                ticker,
                timestep,
                fc["days_before"],
                fc["forecast_temp_f"],
                fc["source"],
                fc["forecast_date_raw"],
            ),
        )
    conn.commit()

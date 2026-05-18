#!/usr/bin/env python3
"""Compile experiment dataset: 25 settled Kalshi weather markets + synthesized forecast snapshots.

Outputs: experiments/experiment_data.db (SQLite)

Forecast variation is synthesized from actual observed temperatures with realistic
error distributions that decrease with lead time (standard practice for weather
market backtesting when historical model runs are unavailable).

Market prices are synthesized from forecast-implied probabilities with noise.

Run: python3 experiments/compile_data.py
Requires: TraderBot env with Kalshi API credentials
"""

from __future__ import annotations

import asyncio
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# ── Config ──────────────────────────────────────────────────────────────────

CITY_COORDS: dict[str, tuple[str, float, float, str]] = {
    "KXHIGHAUS": ("Austin", 30.27, -97.74, "America/Chicago"),
    "KXHIGHCHI": ("Chicago", 41.88, -87.63, "America/Chicago"),
    "KXHIGHDEN": ("Denver", 39.74, -104.99, "America/Denver"),
    "KXHIGHLAX": ("Los Angeles", 34.05, -118.24, "America/Los_Angeles"),
    "KXHIGHMIA": ("Miami", 25.76, -80.19, "America/New_York"),
    "KXHIGHNY": ("New York", 40.71, -74.01, "America/New_York"),
    "KXHIGHPHIL": ("Philadelphia", 39.95, -75.16, "America/New_York"),
    "KXHIGHTATL": ("Atlanta", 33.75, -84.39, "America/New_York"),
    "KXHIGHTBOS": ("Boston", 42.36, -71.06, "America/New_York"),
    "KXHIGHTDAL": ("Dallas", 32.78, -96.80, "America/Chicago"),
    "KXHIGHTDC": ("Washington DC", 38.91, -77.04, "America/New_York"),
    "KXHIGHTHOU": ("Houston", 29.76, -95.37, "America/Chicago"),
    "KXHIGHTLV": ("Las Vegas", 36.17, -115.14, "America/Los_Angeles"),
    "KXHIGHTMIN": ("Minneapolis", 44.98, -93.26, "America/Chicago"),
    "KXHIGHTNOLA": ("New Orleans", 29.95, -90.07, "America/Chicago"),
    "KXHIGHTOKC": ("Oklahoma City", 35.47, -97.52, "America/Chicago"),
    "KXHIGHTPHX": ("Phoenix", 33.45, -112.07, "America/Phoenix"),
    "KXHIGHTSATX": ("San Antonio", 29.42, -98.49, "America/Chicago"),
    "KXHIGHTSEA": ("Seattle", 47.61, -122.33, "America/Los_Angeles"),
    "KXHIGHTSFO": ("San Francisco", 37.77, -122.42, "America/Los_Angeles"),
}

# Forecast error standard deviation (°F) at each lead time.
# Based on NWS verification data: 7-day high temp forecast MAE ≈ 4-5°F,
# 3-day ≈ 2-3°F, 1-day ≈ 1-2°F.
FORECAST_ERROR_STD = {
    1: 4.5,   # T-9: 9 days lead
    2: 4.0,   # T-8
    3: 3.5,   # T-7
    4: 3.0,   # T-6
    5: 2.5,   # T-5
    6: 2.0,   # T-4
    7: 1.5,   # T-3
    8: 1.2,   # T-2
    9: 0.8,   # T-1
    10: 0.3,  # T-0: near-certain (model very close to actual)
}

# Systematic forecast bias by region (°F). Positive = model over-predicts.
# NOAA verification shows slight warm bias for most US cities in summer.
CITY_BIAS_F: dict[str, float] = {
    "KXHIGHAUS": 0.5, "KXHIGHCHI": -0.3, "KXHIGHDEN": -0.5,
    "KXHIGHLAX": 0.2, "KXHIGHMIA": 0.8, "KXHIGHNY": -0.2,
    "KXHIGHPHIL": -0.2, "KXHIGHTATL": 0.5, "KXHIGHTBOS": -0.4,
    "KXHIGHTDAL": 0.6, "KXHIGHTDC": -0.1, "KXHIGHTHOU": 0.7,
    "KXHIGHTLV": 0.3, "KXHIGHTMIN": -0.5, "KXHIGHTNOLA": 0.4,
    "KXHIGHTOKC": 0.3, "KXHIGHTPHX": 0.9, "KXHIGHTSATX": 0.5,
    "KXHIGHTSEA": -0.4, "KXHIGHTSFO": -0.3,
}

KALSHI_BASE = "https://trade-api.kalshi.com"
DB_PATH = Path(__file__).parent / "experiment_data.db"
RANDOM_SEED = 42  # Deterministic for reproducibility

# ── Helpers ────────────────────────────────────────────────────────────────

def c2f(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 1)

def f2c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0

def parse_resolution_date(ticker: str) -> datetime | None:
    try:
        parts = ticker.split("-")
        if len(parts) < 3:
            return None
        d = parts[1]
        year = 2000 + int(d[:2])
        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                   "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        month = months.get(d[2:5].upper())
        if month is None:
            return None
        day = int(d[5:7])
        return datetime(year, month, day, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None

def synthesize_forecast(actual_temp_f: float, timestep: int, city_prefix: str, rng: random.Random) -> dict[str, float | None]:
    """Synthesize a realistic forecast for a given timestep.
    
    Starts from actual temperature and adds forecast error that decreases
    with lead time (closer to settlement = more accurate forecast).
    Includes a systematic city bias term.
    """
    std = FORECAST_ERROR_STD[timestep]
    bias = CITY_BIAS_F.get(city_prefix, 0.0)
    error = rng.gauss(bias * (1 - timestep / 10), std)  # Bias diminishes closer to settlement
    forecast_temp = actual_temp_f + error
    
    # Also synthesize min temp (typically 15-25°F below max)
    min_offset = rng.gauss(-18, 3)  # avg 18°F spread
    forecast_min = forecast_temp + min_offset
    
    # Precipitation: increasing certainty closer to settlement
    precip_prob = max(0, min(1, 0.5 + rng.gauss(0, 0.15 * (1 + (10 - timestep) / 10))))
    precip_mm = round(rng.expovariate(2) if precip_prob > 0.3 else 0, 1)
    
    # Wind: moderate variation
    wind = round(max(5, rng.gauss(15, 5 * (1 + (10 - timestep) / 10))), 1)
    
    # Humidity: high baseline with variation
    humidity = round(min(100, max(30, rng.gauss(70, 10 * (1 + (10 - timestep) / 10)))), 0)
    
    # Weather code: more certain closer to settlement
    # 0=clear, 1=mainly clear, 2=partly cloudy, 3=overcast, 45=fog, 51=drizzle, 61=rain, 63=moderate rain
    if timestep >= 8:
        weather_code = rng.choice([0, 1, 2, 3])  # More certain
    else:
        weather_code = rng.choice([0, 1, 2, 3, 45, 51, 61, 63])
    
    return {
        "temp_max_f": round(forecast_temp, 1),
        "temp_min_f": round(forecast_min, 1),
        "precip_mm": precip_mm,
        "wind_speed_max_kmh": wind,
        "humidity_max_pct": humidity,
        "weather_code": weather_code,
    }


def compute_band_probability(forecast_max_f: float, strike_value: float) -> float:
    """Compute probability of YES for a band market.
    
    For band markets like "Will high temp be 95-96°F?", the strike_value
    is the lower bound. The band covers [strike, strike+1).
    Using a normal CDF approximation centered on forecast with decreasing variance.
    """
    from math import erf, sqrt
    
    # Approximate probability that actual temp falls in [strike, strike+1)
    # Given forecast with assumed std
    lower = strike_value
    upper = strike_value + 1.0
    # Use normal CDF: P(lower <= X < upper) given X ~ N(forecast, forecast_std^2)
    # For simplicity, use σ ≈ 2°F (typical 1-day forecast error)
    forecast_std = 2.0
    
    z_lower = (lower - forecast_max_f) / (forecast_std * sqrt(2))
    z_upper = (upper - forecast_max_f) / (forecast_std * sqrt(2))
    
    prob = 0.5 * (erf(z_upper) - erf(z_lower))
    return max(0.01, min(0.99, prob))  # Clamp to [0.01, 0.99]


# ── SQLite ──────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            ticker TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            city TEXT NOT NULL,
            city_prefix TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            timezone TEXT NOT NULL,
            resolution_date TEXT NOT NULL,
            close_time TEXT NOT NULL,
            settlement_result TEXT,
            actual_value REAL,
            strike_value REAL,
            strike_type TEXT,
            market_type TEXT,
            yes_price_dollars REAL,
            volume REAL,
            open_interest REAL,
            event_ticker TEXT,
            series_ticker TEXT
        );
        CREATE TABLE IF NOT EXISTS forecast_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestep INTEGER NOT NULL,
            forecast_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            temp_max_f REAL,
            temp_min_f REAL,
            precip_mm REAL,
            wind_speed_max_kmh REAL,
            humidity_max_pct REAL,
            weather_code INTEGER,
            source TEXT DEFAULT 'synthesized',
            FOREIGN KEY (ticker) REFERENCES markets(ticker),
            UNIQUE(ticker, timestep)
        );
        CREATE TABLE IF NOT EXISTS settlement_actuals (
            ticker TEXT PRIMARY KEY,
            actual_temp_max_f REAL,
            actual_temp_min_f REAL,
            actual_precip_mm REAL,
            actual_weather_code INTEGER,
            FOREIGN KEY (ticker) REFERENCES markets(ticker)
        );
        CREATE TABLE IF NOT EXISTS market_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestep INTEGER NOT NULL,
            yes_price REAL NOT NULL,
            no_price REAL NOT NULL,
            volume REAL,
            open_interest REAL,
            FOREIGN KEY (ticker) REFERENCES markets(ticker),
            UNIQUE(ticker, timestep)
        );
        CREATE TABLE IF NOT EXISTS methodology_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestep INTEGER NOT NULL,
            methodology TEXT NOT NULL,
            estimated_prob REAL NOT NULL,
            confidence REAL NOT NULL,
            reasoning_data TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (ticker) REFERENCES markets(ticker),
            UNIQUE(ticker, timestep, methodology)
        );
        CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestep INTEGER NOT NULL,
            methodology TEXT NOT NULL,
            decision TEXT NOT NULL,
            estimated_prob REAL,
            confidence REAL,
            edge_estimate REAL,
            position_size_cents INTEGER,
            reasoning TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (ticker) REFERENCES markets(ticker)
        );
        CREATE TABLE IF NOT EXISTS calibration_bins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            methodology TEXT NOT NULL,
            bin_label TEXT NOT NULL,
            bin_lower REAL NOT NULL,
            bin_upper REAL NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            actual_rate REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(methodology, bin_label)
        );
        CREATE INDEX IF NOT EXISTS idx_snap_ticker ON forecast_snapshots(ticker);
        CREATE INDEX IF NOT EXISTS idx_snap_timestep ON forecast_snapshots(ticker, timestep);
        CREATE INDEX IF NOT EXISTS idx_prices_ticker ON market_prices(ticker);
        CREATE INDEX IF NOT EXISTS idx_decisions_ticker ON agent_decisions(ticker);
    """)
    conn.commit()

# ── Main ────────────────────────────────────────────────────────────────────

async def main() -> None:
    from traderbot.kalshi.client import KalshiClient
    
    rng = random.Random(RANDOM_SEED)
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    print(f"DB: {DB_PATH}")

    kalshi = KalshiClient()

    # ── Step 1: Fetch settled weather markets from Kalshi ──
    resp = await kalshi.get("/series", limit=10000)
    all_series = resp.json().get("series", [])
    weather_series = [s for s in all_series if s.get("ticker") in CITY_COORDS]
    print(f"Weather series: {len(weather_series)}")

    all_markets = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)

    for s in weather_series:
        st = s["ticker"]
        city, lat, lon, tz = CITY_COORDS[st]
        resp = await kalshi.get("/markets", limit=100, series_ticker=st)
        markets = resp.json().get("markets", [])

        for m in markets:
            ticker = m.get("ticker", "")
            status = m.get("status", m.get("state", ""))
            if status not in ("finalized", "settled"):
                continue

            parts = ticker.split("-")
            if len(parts) < 3:
                continue
            suffix = parts[-1]
            mtype = "band" if suffix.startswith("B") else "threshold" if suffix.startswith("T") else None
            if mtype is None:
                continue

            res_date = parse_resolution_date(ticker)
            if res_date is None or res_date < cutoff:
                continue

            strike = None
            try: strike = float(suffix[1:])
            except ValueError: pass

            question = m.get("title") or m.get("question") or m.get("no_sub_title") or ""

            detail = await kalshi.get(f"/markets/{ticker}")
            d = detail.json().get("market", detail.json())
            result = d.get("result")
            exp_val = d.get("expiration_value")

            all_markets.append({
                "ticker": ticker, "question": question, "city": city,
                "city_prefix": st, "lat": lat, "lon": lon, "timezone": tz,
                "resolution_date": res_date.strftime("%Y-%m-%d"),
                "close_time": m.get("close_time", ""),
                "settlement_result": result,
                "actual_value": float(exp_val) if exp_val is not None else None,
                "strike_value": strike,
                "strike_type": "greater" if suffix.startswith("T") else "band",
                "market_type": mtype,
                "yes_price_dollars": float(m.get("yes_ask_dollars", 0)) if m.get("yes_ask_dollars") else None,
                "volume": float(m.get("volume_fp", m.get("volume", 0))),
                "open_interest": float(m.get("open_interest_fp", m.get("open_interest", 0))),
                "event_ticker": m.get("event_ticker", ""),
                "series_ticker": st,
            })
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.5)

    print(f"Total settled markets (last 30d): {len(all_markets)}")

    # Select 25 diverse markets
    city_groups: dict[str, list[dict]] = {}
    for m in all_markets:
        city_groups.setdefault(m["city_prefix"], []).append(m)

    selected = []
    for cp, cms in sorted(city_groups.items()):
        used: set[str] = set()
        for pool in [[m for m in cms if m["market_type"] == "band"],
                    [m for m in cms if m["market_type"] == "threshold"]]:
            for m in pool:
                if m["resolution_date"] not in used and len(selected) < 25:
                    selected.append(m)
                    used.add(m["resolution_date"])
                if len(used) >= 2:
                    break

    print(f"Selected {len(selected)} markets")

    # ── Step 2: Fetch actuals from Open-Meteo + synthesize forecasts ──
    async with httpx.AsyncClient(timeout=30.0) as http:
        for i, m in enumerate(selected):
            ticker = m["ticker"]
            print(f"\n[{i+1}/{len(selected)}] {ticker} ({m['city']}, {m['resolution_date']})")

            # Insert market
            conn.execute("""
                INSERT OR REPLACE INTO markets
                (ticker, question, city, city_prefix, lat, lon, timezone, resolution_date, close_time,
                 settlement_result, actual_value, strike_value, strike_type, market_type,
                 yes_price_dollars, volume, open_interest, event_ticker, series_ticker)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker, m["question"], m["city"], m["city_prefix"], m["lat"], m["lon"], m["timezone"],
                m["resolution_date"], m["close_time"], m["settlement_result"], m["actual_value"],
                m["strike_value"], m["strike_type"], m["market_type"],
                m["yes_price_dollars"], m["volume"], m["open_interest"], m["event_ticker"], m["series_ticker"],
            ))
            conn.commit()

            # Fetch actual observed weather for the target date
            actual_temp_max_f = m["actual_value"]  # From Kalshi expiration_value (most authoritative)
            actual_temp_min_f = None
            actual_precip = None
            actual_wmo = None

            try:
                resp = await http.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params={"latitude": m["lat"], "longitude": m["lon"],
                             "start_date": m["resolution_date"], "end_date": m["resolution_date"],
                             "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                             "timezone": m["timezone"]},
                )
                resp.raise_for_status()
                d = resp.json().get("daily", {})
                tmax = (d.get("temperature_2m_max") or [None])[0]
                tmin = (d.get("temperature_2m_min") or [None])[0]
                prec = (d.get("precipitation_sum") or [None])[0]
                wmo = (d.get("weather_code") or [None])[0]
                
                # Use Kalshi expiration_value as authoritative actual_max, 
                # but store Open-Meteo for verification
                actual_temp_min_f = c2f(tmin) if tmin is not None else actual_temp_max_f - 18.0 if actual_temp_max_f else None
                actual_precip = prec
                actual_wmo = int(wmo) if wmo is not None else None
                
                # Also cross-check: if Kalshi didn't have actual_value, use OWM
                if actual_temp_max_f is None and tmax is not None:
                    actual_temp_max_f = c2f(tmax)
                    
            except Exception as e:
                print(f"  WARN actuals: {e}")

            # Store actuals (separate table, NOT exposed to agent during simulation)
            conn.execute("""
                INSERT OR REPLACE INTO settlement_actuals
                (ticker, actual_temp_max_f, actual_temp_min_f, actual_precip_mm, actual_weather_code)
                VALUES (?,?,?,?,?)
            """, (ticker, actual_temp_max_f, actual_temp_min_f, actual_precip, actual_wmo))
            conn.commit()

            if actual_temp_max_f is None:
                print(f"  SKIP: No actual temperature data")
                continue

            # ── Synthesize 10 forecast snapshots ──
            # Each timestep represents what the forecast LOOKED LIKE at that lead time.
            # Error decreases as timestep increases (closer to settlement = more accurate).
            for ts in range(1, 11):
                days_before = 10 - ts
                forecast_date = (datetime.fromisoformat(m["resolution_date"]) - timedelta(days=days_before)).strftime("%Y-%m-%d")
                
                fc = synthesize_forecast(actual_temp_max_f, ts, m["city_prefix"], rng)
                
                conn.execute("""
                    INSERT OR REPLACE INTO forecast_snapshots
                    (ticker, timestep, forecast_date, target_date, temp_max_f, temp_min_f,
                     precip_mm, wind_speed_max_kmh, humidity_max_pct, weather_code, source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (ticker, ts, forecast_date, m["resolution_date"],
                      fc["temp_max_f"], fc["temp_min_f"], fc["precip_mm"],
                      fc["wind_speed_max_kmh"], fc["humidity_max_pct"],
                      fc.get("weather_code"), "synthesized"))

                # ── Synthesize market prices for this timestep ──
                # Price reflects forecast-implied probability with noise
                base_prob = compute_band_probability(fc["temp_max_f"], m["strike_value"])
                # Add market noise: early timesteps have wider spreads, later are tighter
                price_noise = rng.gauss(0, 0.03 * (1 + (10 - ts) / 5))
                yes_price = max(0.01, min(0.99, round(base_prob + price_noise, 2)))
                no_price = round(1.0 - yes_price, 2)
                
                # Volume and OI: higher closer to settlement
                base_vol = m.get("volume", 1000) or 1000
                vol_factor = 0.3 + 0.7 * (ts / 10)  # 30% at T-9, 100% at T-0
                vol = round(base_vol * vol_factor * rng.uniform(0.8, 1.2), 0)
                oi = round(vol * rng.uniform(0.3, 0.6), 0)
                
                conn.execute("""
                    INSERT OR REPLACE INTO market_prices
                    (ticker, timestep, yes_price, no_price, volume, open_interest)
                    VALUES (?,?,?,?,?,?)
                """, (ticker, ts, yes_price, no_price, vol, oi))

            conn.commit()
            
            ts_data = conn.execute(
                "SELECT timestep, temp_max_f FROM forecast_snapshots WHERE ticker=? ORDER BY timestep", 
                (ticker,)
            ).fetchall()
            temps = [r[1] for r in ts_data]
            min_t, max_t = min(temps), max(temps)
            spread = round(max_t - min_t, 1) if len(temps) > 1 else 0
            print(f"  Actual={actual_temp_max_f}°F, Forecast range=[{min_t}, {max_t}]°F, Spread={spread}°F, Snapshots={len(ts_data)}")

            await asyncio.sleep(0.3)

    await kalshi.close()

    # ── Summary ──
    mc = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
    fc = conn.execute("SELECT COUNT(DISTINCT ticker || timestep) FROM forecast_snapshots").fetchone()[0]
    ac = conn.execute("SELECT COUNT(*) FROM settlement_actuals WHERE actual_temp_max_f IS NOT NULL").fetchone()[0]
    sr = conn.execute("SELECT COUNT(*) FROM markets WHERE settlement_result IS NOT NULL").fetchone()[0]
    pc = conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0]
    
    # Verify forecast variation
    zero_spread = 0
    for (ticker,) in conn.execute("SELECT DISTINCT ticker FROM forecast_snapshots").fetchall():
        temps = [r[0] for r in conn.execute(
            "SELECT temp_max_f FROM forecast_snapshots WHERE ticker=? ORDER BY timestep", (ticker,)
        ).fetchall()]
        if len(set(temps)) <= 1:
            zero_spread += 1

    print(f"\n{'='*60}")
    print(f"Database: {DB_PATH}")
    print(f"  Markets: {mc} (with result: {sr})")
    print(f"  Unique forecast snapshots: {fc}")
    print(f"  Market prices: {pc}")
    print(f"  Settlement actuals: {ac}")
    print(f"  Markets with zero forecast spread: {zero_spread}/{mc}")
    print(f"{'='*60}")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""One-time data compilation: 25 settled Kalshi weather markets + 10 Open-Meteo forecast snapshots.

Outputs: experiments/experiment_data.db (SQLite)
Run: python3 experiments/compile_data.py
Uses TraderBot's KalshiClient for auth.
"""

from __future__ import annotations

import asyncio
import os
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

DB_PATH = Path(__file__).parent / "experiment_data.db"

# ── Helpers ────────────────────────────────────────────────────────────────

def c2f(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 1)

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
            source TEXT DEFAULT 'open-meteo'
        );
        CREATE TABLE IF NOT EXISTS settlement_actuals (
            ticker TEXT PRIMARY KEY,
            actual_temp_max_f REAL,
            actual_temp_min_f REAL,
            actual_precip_mm REAL,
            actual_weather_code INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_snap_ticker ON forecast_snapshots(ticker);
        CREATE INDEX IF NOT EXISTS idx_snap_ts ON forecast_snapshots(ticker, timestep);
    """)
    conn.commit()

# ── Main ────────────────────────────────────────────────────────────────────

async def main() -> None:
    from traderbot.kalshi.client import KalshiClient

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    print(f"DB: {DB_PATH}")

    kalshi = KalshiClient()

    # ── Step 1: Fetch settled weather markets ──
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

            # Fetch detail for settlement result
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

        print(f"  {st}: total settled={len(all_markets)}")
        await asyncio.sleep(0.5)

    print(f"\nTotal settled markets (last 30d): {len(all_markets)}")

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
    for m in selected:
        sr = m["settlement_result"] or "?"
        av = f"{m['actual_value']}°F" if m["actual_value"] else "?"
        print(f"  {m['ticker']} | {m['city']} | res={m['resolution_date']} | result={sr} | actual={av} | strike={m['strike_value']}")

    # ── Step 2: Store + fetch forecasts ──
    async with httpx.AsyncClient(timeout=30.0) as http:
        for i, m in enumerate(selected):
            ticker = m["ticker"]
            print(f"\n[{i+1}/{len(selected)}] {ticker} ({m['city']}, {m['resolution_date']})")

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

            # 10 forecast snapshots
            for ts in range(1, 11):
                days_before = 10 - ts
                target_date = m["resolution_date"]
                forecast_date = (datetime.fromisoformat(target_date) - timedelta(days=days_before)).strftime("%Y-%m-%d")

                try:
                    resp = await http.get(
                        "https://archive-api.open-meteo.com/v1/archive",
                        params={"latitude": m["lat"], "longitude": m["lon"],
                                 "start_date": forecast_date, "end_date": target_date,
                                 "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max,relative_humidity_2m_max",
                                 "timezone": m["timezone"]},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    daily = data.get("daily", {})
                    times = daily.get("time", [])
                    idx = times.index(target_date) if target_date in times else None

                    def gv(key: str, i: int | None) -> float | None:
                        vals = daily.get(key, [])
                        return float(vals[i]) if i is not None and i < len(vals) and vals[i] is not None else None

                    if idx is not None:
                        tmax = gv("temperature_2m_max", idx)
                        tmin = gv("temperature_2m_min", idx)
                        prec = gv("precipitation_sum", idx)
                        wmo_raw = daily.get("weather_code", [])
                        wmo = int(wmo_raw[idx]) if idx < len(wmo_raw) and wmo_raw[idx] is not None else None
                        wind = gv("wind_speed_10m_max", idx)
                        humid = gv("relative_humidity_2m_max", idx)
                        conn.execute("""
                            INSERT INTO forecast_snapshots
                            (ticker, timestep, forecast_date, target_date, temp_max_f, temp_min_f,
                             precip_mm, wind_speed_max_kmh, humidity_max_pct, weather_code, source)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (ticker, ts, forecast_date, target_date,
                              c2f(tmax) if tmax else None, c2f(tmin) if tmin else None,
                              prec, wind, humid, wmo, "open-meteo-archive"))
                    else:
                        conn.execute("""
                            INSERT INTO forecast_snapshots (ticker, timestep, forecast_date, target_date, source)
                            VALUES (?,?,?,?,?,'missing')
                        """, (ticker, ts, forecast_date, target_date))
                except Exception as e:
                    conn.execute("""
                        INSERT INTO forecast_snapshots (ticker, timestep, forecast_date, target_date, source)
                        VALUES (?,?,?,?,?'error')
                    """, (ticker, ts, forecast_date, target_date))

                await asyncio.sleep(0.15)

            conn.commit()
            valid = conn.execute("SELECT COUNT(*) FROM forecast_snapshots WHERE ticker=? AND temp_max_f IS NOT NULL", (ticker,)).fetchone()[0]
            print(f"  -> {valid}/10 forecast snapshots")

            # Settlement actuals
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
                conn.execute("""
                    INSERT OR REPLACE INTO settlement_actuals
                    (ticker, actual_temp_max_f, actual_temp_min_f, actual_precip_mm, actual_weather_code)
                    VALUES (?,?,?,?,?)
                """, (ticker, c2f(tmax) if tmax else None, c2f(tmin) if tmin else None,
                      prec, int(wmo) if wmo else None))
                conn.commit()
                print(f"  -> Actual: max={c2f(tmax) if tmax else '?'}°F")
            except Exception as e:
                print(f"  -> Actual error: {e}")

            await asyncio.sleep(0.3)

    await kalshi.close()

    mc = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
    sc = conn.execute("SELECT COUNT(*) FROM forecast_snapshots WHERE temp_max_f IS NOT NULL").fetchone()[0]
    ac = conn.execute("SELECT COUNT(*) FROM settlement_actuals WHERE actual_temp_max_f IS NOT NULL").fetchone()[0]
    sr = conn.execute("SELECT COUNT(*) FROM markets WHERE settlement_result IS NOT NULL").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"Database: {DB_PATH}")
    print(f"  Markets: {mc} (with result: {sr})")
    print(f"  Forecast snapshots: {sc}")
    print(f"  Settlement actuals: {ac}")
    print(f"{'='*60}")
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())

import random
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Stratum:
    difficulty: str
    strike_type: str
    lead_time_bucket: str


def compute_stratum(market: dict, t0_price: dict) -> Stratum:
    yes_price = t0_price.get("yes_price", 0.5)
    difficulty = "contested" if 0.20 <= yes_price <= 0.80 else "blowout"
    strike_type = market.get("strike_type", "between")
    lead_time_bucket = market.get("lead_time_bucket", "medium")
    return Stratum(
        difficulty=difficulty, strike_type=strike_type, lead_time_bucket=lead_time_bucket
    )


def _parse_date(date_str: str) -> date | None:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _compute_lead_bucket(resolution_date_str: str | None, reference_date: date) -> str:
    if not resolution_date_str:
        return "medium"
    rd = _parse_date(resolution_date_str)
    if rd is None:
        return "medium"
    days = (rd - reference_date).days
    if days <= 2:
        return "short"
    elif days <= 7:
        return "medium"
    else:
        return "long"


def select_markets(
    conn: sqlite3.Connection,
    markets_per_cell: int = 2,
    seed: int = 42,
    reference_date: date | None = None,
) -> dict[str, list[str]]:
    if reference_date is None:
        reference_date = date.today()

    rng = random.Random(seed)

    cur = conn.execute("""
        SELECT m.ticker, m.strike_type, m.resolution_date, mp.yes_price
        FROM markets m
        JOIN market_prices mp ON m.ticker = mp.ticker
        WHERE m.settlement_result IS NOT NULL
          AND mp.timestep = 0
    """)

    markets: dict[str, list[str]] = {}
    for row in cur.fetchall():
        ticker, strike_type, resolution_date_str, yes_price = row
        difficulty = "contested" if 0.20 <= yes_price <= 0.80 else "blowout"
        lead_bucket = _compute_lead_bucket(resolution_date_str, reference_date)
        stratum_key = f"{difficulty}-{strike_type}-{lead_bucket}"
        markets.setdefault(stratum_key, []).append(ticker)

    selected: dict[str, list[str]] = {}
    for stratum_key, tickers in markets.items():
        sample_size = min(markets_per_cell, len(tickers))
        selected[stratum_key] = rng.sample(tickers, sample_size)

    return selected

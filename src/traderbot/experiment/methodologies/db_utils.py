from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timezone


def select_markets(
    conn: sqlite3.Connection,
    markets_per_cell: int = 2,
    seed: int = 42,
) -> dict[str, list[str]]:
    rows = conn.execute(
        "SELECT ticker, city_prefix, resolution_date FROM markets"
    ).fetchall()

    if not rows:
        return {}

    today = datetime.now(timezone.utc).date()
    prefix_tickers: dict[str, dict[str, list[str]]] = {}

    for ticker, city_prefix, resolution_date in rows:
        try:
            res_date = datetime.strptime(resolution_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        days_to = (res_date - today).days
        if days_to < 7:
            bucket = "lt7d"
        elif days_to <= 14:
            bucket = "7-14d"
        else:
            bucket = "gt14d"
        prefix_tickers.setdefault(
            city_prefix, {"lt7d": [], "7-14d": [], "gt14d": []}
        )
        prefix_tickers[city_prefix][bucket].append(ticker)

    rng = random.Random(seed)
    result = {}

    for prefix, by_bucket in prefix_tickers.items():
        for bucket_name, tickers in by_bucket.items():
            if len(tickers) >= markets_per_cell:
                rng.shuffle(tickers)
                result[f"{prefix}_{bucket_name}"] = tickers[:markets_per_cell]

    return result

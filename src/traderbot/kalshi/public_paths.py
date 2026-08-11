from __future__ import annotations

from typing import Final

PUBLIC_ENDPOINTS: Final = frozenset(
    {
        "/exchange/status",
        "/markets",
        "/markets/trades",
        "/markets/{ticker}",
        "/markets/{ticker}/orderbook",
        "/markets/orderbooks",
        "/events",
        "/events/{event_ticker}",
        "/events/{event_ticker}/candlesticks",
        "/events/{event_ticker}/metadata",
        "/events/multivariate",
        "/series",
        "/series/{ticker}",
        "/series/{series_ticker}/markets/{ticker}/candlesticks",
        "/historical/markets/{ticker}/candlesticks",
        "/multivariate/event-collections",
        "/multivariate/event-collections/{ticker}",
    }
)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_ENDPOINTS:
        return True
    segments = path.strip("/").split("/")
    for public in PUBLIC_ENDPOINTS:
        public_segments = public.strip("/").split("/")
        if len(segments) != len(public_segments):
            continue
        matches = all(
            (pattern.startswith("{") and pattern.endswith("}")) or segment == pattern
            for segment, pattern in zip(segments, public_segments, strict=True)
        )
        if matches:
            return True
    return False

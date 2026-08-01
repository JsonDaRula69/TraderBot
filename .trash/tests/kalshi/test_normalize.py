"""Tests for _normalize_market strike_type extraction."""

from __future__ import annotations

import pytest

from traderbot.kalshi._normalize import _normalize_market


def _make_raw_market(**overrides) -> dict:
    """Build a minimal raw market dict for _normalize_market tests."""
    base = {
        "ticker": "KXHIGHTCHI-26JUN02-T81",
        "question": "Will Chicago high be below 81°F?",
        "outcome_prices": ["0.55", "0.45"],
        "volume_fp": "1000",
        "open_interest_fp": "500",
        "close_time": 1750000000,
        "state": "active",
        "event_ticker": "EV-KXHIGHCHI-26JUN02",
        "category": "weather",
    }
    base.update(overrides)
    return base


class TestNormalizeMarketStrikeType:
    def test_strike_type_less_from_api(self):
        raw = _make_raw_market(strike_type="less")
        market = _normalize_market(raw)
        assert market.strike_type == "less"

    def test_strike_type_greater_from_api(self):
        raw = _make_raw_market(strike_type="greater")
        market = _normalize_market(raw)
        assert market.strike_type == "greater"

    def test_strike_type_between_from_api(self):
        raw = _make_raw_market(strike_type="between")
        market = _normalize_market(raw)
        assert market.strike_type == "between"

    def test_strike_type_absent_yields_none(self):
        raw = _make_raw_market()
        market = _normalize_market(raw)
        assert market.strike_type is None

    def test_strike_type_case_insensitive(self):
        raw = _make_raw_market(strike_type="Less")
        market = _normalize_market(raw)
        assert market.strike_type == "less"

    def test_strike_type_non_standard_less(self):
        raw = _make_raw_market(strike_type="below_threshold")
        market = _normalize_market(raw)
        assert market.strike_type == "less"

    def test_strike_type_non_standard_greater(self):
        raw = _make_raw_market(strike_type="above_threshold")
        market = _normalize_market(raw)
        assert market.strike_type == "greater"

    def test_strike_type_integer_ignored(self):
        raw = _make_raw_market(strike_type=42)
        market = _normalize_market(raw)
        assert market.strike_type is None
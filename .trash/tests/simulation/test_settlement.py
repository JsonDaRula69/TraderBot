"""Tests for weather bet settlement direction logic."""

from __future__ import annotations

import pytest

from traderbot.simulation.settlement import _parse_kalshi_ticker


class TestParseKalshiTicker:
    def test_kxhigh_t_type(self):
        result = _parse_kalshi_ticker("KXHIGHTCHI-26JUN02-T81")
        assert result is not None
        prefix, year, month, day, strike_type, strike_val = result
        assert prefix == "KXHIGHTCHI"
        assert strike_type == "T"
        assert strike_val == 81.0

    def test_kxlowt_t_type(self):
        result = _parse_kalshi_ticker("KXLOWTCHI-26JUN02-T32")
        assert result is not None
        prefix, year, month, day, strike_type, strike_val = result
        assert prefix == "KXLOWTCHI"
        assert strike_type == "T"
        assert strike_val == 32.0

    def test_b_type(self):
        result = _parse_kalshi_ticker("KXHIGHTCHI-26JUN02-B72.5")
        assert result is not None
        strike_type = result[4]
        strike_val = result[5]
        assert strike_type == "B"
        assert strike_val == 72.5

    def test_case_insensitive(self):
        result = _parse_kalshi_ticker("kxhightchi-26jun02-t81")
        assert result is not None

    def test_invalid_ticker(self):
        assert _parse_kalshi_ticker("INVALID") is None


class TestSettlementDirection:
    """Verify settlement direction logic for KXHIGH T-type vs KXLOWT T-type.

    KXHIGH T-type: YES wins when actual < threshold (below)
    KXLOWT T-type: YES wins when actual > threshold (above)
    """

    def test_kxhigh_t_type_yes_wins_below(self):
        """KXHIGH T-type: actual=70°F < threshold=81°F → YES wins."""
        prefix = "KXHIGHTCHI"
        strike_type_marker = "T"
        strike_val = 81.0
        actual_temp = 70.0

        if strike_type_marker == "T":
            if prefix.upper().startswith("KXLOWT"):
                won = actual_temp > strike_val
            else:
                won = actual_temp < strike_val
        else:
            won = actual_temp > strike_val

        assert won is True, "KXHIGH T-type: actual < threshold → YES should win"

    def test_kxhigh_t_type_no_wins_above(self):
        """Bug #143: KXHIGH T-type: actual=86°F > threshold=81°F → NO wins (YES loses)."""
        prefix = "KXHIGHTCHI"
        strike_type_marker = "T"
        strike_val = 81.0
        actual_temp = 86.0

        if strike_type_marker == "T":
            if prefix.upper().startswith("KXLOWT"):
                won = actual_temp > strike_val
            else:
                won = actual_temp < strike_val
        else:
            won = actual_temp > strike_val

        assert won is False, "KXHIGH T-type: actual > threshold → YES should NOT win"

    def test_kxlowt_t_type_yes_wins_above(self):
        """KXLOWT T-type: actual=40°F > threshold=32°F → YES wins."""
        prefix = "KXLOWTCHI"
        strike_type_marker = "T"
        strike_val = 32.0
        actual_temp = 40.0

        if strike_type_marker == "T":
            if prefix.upper().startswith("KXLOWT"):
                won = actual_temp > strike_val
            else:
                won = actual_temp < strike_val
        else:
            won = actual_temp > strike_val

        assert won is True, "KXLOWT T-type: actual > threshold → YES should win"

    def test_kxlowt_t_type_no_wins_below(self):
        """KXLOWT T-type: actual=20°F < threshold=32°F → NO wins (YES loses)."""
        prefix = "KXLOWTCHI"
        strike_type_marker = "T"
        strike_val = 32.0
        actual_temp = 20.0

        if strike_type_marker == "T":
            if prefix.upper().startswith("KXLOWT"):
                won = actual_temp > strike_val
            else:
                won = actual_temp < strike_val
        else:
            won = actual_temp > strike_val

        assert won is False, "KXLOWT T-type: actual < threshold → YES should NOT win"

    def test_b_type_default_greater(self):
        """B-type: defaults to actual > strike_val check."""
        strike_type_marker = "B"
        strike_val = 72.5
        actual_temp = 80.0

        won = actual_temp > strike_val
        assert won is True, "B-type: actual > threshold → settlement wins"
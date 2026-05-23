"""Tests for V3 Kalshi weather ticker parser."""
from __future__ import annotations

import pytest

from experiments.v3.ticker_parser import ParseError, is_high_temp, parse_ticker


class TestAllTenV3Tickers:
    """Verify each of the 10 V3 example tickers parses exactly as specified."""

    def test_aus_26apr01_b90_5(self) -> None:
        result = parse_ticker("KXHIGHAUS-26APR01-B90.5")
        assert result["city"] == "Austin"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 90.5
        assert result["floor"] == 90
        assert result["ceiling"] == 91
        assert result["date"] == "2026-04-01"

    def test_tsea_26may07_t66(self) -> None:
        result = parse_ticker("KXHIGHTSEA-26MAY07-T66")
        assert result["city"] == "Seattle"
        assert result["strike_type"] == "less"
        assert result["threshold"] == 66.0
        assert result["floor"] is None
        assert result["ceiling"] is None
        assert result["date"] == "2026-05-07"

    def test_tsea_26may11_t75(self) -> None:
        result = parse_ticker("KXHIGHTSEA-26MAY11-T75")
        assert result["city"] == "Seattle"
        assert result["strike_type"] == "greater"
        assert result["threshold"] == 75.0
        assert result["floor"] is None
        assert result["ceiling"] is None
        assert result["date"] == "2026-05-11"

    def test_nyc_26may08_t64(self) -> None:
        result = parse_ticker("KXHIGHNYC-26MAY08-T64")
        assert result["city"] == "NYC"
        assert result["strike_type"] == "less"
        assert result["threshold"] == 64.0
        assert result["floor"] is None
        assert result["ceiling"] is None
        assert result["date"] == "2026-05-08"

    def test_nyc_26jun01_b94_5(self) -> None:
        result = parse_ticker("KXHIGHNYC-26JUN01-B94.5")
        assert result["city"] == "NYC"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 94.5
        assert result["floor"] == 94
        assert result["ceiling"] == 95
        assert result["date"] == "2026-06-01"

    def test_aus_26apr16_b91_5(self) -> None:
        result = parse_ticker("KXHIGHAUS-26APR16-B91.5")
        assert result["city"] == "Austin"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 91.5
        assert result["floor"] == 91
        assert result["ceiling"] == 92
        assert result["date"] == "2026-04-16"

    def test_lvx_26may11_b82_5(self) -> None:
        result = parse_ticker("KXHIGHLVX-26MAY11-B82.5")
        assert result["city"] == "Las Vegas"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 82.5
        assert result["floor"] == 82
        assert result["ceiling"] == 83
        assert result["date"] == "2026-05-11"

    def test_lvx_26jun07_b97_5(self) -> None:
        result = parse_ticker("KXHIGHLVX-26JUN07-B97.5")
        assert result["city"] == "Las Vegas"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 97.5
        assert result["floor"] == 97
        assert result["ceiling"] == 98
        assert result["date"] == "2026-06-07"

    def test_hou_26apr06_b83_5(self) -> None:
        result = parse_ticker("KXHIGHHOU-26APR06-B83.5")
        assert result["city"] == "Houston"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 83.5
        assert result["floor"] == 83
        assert result["ceiling"] == 84
        assert result["date"] == "2026-04-06"

    def test_mia_26may06_b84_5(self) -> None:
        result = parse_ticker("KXHIGHMIA-26MAY06-B84.5")
        assert result["city"] == "Miami"
        assert result["strike_type"] == "between"
        assert result["threshold"] == 84.5
        assert result["floor"] == 84
        assert result["ceiling"] == 85
        assert result["date"] == "2026-05-06"

    def test_geo_fields(self) -> None:
        """Spot-check lat/lon/timezone for one ticker."""
        result = parse_ticker("KXHIGHAUS-26APR01-B90.5")
        assert result["lat"] == pytest.approx(30.27)
        assert result["lon"] == pytest.approx(-97.74)
        assert result["timezone"] == "America/Chicago"


class TestIsHighTemp:
    def test_kxhigh_returns_true(self) -> None:
        assert is_high_temp("KXHIGHAUS-26APR01-B90.5") is True
        assert is_high_temp("KXHIGHTSEA-26MAY07-T66") is True

    def test_kxlow_returns_false(self) -> None:
        assert is_high_temp("KXLOWAUS-26APR01-B90.5") is False
        assert is_high_temp("KXLOWTSEA-26MAY07-T66") is False


class TestErrorCases:
    def test_unknown_city_code(self) -> None:
        with pytest.raises(ParseError, match="Unknown city"):
            parse_ticker("KXHIGHZZZ-26APR01-B90.5")

    def test_malformed_no_strike_prefix(self) -> None:
        with pytest.raises(ParseError, match="Malformed ticker"):
            parse_ticker("KXHIGHAUS-26APR01-99")

    def test_empty_string(self) -> None:
        with pytest.raises(ParseError):
            parse_ticker("")

    def test_non_string(self) -> None:
        with pytest.raises(ParseError):
            parse_ticker(None)  # type: ignore[arg-type]

    def test_malformed_date(self) -> None:
        with pytest.raises(ParseError, match="Malformed ticker"):
            parse_ticker("KXHIGHAUS-BADATE-B90.5")

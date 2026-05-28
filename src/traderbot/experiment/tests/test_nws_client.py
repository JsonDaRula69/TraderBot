"""Tests for city alias resolution — regression coverage.

Verifies _resolve_city(), _CITY_MAP, and _KALSHI_CITY_MAP work correctly
in the weather provider module.
"""

import pytest

from traderbot.data.weather.provider import (
    _CITY_ALIASES,
    _CITY_MAP,
    _KALSHI_CITY_MAP,
    _resolve_city,
)


class TestResolveCity:
    """Verify _resolve_city() maps aliases to canonical names."""

    def test_full_name_passthrough(self) -> None:
        """Full city name resolves to itself."""
        assert _resolve_city("New York") == "New York"
        assert _resolve_city("Chicago") == "Chicago"
        assert _resolve_city("Los Angeles") == "Los Angeles"

    def test_nyc_alias_to_new_york(self) -> None:
        """NYC alias must resolve to New York."""
        assert _resolve_city("NYC") == "New York"

    def test_ny_alias_to_new_york(self) -> None:
        """NY alias must resolve to New York."""
        assert _resolve_city("NY") == "New York"

    def test_la_alias_to_los_angeles(self) -> None:
        """LA alias must resolve to Los Angeles."""
        assert _resolve_city("LA") == "Los Angeles"

    def test_lax_alias_to_los_angeles(self) -> None:
        """LAX alias must resolve to Los Angeles."""
        assert _resolve_city("LAX") == "Los Angeles"

    def test_chi_alias_to_chicago(self) -> None:
        """CHI alias must resolve to Chicago."""
        assert _resolve_city("CHI") == "Chicago"

    def test_sf_alias_to_san_francisco(self) -> None:
        """SF alias must resolve to San Francisco."""
        assert _resolve_city("SF") == "San Francisco"

    def test_sfo_alias_to_san_francisco(self) -> None:
        """SFO alias must resolve to San Francisco."""
        assert _resolve_city("SFO") == "San Francisco"

    def test_dal_alias_to_dallas(self) -> None:
        """DAL alias must resolve to Dallas."""
        assert _resolve_city("DAL") == "Dallas"

    def test_dfw_alias_to_dallas(self) -> None:
        """DFW alias must resolve to Dallas."""
        assert _resolve_city("DFW") == "Dallas"

    def test_unknown_city_returns_none(self) -> None:
        """Unknown city/alias must return None."""
        assert _resolve_city("MARS") is None
        assert _resolve_city("UNKNOWN") is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string input returns None."""
        assert _resolve_city("") is None


class TestCityMap:
    """Verify _CITY_MAP has correct entries and coordinates."""

    def test_city_map_has_expected_cities(self) -> None:
        """_CITY_MAP must contain all expected city entries."""
        expected = {
            "New York",
            "Philadelphia",
            "Phoenix",
            "Minneapolis",
            "Seattle",
            "Chicago",
            "Houston",
            "Los Angeles",
            "Miami",
            "Denver",
            "Atlanta",
            "Boston",
            "Dallas",
            "Detroit",
            "San Francisco",
        }
        assert set(_CITY_MAP.keys()) == expected

    def test_city_map_coordinates_are_floats(self) -> None:
        """All coordinates in _CITY_MAP must be (float, float) tuples."""
        for city, coords in _CITY_MAP.items():
            assert isinstance(coords, tuple), f"{city}: expected tuple, got {type(coords)}"
            assert len(coords) == 2, f"{city}: expected 2 coords, got {len(coords)}"
            assert isinstance(coords[0], float), f"{city}: lat must be float"
            assert isinstance(coords[1], float), f"{city}: lon must be float"

    def test_latitudes_in_valid_range(self) -> None:
        """US city latitudes must be in range [25, 50]."""
        for city, (lat, lon) in _CITY_MAP.items():
            assert 25.0 <= lat <= 50.0, f"{city}: lat {lat} out of range"

    def test_longitudes_in_valid_range(self) -> None:
        """US city longitudes must be in range [-125, -70]."""
        for city, (lat, lon) in _CITY_MAP.items():
            assert -125.0 <= lon <= -70.0, f"{city}: lon {lon} out of range"


class TestKalshiCityMap:
    """Verify _KALSHI_CITY_MAP ticker prefixes map correctly."""

    def test_kalshi_map_has_all_expected_tickers(self) -> None:
        """_KALSHI_CITY_MAP must contain all expected Kalshi ticker prefixes."""
        expected_tickers = {
            "KXHIGHNY",
            "KXHIGHPHIL",
            "KXHIGHTPHX",
            "KXHIGHTMIN",
            "KXHIGHTSEA",
            "KXHIGHTCHI",
            "KXHIGHTLA",
            "KXHIGHTMIA",
            "KXHIGHTDEN",
            "KXHIGHTATL",
            "KXHIGHTBOS",
            "KXHIGHTDAL",
            "KXHIGHTDET",
            "KXHIGHTSF",
            "KXHIGHTHOU",
        }
        assert set(_KALSHI_CITY_MAP.keys()) == expected_tickers

    def test_kalshi_entries_are_4_tuples(self) -> None:
        """Each _KALSHI_CITY_MAP entry must be (city_name, lat, lon, timezone)."""
        for ticker, entry in _KALSHI_CITY_MAP.items():
            assert isinstance(entry, tuple), f"{ticker}: expected tuple"
            assert len(entry) == 4, f"{ticker}: expected 4 fields, got {len(entry)}"
            name, lat, lon, tz = entry
            assert isinstance(name, str), f"{ticker}: name must be str"
            assert isinstance(lat, float), f"{ticker}: lat must be float"
            assert isinstance(lon, float), f"{ticker}: lon must be float"
            assert isinstance(tz, str), f"{ticker}: tz must be str"
            assert "/" in tz, f"{ticker}: tz must contain region (e.g. America/Chicago)"

    def test_kalshi_map_resolves_via_resolve_city(self) -> None:
        """_KALSHI_CITY_MAP ticker prefixes must resolve via _resolve_city()."""
        ticker_name_map = {
            "KXHIGHNY": "New York",
            "KXHIGHTCHI": "Chicago",
            "KXHIGHTLA": "Los Angeles",
            "KXHIGHTSF": "San Francisco",
        }
        for prefix, expected_name in ticker_name_map.items():
            assert _resolve_city(prefix) == expected_name, (
                f"{prefix} should resolve to {expected_name}"
            )

    def test_kalshi_coords_match_city_map(self) -> None:
        """Coordinates in _KALSHI_CITY_MAP must match _CITY_MAP for each city."""
        for ticker, (name, klat, klon, _tz) in _KALSHI_CITY_MAP.items():
            assert name in _CITY_MAP, (
                f"Kalshi city '{name}' (from {ticker}) not in _CITY_MAP"
            )
            cmap_lat, cmap_lon = _CITY_MAP[name]
            assert klat == cmap_lat, (
                f"{name}: Kalshi lat {klat} != CITY_MAP lat {cmap_lat}"
            )
            assert klon == cmap_lon, (
                f"{name}: Kalshi lon {klon} != CITY_MAP lon {cmap_lon}"
            )


class TestCityAliases:
    """Verify _CITY_ALIASES mappings."""

    def test_all_aliases_resolve_to_valid_cities(self) -> None:
        """Every alias in _CITY_ALIASES must resolve to a city in _CITY_MAP."""
        for alias, full_name in _CITY_ALIASES.items():
            assert full_name in _CITY_MAP, (
                f"Alias '{alias}' maps to '{full_name}' which is not in _CITY_MAP"
            )

    def test_aliases_are_uppercase(self) -> None:
        """All alias keys must be uppercase for consistency."""
        for alias in _CITY_ALIASES:
            assert alias == alias.upper(), f"Alias '{alias}' is not uppercase"

    def test_nyc_chi_la_have_aliases(self) -> None:
        """Key aliases exist for NYC→New York, CHI→Chicago, LA→Los Angeles."""
        assert _CITY_ALIASES["NYC"] == "New York"
        assert _CITY_ALIASES["CHI"] == "Chicago"
        assert _CITY_ALIASES["LA"] == "Los Angeles"

    def test_alias_resolve_via_resolve_city(self) -> None:
        """All aliases must be resolvable via _resolve_city()."""
        for alias, expected_city in _CITY_ALIASES.items():
            resolved = _resolve_city(alias)
            assert resolved == expected_city, (
                f"_resolve_city({alias!r}) = {resolved!r}, expected {expected_city!r}"
            )

    def test_full_name_also_resolves(self) -> None:
        """Full city names also resolve correctly via _resolve_city()."""
        for alias, full_name in _CITY_ALIASES.items():
            assert _resolve_city(full_name) == full_name

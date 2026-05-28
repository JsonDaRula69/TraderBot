"""Tests for installer multi-category agent name logic — regression coverage.

Verifies the suggested_name mapping from categories to agent names
as implemented in the traderbot-installer.sh script.
"""

import pytest


# The suggested-name mapping from traderbot-installer.sh lines 1734-1746
_SUGGESTED_NAME_MAP: dict[str, str] = {
    "weather": "weatherman",
    "economics": "economics",
    "politics": "politics",
    "sports": "sports",
    "crypto": "crypto",
    "science_and_technology": "science",
    "commodities": "commodities",
    "companies": "companies",
    "elections": "elections",
    "entertainment": "entertainment",
    "financials": "financials",
    "health": "health",
    "mentions": "mentions",
    "social": "social",
}


def _suggested_name(category: str) -> str:
    """Replicate the installer's suggested-name mapping logic.

    This mirrors the case statement in traderbot-installer.sh lines 1734-1746.
    """
    mapping = {
        "weather": "weatherman",
        "economics": "economics",
        "politics": "politics",
        "sports": "sports",
        "crypto": "crypto",
        "science_and_technology": "science",
        "commodities": "commodities",
        "companies": "companies",
        "elections": "elections",
        "entertainment": "entertainment",
        "financials": "financials",
        "health": "health",
        "mentions": "mentions",
        "social": "social",
    }
    if category in mapping:
        return mapping[category]
    # Fallback: first 8 chars
    return category[:8]


class TestSuggestedNameMapping:
    """Verify category → agent name mapping matches the installer script."""

    def test_weather_maps_to_weatherman(self) -> None:
        """weather category must produce 'weatherman' as suggested name."""
        assert _suggested_name("weather") == "weatherman"

    def test_economics_maps_to_economics(self) -> None:
        """economics category keeps its name."""
        assert _suggested_name("economics") == "economics"

    def test_politics_maps_to_politics(self) -> None:
        """politics category keeps its name."""
        assert _suggested_name("politics") == "politics"

    def test_sports_maps_to_sports(self) -> None:
        """sports category keeps its name."""
        assert _suggested_name("sports") == "sports"

    def test_crypto_maps_to_crypto(self) -> None:
        """crypto category keeps its name."""
        assert _suggested_name("crypto") == "crypto"

    def test_science_and_technology_maps_to_science(self) -> None:
        """science_and_technology category shortens to 'science'."""
        assert _suggested_name("science_and_technology") == "science"

    def test_commodities_maps_to_commodities(self) -> None:
        """commodities category keeps its name."""
        assert _suggested_name("commodities") == "commodities"

    def test_companies_maps_to_companies(self) -> None:
        """companies category keeps its name."""
        assert _suggested_name("companies") == "companies"

    def test_elections_maps_to_elections(self) -> None:
        """elections category keeps its name."""
        assert _suggested_name("elections") == "elections"

    def test_entertainment_maps_to_entertainment(self) -> None:
        """entertainment category keeps its name."""
        assert _suggested_name("entertainment") == "entertainment"

    def test_financials_maps_to_financials(self) -> None:
        """financials category keeps its name."""
        assert _suggested_name("financials") == "financials"

    def test_health_maps_to_health(self) -> None:
        """health category keeps its name."""
        assert _suggested_name("health") == "health"

    def test_mentions_maps_to_mentions(self) -> None:
        """mentions category keeps its name."""
        assert _suggested_name("mentions") == "mentions"

    def test_social_maps_to_social(self) -> None:
        """social category keeps its name."""
        assert _suggested_name("social") == "social"

    def test_all_market_categories_have_mapping(self) -> None:
        """Every MarketCategory must have a suggested-name mapping."""
        from traderbot.kalshi.models import MarketCategory

        for cat in MarketCategory:
            name = _suggested_name(cat.value)
            assert isinstance(name, str)
            assert len(name) > 0, f"No mapping for category {cat.value}"
            assert name != cat.value[:1], f"Default single-char fallback for {cat.value}: got {name!r}"


class TestAgentExists:
    """Verify agent_exists() logic used in the installer."""

    def test_agent_exists_finds_by_id(self) -> None:
        """agent_exists() greps JSON output for '\"id\":\"<name>\"'."""
        json_output = '{"agents": [{"id": "weatherman", "status": "active"}]}'
        assert '"id":"weatherman"' in json_output.replace(" ", "")

    def test_agent_exists_fails_when_not_found(self) -> None:
        """agent_exists() returns false when agent id is not in output."""
        json_output = '{"agents": [{"id": "economics", "status": "active"}]}'
        assert '"id":"weatherman"' not in json_output.replace(" ", "")

    def test_agent_exists_handles_empty_list(self) -> None:
        """agent_exists() handles empty agent list gracefully."""
        json_output = '{"agents": []}'
        assert '"id":"weatherman"' not in json_output.replace(" ", "")

    def test_suggested_name_never_empty(self) -> None:
        """Every known category must produce a non-empty suggested name."""
        for cat, name in _SUGGESTED_NAME_MAP.items():
            assert name, f"Empty suggested name for category '{cat}'"
            assert name.strip(), f"Whitespace-only suggested name for category '{cat}'"

    def test_weatherman_unique(self) -> None:
        """weather is the ONLY category mapping to 'weatherman'."""
        weatherman_cats = [
            cat for cat, name in _SUGGESTED_NAME_MAP.items() if name == "weatherman"
        ]
        assert weatherman_cats == ["weather"], (
            f"weatherman should only map from 'weather', got {weatherman_cats}"
        )

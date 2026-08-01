"""Tests for unified MarketCategory enum across modules."""

from traderbot.kalshi.models import MarketCategory
from traderbot.news.models import NewsCategory
from traderbot.simulation.adaptation import MarketCategory as AdaptationMarketCategory


class TestMarketCategoryValues:
    """MarketCategory values are lowercase strings matching name.lower()."""

    def test_all_values_are_lowercase(self) -> None:
        for member in MarketCategory:
            assert member.value == member.value.lower(), (
                f"{member.name} value {member.value!r} is not lowercase"
            )

    def test_all_values_match_name_lower(self) -> None:
        for member in MarketCategory:
            assert member.value == member.name.lower(), (
                f"{member.name}.value != {member.name!r}.lower()"
            )

    def test_known_members(self) -> None:
        assert MarketCategory.ECONOMICS.value == "economics"
        assert MarketCategory.POLITICS.value == "politics"
        assert MarketCategory.WEATHER.value == "weather"
        assert MarketCategory.SPORTS.value == "sports"
        assert MarketCategory.SCIENCE_AND_TECHNOLOGY.value == "science_and_technology"
        assert MarketCategory.CRYPTO.value == "crypto"
        assert MarketCategory.COMMODITIES.value == "commodities"
        assert MarketCategory.COMPANIES.value == "companies"
        assert MarketCategory.ELECTIONS.value == "elections"
        assert MarketCategory.ENTERTAINMENT.value == "entertainment"
        assert MarketCategory.FINANCIALS.value == "financials"
        assert MarketCategory.HEALTH.value == "health"
        assert MarketCategory.MENTIONS.value == "mentions"
        assert MarketCategory.SOCIAL.value == "social"


class TestNewsCategoryAlias:
    """NewsCategory is a backward-compatible alias for MarketCategory."""

    def test_news_category_is_market_category(self) -> None:
        assert NewsCategory is MarketCategory

    def test_news_category_has_same_members(self) -> None:
        assert set(NewsCategory.__members__.keys()) == set(
            MarketCategory.__members__.keys()
        )

    def test_news_category_values_match(self) -> None:
        for name, member in MarketCategory.__members__.items():
            assert NewsCategory[name].value == member.value


class TestMarketCategoryLowercase:
    """Every MarketCategory value must be lowercase."""

    def test_all_values_lowercase(self) -> None:
        for member in MarketCategory:
            assert member.value == member.value.lower(), (
                f"{member.name} value {member.value!r} is not lowercase"
            )

    def test_specific_lowercase_values(self) -> None:
        assert MarketCategory.ECONOMICS.value == "economics"
        assert MarketCategory.POLITICS.value == "politics"
        assert MarketCategory.SCIENCE_AND_TECHNOLOGY.value == "science_and_technology"
        assert MarketCategory.HEALTH.value == "health"
        assert MarketCategory.CRYPTO.value == "crypto"


class TestMarketCategoryEnumCompleteness:
    """Verify MarketCategory has the expected categories."""

    EXPECTED_CATEGORIES = {
        "ECONOMICS", "POLITICS", "SCIENCE_AND_TECHNOLOGY", "WEATHER",
        "SPORTS", "CRYPTO", "COMMODITIES", "COMPANIES", "ELECTIONS",
        "ENTERTAINMENT", "FINANCIALS", "HEALTH", "MENTIONS", "SOCIAL",
    }

    def test_expected_categories_present(self) -> None:
        member_names = set(MarketCategory.__members__.keys())
        for expected in self.EXPECTED_CATEGORIES:
            assert expected in member_names, f"{expected} missing from MarketCategory"

    def test_news_category_is_market_category_identity(self) -> None:
        assert NewsCategory is MarketCategory

    def test_news_category_identity_not_just_equal(self) -> None:
        """Verify NewsCategory IS MarketCategory (identity, not just equality)."""
        assert NewsCategory is MarketCategory
        assert NewsCategory.ECONOMICS is MarketCategory.ECONOMICS


class TestAdaptationImport:
    """Importing MarketCategory from adaptation gives kalshi version."""

    def test_adaptation_import_is_same_class(self) -> None:
        assert AdaptationMarketCategory is MarketCategory

    def test_adaptation_member_access(self) -> None:
        assert AdaptationMarketCategory.ECONOMICS is MarketCategory.ECONOMICS
        assert AdaptationMarketCategory.POLITICS is MarketCategory.POLITICS
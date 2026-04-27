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
        assert MarketCategory.CULTURE.value == "culture"
        assert MarketCategory.TECHNOLOGY.value == "technology"
        assert MarketCategory.SCIENCE.value == "science"
        assert MarketCategory.TECH.value == "tech"
        assert MarketCategory.CRYPTO.value == "crypto"


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


class TestAdaptationImport:
    """Importing MarketCategory from adaptation gives kalshi version."""

    def test_adaptation_import_is_same_class(self) -> None:
        assert AdaptationMarketCategory is MarketCategory

    def test_adaptation_member_access(self) -> None:
        assert AdaptationMarketCategory.ECONOMICS is MarketCategory.ECONOMICS
        assert AdaptationMarketCategory.POLITICS is MarketCategory.POLITICS
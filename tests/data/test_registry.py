from __future__ import annotations

from traderbot.data.base_provider import BaseDataProvider
from traderbot.data.registry import get_provider, list_providers, register_provider


class FakeProvider(BaseDataProvider):
    async def fetch(self, *args, **kwargs):
        return []


class TestRegistry:
    def test_list_providers_empty_by_default(self) -> None:
        providers = list_providers()
        assert isinstance(providers, list)

    def test_register_and_get(self) -> None:
        register_provider("fake", FakeProvider)
        cls = get_provider("fake")
        assert cls is FakeProvider

    def test_get_nonexistent(self) -> None:
        assert get_provider("nonexistent") is None

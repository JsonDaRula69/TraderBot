"""ProviderRegistry — lookup of BaseDataProvider classes (DD-028).

Ports the retired ``traderbot.data.registry`` module as a class so tests and
the pipeline can hold isolated registries instead of a process-global dict.
"""

from __future__ import annotations

import logging

from traderbot.data.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry mapping provider names to provider classes.

    Stores classes, not instances: the caller instantiates and passes a
    concrete provider to the :class:`~traderbot.data.pipeline.DataCollectionService`.
    """

    def __init__(self) -> None:
        self._classes: dict[str, type[BaseDataProvider]] = {}

    def register(self, name: str, cls: type[BaseDataProvider]) -> None:
        """Register a provider class under ``name``.

        Args:
            name: Logical provider name (e.g., "open-meteo", "nws").
            cls: Provider class that subclasses :class:`BaseDataProvider`.

        Raises:
            TypeError: if ``cls`` does not subclass :class:`BaseDataProvider`.
            ValueError: if ``name`` is already registered.
        """
        if not issubclass(cls, BaseDataProvider):
            raise TypeError(f"Provider {cls.__name__} must subclass BaseDataProvider")
        if name in self._classes:
            raise ValueError(f"Provider {name!r} is already registered")
        self._classes[name] = cls
        logger.info("Registered provider %r -> %s", name, cls.__name__)

    def get(self, name: str) -> type[BaseDataProvider] | None:
        """Return the registered class for ``name``, or None if not found."""
        return self._classes.get(name)

    def list_names(self) -> list[str]:
        """Return sorted names of all registered providers."""
        return sorted(self._classes)


def build_default_registry() -> ProviderRegistry:
    """Build a registry pre-loaded with the Phase 2 bundled providers.

    Registers the weather providers (open-meteo, nws), the news ingest stub,
    and the settlement monitor. ``settlement-monitor`` requires a
    :class:`~traderbot.kalshi.client.KalshiClient` at instantiation, so callers
    construct it from a configured client before running the pipeline.
    """
    from traderbot.data.providers.news import NewsProvider
    from traderbot.data.providers.nws import NwsProvider
    from traderbot.data.providers.open_meteo import OpenMeteoProvider
    from traderbot.data.providers.settlement import SettlementMonitor

    registry = ProviderRegistry()
    registry.register("open-meteo", OpenMeteoProvider)
    registry.register("nws", NwsProvider)
    registry.register("news", NewsProvider)
    registry.register("settlement-monitor", SettlementMonitor)
    return registry

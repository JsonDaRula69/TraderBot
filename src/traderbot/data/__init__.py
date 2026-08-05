"""Unified data collection package (DD-028).

Provides the :class:`BaseDataProvider` ABC, the :class:`RateLimiter` asyncio
primitive, the :class:`DataScheduler` task manager, the
:class:`ProviderRegistry`, and the :class:`DataCollectionService` pipeline
orchestrator. Specific providers live under ``traderbot.data.providers``.
"""

from traderbot.data.base_provider import BaseDataProvider, RateLimiter
from traderbot.data.pipeline import DataCollectionService
from traderbot.data.registry import ProviderRegistry
from traderbot.data.scheduler import DataScheduler

__all__ = [
    "BaseDataProvider",
    "DataCollectionService",
    "DataScheduler",
    "ProviderRegistry",
    "RateLimiter",
]

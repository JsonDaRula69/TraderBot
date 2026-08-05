"""DataCollectionService — always-on data pipeline orchestrator (DD-016, DD-028).

TraderBot fetches data on a schedule; agents query local storage. This
service registers provider instances, schedules each one's worker loop as an
independent asyncio task, and stops them gracefully. A failing provider is
isolated inside its own task: it logs and retries without affecting the
others. Standalone — not coupled to the MCP server.
"""

from __future__ import annotations

import logging

from traderbot.data.base_provider import BaseDataProvider
from traderbot.data.scheduler import DataScheduler

logger = logging.getLogger(__name__)


class DataCollectionService:
    """Orchestrates the lifecycle of all registered data providers.

    ``register`` collects providers; ``start`` schedules each provider's
    worker loop as its own asyncio task; ``stop`` cancels them gracefully;
    ``status`` reports per-provider health.
    """

    def __init__(self, scheduler: DataScheduler | None = None) -> None:
        self._scheduler: DataScheduler = scheduler if scheduler is not None else DataScheduler()
        #: Provider name -> provider instance, in registration order.
        self._providers: dict[str, BaseDataProvider] = {}

    def register(self, provider: BaseDataProvider) -> None:
        """Register a provider instance.

        Raises:
            ValueError: if a provider with the same name is already registered.
        """
        if provider.name in self._providers:
            raise ValueError(f"Provider {provider.name!r} is already registered")
        self._providers[provider.name] = provider
        logger.info("Registered provider instance %r", provider.name)

    def registered_names(self) -> list[str]:
        """Return sorted names of all registered providers."""
        return sorted(self._providers)

    @property
    def is_running(self) -> bool:
        """True while any registered provider has a live worker task."""
        return any(self._scheduler.is_running(name) for name in self._providers)

    async def start(self) -> None:
        """Schedule every registered provider (idempotent per provider)."""
        for provider in self._providers.values():
            await self._scheduler.start(provider)
        logger.info("Data collection started for %d providers", len(self._providers))

    async def stop(self) -> None:
        """Cancel every provider task and await completion (no-op if never started)."""
        await self._scheduler.stop_all()
        logger.info("Data collection stopped")

    def status(self) -> dict[str, dict[str, object]]:
        """Return a per-provider status snapshot keyed by provider name."""
        statuses: dict[str, dict[str, object]] = {}
        for name, provider in self._providers.items():
            statuses[name] = {
                "running": self._scheduler.is_running(name),
                "interval_seconds": provider.interval_seconds,
                "last_run_at": provider.last_run_at,
                "last_error": provider.last_error,
                "total_runs": provider.total_runs,
                "total_errors": provider.total_errors,
            }
        return statuses

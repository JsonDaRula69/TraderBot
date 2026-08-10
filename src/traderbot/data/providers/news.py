"""News ingest provider — Phase 2 stub (DD-028).

Reserves the 30-minute news slot in the scheduler. The full news pipeline
(NewsAPI + Reddit + Twitter fetch, embedding, ChromaDB storage) is deferred
to a later phase; this provider records its placeholder run and returns an
empty payload so the scheduler exercises the slot end-to-end.
"""

from __future__ import annotations

import logging
from typing import Any, override

from traderbot.data.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

_NEWS_INTERVAL_SECONDS: float = 30.0 * 60.0  # 30 minutes


class NewsProvider(BaseDataProvider):
    """Placeholder news provider (no external API calls in Phase 2)."""

    def __init__(self) -> None:
        super().__init__()
        self._stub_runs: int = 0

    @property
    @override
    def name(self) -> str:
        return "news"

    @property
    @override
    def interval_seconds(self) -> float:
        return _NEWS_INTERVAL_SECONDS

    @override
    async def fetch(self) -> dict[str, Any]:
        self._stub_runs += 1
        logger.info("news ingest not yet implemented (Phase 2 stub)")
        return {"stub": True, "runs": self._stub_runs}

    @override
    async def insert(self, data: dict[str, Any]) -> int:
        return 0


__all__ = ["NewsProvider"]

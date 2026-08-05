"""Weather data providers for the always-on data pipeline (DD-028).

Subclasses of :class:`~traderbot.data.base_provider.BaseDataProvider` that fetch
weather observations/forecasts from external sources on a schedule and persist
them to the global TraderBot SQLite database. Agents query these snapshots
locally — the pipeline never serves data on-demand (DD-016).
"""

from traderbot.data.providers.news import NewsProvider
from traderbot.data.providers.nws import NwsProvider
from traderbot.data.providers.open_meteo import OpenMeteoProvider
from traderbot.data.providers.settlement import SettlementMonitor

__all__ = [
    "NewsProvider",
    "NwsProvider",
    "OpenMeteoProvider",
    "SettlementMonitor",
]

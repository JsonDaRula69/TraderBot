"""Provider registry for auto-discovery and lookup of BaseDataProvider implementations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.data.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

_registry: dict[str, type[BaseDataProvider]] = {}


def register_provider(name: str, cls: type[BaseDataProvider]) -> None:
    """Register a data provider class under a logical name.

    Args:
        name: Logical provider name (e.g., "open-meteo", "nws").
        cls: Provider class that subclasses BaseDataProvider.

    Raises:
        TypeError: If cls does not subclass BaseDataProvider.
    """
    from traderbot.data.base_provider import BaseDataProvider

    if not issubclass(cls, BaseDataProvider):
        raise TypeError(
            f"Provider {cls.__name__} must subclass BaseDataProvider"
        )
    _registry[name] = cls
    logger.info("Registered provider '%s' -> %s", name, cls.__name__)


def get_provider(name: str) -> type[BaseDataProvider] | None:
    """Look up a registered provider by name.

    Args:
        name: Logical provider name.

    Returns:
        The provider class if found, or None.
    """
    return _registry.get(name)


def list_providers() -> list[str]:
    """Return sorted list of registered provider names."""
    return sorted(_registry.keys())

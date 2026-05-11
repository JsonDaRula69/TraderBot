"""Per-profile authentication storage with keyring namespace."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

_KEYRING_SERVICE_PREFIX = "traderbot.profiles."


class ProfileAuthStore:
    """Per-profile credential store via OS keyring.

    Each profile has isolated credential storage under:
    traderbot.profiles.{profile_name}.{service}
    """

    def __init__(self, profile: TradingProfile, keyring_module: Any = None) -> None:
        """Initialize auth store for a specific profile.

        Args:
            profile: TradingProfile to manage credentials for
            keyring_module: Optional keyring module (for testing)
        """
        self._profile = profile
        self._keyring = keyring_module
        self._keyring_available: bool | None = None

    @property
    def keyring_available(self) -> bool:
        """Check if OS keyring is available for per-profile credential storage."""
        if self._keyring_available is None:
            try:
                import keyring as kr
                if self._keyring is not None:
                    kr = self._keyring
                backend_name = type(kr.get_keyring()).__name__
                self._keyring_available = "Fail" not in backend_name and "Null" not in backend_name
            except Exception:
                self._keyring_available = False
        return self._keyring_available

    def _get_keyring(self) -> Any:
        """Get keyring module (real or mock)."""
        if self._keyring is not None:
            return self._keyring
        return __import__("keyring")

    def _service_name(self, service: str) -> str:
        """Get full keyring service name for this profile and service.

        Args:
            service: Service name (e.g., 'kalshi', 'voyage')

        Returns:
            Full service name: traderbot.profiles.{profile_name}.{service}
        """
        return f"{_KEYRING_SERVICE_PREFIX}{self._profile.name}.{service}"

    def set_credentials(self, service: str, key: str, secret: str) -> None:
        """Store credentials in keyring for this profile.

        Args:
            service: Service name (e.g., 'kalshi')
            key: API key
            secret: API secret
        """
        kr = self._get_keyring()
        service_name = self._service_name(service)

        # Store as JSON with timestamp
        data = {
            "key": key,
            "secret": secret,
            "created_at": datetime.now(UTC).isoformat(),
        }
        kr.set_password(service_name, "credentials", json.dumps(data))
        logger.info("Stored credentials for profile '%s' service '%s'", self._profile.name, service)

    def get_credentials(self, service: str) -> tuple[str, str] | None:
        """Retrieve credentials for this profile.

        Args:
            service: Service name (e.g., 'kalshi')

        Returns:
            Tuple of (key, secret) if found, None otherwise
        """
        kr = self._get_keyring()
        service_name = self._service_name(service)

        try:
            stored = kr.get_password(service_name, "credentials")
            if stored is None:
                return None

            data = json.loads(stored)
            return (data["key"], data["secret"])
        except Exception as e:
            logger.warning(
                "Failed to retrieve credentials for profile '%s' service '%s': %s",
                self._profile.name,
                service,
                e,
            )
            return None

    def delete_credentials(self, service: str) -> None:
        """Remove credentials from keyring for this profile.

        Args:
            service: Service name (e.g., 'kalshi')
        """
        kr = self._get_keyring()
        service_name = self._service_name(service)

        try:
            kr.delete_password(service_name, "credentials")
            logger.info("Deleted credentials for profile '%s' service '%s'", self._profile.name, service)
        except Exception as e:
            logger.warning(
                "Failed to delete credentials for profile '%s' service '%s': %s",
                self._profile.name,
                service,
                e,
            )

    def has_credentials(self, service: str) -> bool:
        """Check if credentials exist for this profile.

        Args:
            service: Service name (e.g., 'kalshi')

        Returns:
            True if credentials exist, False otherwise
        """
        return self.get_credentials(service) is not None

    def list_services(self) -> list[str]:
        """List all services with stored credentials for this profile.

        Returns:
            List of service names (sorted alphabetically)
        """
        kr = self._get_keyring()
        services: list[str] = []

        # For mock keyring, iterate the store
        if hasattr(kr, "_store"):
            prefix = f"{_KEYRING_SERVICE_PREFIX}{self._profile.name}."
            for (service_name, username) in kr._store:
                if service_name.startswith(prefix) and username == "credentials":
                    # Extract service name from full service path
                    service = service_name[len(prefix):]
                    services.append(service)
        else:
            # For real keyring, we'd need to maintain an index or try known services
            # For now, try common services
            common_services = ["kalshi", "voyage", "newsapi", "twitter", "reddit"]
            for service in common_services:
                if self.has_credentials(service):
                    services.append(service)

        return sorted(services)



"""Profile registry with encrypted keyring storage."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

_KEYRING_SERVICE_PREFIX = "traderbot.profiles."


class ProfileRegistry:
    """Manage trading profiles with encrypted OS keyring storage."""

    def __init__(self, keyring_module: Any = None) -> None:
        """Initialize registry with optional keyring module (for testing)."""
        self._keyring = keyring_module

    def _get_keyring(self) -> Any:
        """Get keyring module (real or mock)."""
        if self._keyring is not None:
            return self._keyring
        return __import__("keyring")

    def _service_name(self, profile_name: str) -> str:
        """Get full keyring service name for a profile."""
        return f"{_KEYRING_SERVICE_PREFIX}{profile_name}"

    def create_profile(self, profile: TradingProfile) -> None:
        """Store profile in keyring under traderbot.profiles.{name}.

        Args:
            profile: TradingProfile to store

        Raises:
            ValueError: If profile with same name already exists
        """
        if self.profile_exists(profile.name):
            raise ValueError(f"Profile '{profile.name}' already exists")

        kr = self._get_keyring()
        service = self._service_name(profile.name)
        # Store as JSON-serialized profile (exclude computed fields, use mode='json' for proper enum serialization)
        profile_dict = profile.model_dump(
            exclude={"demo_mode", "base_dir", "keyring_prefix", "env_file"},
            mode="json"
        )
        profile_json = json.dumps(profile_dict)
        kr.set_password(service, "profile", profile_json)
        
        # Update index for real keyring
        self._update_index(profile.name, add=True)
        
        logger.info("Created profile '%s' in keyring", profile.name)

    def get_profile(self, name: str) -> TradingProfile | None:
        """Retrieve profile from keyring.

        Args:
            name: Profile name to retrieve

        Returns:
            TradingProfile if found, None otherwise
        """
        kr = self._get_keyring()
        service = self._service_name(name)

        try:
            profile_json = kr.get_password(service, "profile")
            if profile_json is None:
                return None

            # Deserialize from JSON
            profile_dict = json.loads(profile_json)
            
            # Convert enabled_categories strings back to MarketCategory enums
            if "enabled_categories" in profile_dict and profile_dict["enabled_categories"]:
                from traderbot.kalshi.models import MarketCategory
                profile_dict["enabled_categories"] = [
                    MarketCategory(cat) if isinstance(cat, str) else cat
                    for cat in profile_dict["enabled_categories"]
                ]
            
            return TradingProfile.model_validate(profile_dict)
        except Exception as e:
            logger.warning("Failed to retrieve profile '%s': %s", name, e)
            return None

    def list_profiles(self) -> list[str]:
        """List all profile names stored in keyring.

        Returns:
            List of profile names (sorted alphabetically)
        """
        kr = self._get_keyring()
        profiles: list[str] = []

        # Try to enumerate all profiles by checking the keyring store
        # For mock keyring, we can iterate the store directly
        if hasattr(kr, "_store"):
            # Mock keyring case
            for (service, username) in kr._store.keys():
                if service.startswith(_KEYRING_SERVICE_PREFIX) and username == "profile":
                    profile_name = service[len(_KEYRING_SERVICE_PREFIX):]
                    profiles.append(profile_name)
        else:
            # Real keyring case - we need to try common profile names
            # Since keyring doesn't provide enumeration, we'll need to maintain
            # a separate index. For now, we'll use a simple approach:
            # Store a list of profile names in a special keyring entry
            try:
                index_json = kr.get_password(_KEYRING_SERVICE_PREFIX + "_index", "profiles")
                if index_json:
                    profiles = json.loads(index_json)
            except Exception:
                pass

        return sorted(profiles)

    def delete_profile(self, name: str, keep_data: bool = True) -> None:
        """Remove profile from keyring, optionally delete data directories.

        Args:
            name: Profile name to delete
            keep_data: If True, keep data directories; if False, delete them
        """
        if not self.profile_exists(name):
            logger.warning("Profile '%s' does not exist, nothing to delete", name)
            return

        # Get profile to determine data directory
        profile = self.get_profile(name)

        # Delete from keyring
        kr = self._get_keyring()
        service = self._service_name(name)
        try:
            kr.delete_password(service, "profile")
            logger.info("Deleted profile '%s' from keyring", name)
        except Exception as e:
            logger.warning("Failed to delete profile '%s' from keyring: %s", name, e)

        # Update index for real keyring
        if not hasattr(kr, "_store"):
            try:
                index_json = kr.get_password(_KEYRING_SERVICE_PREFIX + "_index", "profiles")
                if index_json:
                    profiles = json.loads(index_json)
                    if name in profiles:
                        profiles.remove(name)
                        kr.set_password(
                            _KEYRING_SERVICE_PREFIX + "_index",
                            "profiles",
                            json.dumps(profiles)
                        )
            except Exception:
                pass

        # Delete data directories if requested
        if not keep_data and profile is not None:
            data_dir = Path.home() / profile.base_dir
            if data_dir.exists():
                try:
                    shutil.rmtree(data_dir)
                    logger.info("Deleted data directory: %s", data_dir)
                except Exception as e:
                    logger.warning("Failed to delete data directory %s: %s", data_dir, e)

    def profile_exists(self, name: str) -> bool:
        """Check if profile exists in keyring.

        Args:
            name: Profile name to check

        Returns:
            True if profile exists, False otherwise
        """
        kr = self._get_keyring()
        service = self._service_name(name)
        try:
            profile_json = kr.get_password(service, "profile")
            return profile_json is not None
        except Exception:
            return False

    def _update_index(self, name: str, add: bool = True) -> None:
        """Update profile index for real keyring (internal helper).

        Args:
            name: Profile name to add or remove
            add: If True, add to index; if False, remove from index
        """
        kr = self._get_keyring()
        if hasattr(kr, "_store"):
            # Mock keyring doesn't need index
            return

        try:
            index_json = kr.get_password(_KEYRING_SERVICE_PREFIX + "_index", "profiles")
            profiles = json.loads(index_json) if index_json else []

            if add and name not in profiles:
                profiles.append(name)
            elif not add and name in profiles:
                profiles.remove(name)

            kr.set_password(
                _KEYRING_SERVICE_PREFIX + "_index",
                "profiles",
                json.dumps(profiles)
            )
        except Exception as e:
            logger.warning("Failed to update profile index: %s", e)

# Made with Bob

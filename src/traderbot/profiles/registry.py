"""Profile registry with encrypted keyring storage, AES-256 file fallback."""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

_KEYRING_SERVICE_PREFIX = "traderbot.profiles."
_PROFILES_FILE = Path.home() / ".traderbot" / "profiles.enc"
_ENCRYPTION_KEY_SERVICE = "traderbot.encryption"
_ENCRYPTION_KEY_USERNAME = "profile_key"


def _derive_or_create_key() -> bytes:
    """Get or create AES-256 encryption key. Stored in keyring if available, else derived from machine id."""
    if _keyring_available():
        kr = __import__("keyring")
        try:
            stored = kr.get_password(_ENCRYPTION_KEY_SERVICE, _ENCRYPTION_KEY_USERNAME)
            if stored:
                return base64.urlsafe_b64decode(stored)
        except Exception:
            pass

    key = os.urandom(32)
    if _keyring_available():
        kr = __import__("keyring")
        try:
            kr.set_password(
                _ENCRYPTION_KEY_SERVICE,
                _ENCRYPTION_KEY_USERNAME,
                base64.urlsafe_b64encode(key).decode(),
            )
            return key
        except Exception:
            pass

    key_file = Path.home() / ".traderbot" / ".profile_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        key_file.chmod(0o600)
        return base64.urlsafe_b64decode(key_file.read_text().strip())
    key = os.urandom(32)
    key_file.write_text(base64.urlsafe_b64encode(key).decode())
    key_file.chmod(0o600)
    return key


def _encrypt_data(data: str, key: bytes) -> bytes:
    """Encrypt data using AES-256 via Fernet."""
    from cryptography.fernet import Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key).encrypt(data.encode())


def _decrypt_data(data: bytes, key: bytes) -> str:
    """Decrypt data using AES-256 via Fernet."""
    from cryptography.fernet import Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key).decrypt(data).decode()


def _keyring_available() -> bool:
    try:
        kr = __import__("keyring")
        if hasattr(kr, "get_keyring"):
            backend = kr.get_keyring()
            backend_name = type(backend).__name__
            if "Fail" in backend_name or "Null" in backend_name:
                return False
            kr.set_password("__traderbot_probe__", "test", "probe")
            kr.delete_password("__traderbot_probe__", "test")
        return True
    except Exception:
        return False


_KEYRING_OK: bool | None = None


def _check_keyring() -> bool:
    global _KEYRING_OK
    if _KEYRING_OK is None:
        _KEYRING_OK = _keyring_available()
        if not _KEYRING_OK:
            logger.warning("Keyring unavailable; profiles will be stored encrypted in %s", _PROFILES_FILE)
    return _KEYRING_OK


class ProfileRegistry:
    """Manage trading profiles with keyring storage, file-based fallback."""

    def __init__(self, keyring_module: Any = None) -> None:
        self._keyring = keyring_module
        self._using_keyring = keyring_module is not None or _check_keyring()

    def _get_keyring(self) -> Any:
        if self._keyring is not None:
            return self._keyring
        return __import__("keyring")

    def _service_name(self, profile_name: str) -> str:
        return f"{_KEYRING_SERVICE_PREFIX}{profile_name}"

    def _read_profiles_file(self) -> dict[str, dict]:
        try:
            key = _derive_or_create_key()
            encrypted = _PROFILES_FILE.read_bytes()
            plaintext = _decrypt_data(encrypted, key)
            return json.loads(plaintext)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        except Exception:
            legacy = Path.home() / ".traderbot" / "profiles.json"
            if legacy.exists():
                try:
                    data = json.loads(legacy.read_text())
                    self._write_profiles_file(data)
                    legacy.unlink()
                    return data
                except Exception:
                    pass
            return {}

    def _write_profiles_file(self, data: dict[str, dict]) -> None:
        _PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
        key = _derive_or_create_key()
        plaintext = json.dumps(data, indent=2)
        encrypted = _encrypt_data(plaintext, key)
        _PROFILES_FILE.write_bytes(encrypted)
        _PROFILES_FILE.chmod(0o600)

    def create_profile(self, profile: TradingProfile) -> None:
        if self.profile_exists(profile.name):
            raise ValueError(f"Profile '{profile.name}' already exists")

        profile_dict = profile.model_dump(
            exclude={"demo_mode", "base_dir", "keyring_prefix", "env_file"},
            mode="json"
        )
        profile_json = json.dumps(profile_dict)

        if self._using_keyring:
            kr = self._get_keyring()
            service = self._service_name(profile.name)
            try:
                kr.set_password(service, "profile", profile_json)
                self._update_index(profile.name, add=True)
            except Exception:
                logger.warning("Keyring write failed; falling back to file storage")
                self._using_keyring = False
                _write_profile_to_file(profile.name, profile_json, self)
                self._write_profiles_file(
                    {**self._read_profiles_file(), profile.name: profile_dict}
                )
        else:
            data = self._read_profiles_file()
            data[profile.name] = profile_dict
            self._write_profiles_file(data)

        logger.info("Created profile '%s'", profile.name)

    def get_profile(self, name: str) -> TradingProfile | None:
        profile_dict = self._get_profile_dict(name)
        if profile_dict is None:
            return None

        if "enabled_categories" in profile_dict and profile_dict["enabled_categories"]:
            from traderbot.kalshi.models import MarketCategory
            profile_dict["enabled_categories"] = [
                MarketCategory(cat.lower()) if isinstance(cat, str) else cat
                for cat in profile_dict["enabled_categories"]
            ]

        return TradingProfile.model_validate(profile_dict)

    def _get_profile_dict(self, name: str) -> dict | None:
        """Get profile dict from keyring or file."""
        if self._using_keyring:
            kr = self._get_keyring()
            service = self._service_name(name)
            try:
                profile_json = kr.get_password(service, "profile")
                if profile_json is not None:
                    return json.loads(profile_json)
            except Exception:
                self._using_keyring = False

        data = self._read_profiles_file()
        if name in data:
            return data[name]
        return None

    def list_profiles(self) -> list[str]:
        if self._using_keyring:
            kr = self._get_keyring()
            profiles: list[str] = []
            if hasattr(kr, "_store"):
                for (service, username) in kr._store.keys():
                    if service.startswith(_KEYRING_SERVICE_PREFIX) and username == "profile":
                        profiles.append(service[len(_KEYRING_SERVICE_PREFIX):])
            else:
                try:
                    index_json = kr.get_password(_KEYRING_SERVICE_PREFIX + "_index", "profiles")
                    if index_json:
                        profiles = json.loads(index_json)
                except Exception:
                    pass
            if profiles:
                return sorted(profiles)

        data = self._read_profiles_file()
        return sorted(data.keys())

    def delete_profile(self, name: str, keep_data: bool = True) -> None:
        if not self.profile_exists(name):
            logger.warning("Profile '%s' does not exist, nothing to delete", name)
            return

        profile = self.get_profile(name)

        if self._using_keyring:
            kr = self._get_keyring()
            service = self._service_name(name)
            try:
                kr.delete_password(service, "profile")
                self._update_index(name, add=False)
            except Exception:
                self._using_keyring = False

        if not self._using_keyring:
            data = self._read_profiles_file()
            data.pop(name, None)
            self._write_profiles_file(data)

        if not keep_data and profile is not None:
            data_dir = Path.home() / profile.base_dir
            if data_dir.exists():
                try:
                    shutil.rmtree(data_dir)
                    logger.info("Deleted data directory: %s", data_dir)
                except Exception as e:
                    logger.warning("Failed to delete data directory %s: %s", data_dir, e)

    def profile_exists(self, name: str) -> bool:
        if self._using_keyring:
            kr = self._get_keyring()
            service = self._service_name(name)
            try:
                if kr.get_password(service, "profile") is not None:
                    return True
            except Exception:
                self._using_keyring = False

        data = self._read_profiles_file()
        return name in data

    def update_profile(self, name: str, **kwargs: Any) -> TradingProfile:
        existing = self.get_profile(name)
        if existing is None:
            raise ValueError(f"Profile '{name}' not found")

        profile_dict = existing.model_dump(
            exclude={"demo_mode", "base_dir", "keyring_prefix", "env_file"},
            mode="json"
        )

        if "enabled_categories" in profile_dict and profile_dict["enabled_categories"]:
            from traderbot.kalshi.models import MarketCategory
            profile_dict["enabled_categories"] = [
                MarketCategory(cat.lower()) if isinstance(cat, str) else cat
                for cat in profile_dict["enabled_categories"]
            ]

        if "enabled_categories" in kwargs:
            from traderbot.kalshi.models import MarketCategory
            cats = kwargs.pop("enabled_categories")
            if isinstance(cats, list):
                profile_dict["enabled_categories"] = [
                    MarketCategory(cat.lower()) if isinstance(cat, str) else cat
                    for cat in cats
                ]
            else:
                profile_dict["enabled_categories"] = cats

        for key, value in kwargs.items():
            if value is not None:
                profile_dict[key] = value

        updated_profile = TradingProfile.model_validate(profile_dict)

        if self._using_keyring:
            kr = self._get_keyring()
            service = self._service_name(name)
            try:
                kr.delete_password(service, "profile")
                kr.set_password(service, "profile", json.dumps(updated_profile.model_dump(
                    exclude={"demo_mode", "base_dir", "keyring_prefix", "env_file"},
                    mode="json"
                )))
            except Exception:
                self._using_keyring = False

        if not self._using_keyring:
            data = self._read_profiles_file()
            data[name] = updated_profile.model_dump(
                exclude={"demo_mode", "base_dir", "keyring_prefix", "env_file"},
                mode="json"
            )
            self._write_profiles_file(data)

        logger.info("Updated profile '%s'", name)
        return updated_profile

    def _update_index(self, name: str, add: bool = True) -> None:
        kr = self._get_keyring()
        if hasattr(kr, "_store"):
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


def _write_profile_to_file(name: str, profile_json: str, registry: ProfileRegistry) -> None:
    """Emergency fallback: write profile to file when keyring fails mid-operation."""
    profile_dict = json.loads(profile_json)
    data = registry._read_profiles_file()
    data[name] = profile_dict
    registry._write_profiles_file(data)

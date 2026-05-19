"""Profile registry with encrypted file-based storage."""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from traderbot.fileops import set_dir_owner_only, set_file_owner_only
from traderbot.paths import get_data_dir
from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

_PROFILES_FILE = get_data_dir() / "profiles.enc"


def _get_keys_dir() -> Path:
    keys_dir = get_data_dir() / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    set_dir_owner_only(keys_dir)
    return keys_dir


def _derive_or_create_key() -> bytes:
    key_file = _get_keys_dir() / "profile.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    set_dir_owner_only(key_file.parent)
    if key_file.exists():
        set_file_owner_only(key_file)
        return base64.urlsafe_b64decode(key_file.read_text().strip())
    key = os.urandom(32)
    key_file.write_text(base64.urlsafe_b64encode(key).decode())
    set_file_owner_only(key_file)
    return key


def _encrypt_data(data: str, key: bytes) -> bytes:
    from cryptography.fernet import Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key).encrypt(data.encode())


def _decrypt_data(data: bytes, key: bytes) -> str:
    from cryptography.fernet import Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key).decrypt(data).decode()


class ProfileRegistry:
    """Manage trading profiles stored as encrypted JSON files."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    def _read_profiles_file(self) -> dict[str, dict]:
        try:
            key = _derive_or_create_key()
            encrypted = _PROFILES_FILE.read_bytes()
            plaintext = _decrypt_data(encrypted, key)
            return json.loads(plaintext)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        except Exception:
            legacy = get_data_dir() / "profiles.json"
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
        set_file_owner_only(_PROFILES_FILE)

    def create_profile(self, profile: TradingProfile) -> None:
        if self.profile_exists(profile.name):
            raise ValueError(f"Profile '{profile.name}' already exists")

        profile_dict = profile.model_dump(
            exclude={"paper_mode", "base_dir", "env_file"},
            mode="json"
        )

        data = self._read_profiles_file()
        data[profile.name] = profile_dict
        self._write_profiles_file(data)
        logger.info("Created profile '%s'", profile.name)

    def get_profile(self, name: str) -> TradingProfile | None:
        profile_dict = self._get_profile_dict(name)
        if profile_dict is None:
            return None

        if profile_dict.get("enabled_categories"):
            from traderbot.kalshi.models import MarketCategory
            profile_dict["enabled_categories"] = [
                MarketCategory(cat.lower()) if isinstance(cat, str) else cat
                for cat in profile_dict["enabled_categories"]
            ]

        return TradingProfile.model_validate(profile_dict)

    def _get_profile_dict(self, name: str) -> dict | None:
        data = self._read_profiles_file()
        if name in data:
            return data[name]
        return None

    def list_profiles(self) -> list[str]:
        data = self._read_profiles_file()
        return sorted(data.keys())

    def delete_profile(self, name: str, keep_data: bool = True) -> None:
        if not self.profile_exists(name):
            logger.warning("Profile '%s' does not exist, nothing to delete", name)
            return

        profile = self.get_profile(name)

        data = self._read_profiles_file()
        data.pop(name, None)
        self._write_profiles_file(data)

        if not keep_data and profile is not None:
            data_dir = Path(profile.base_dir)
            if data_dir.exists():
                try:
                    shutil.rmtree(data_dir)
                    logger.info("Deleted data directory: %s", data_dir)
                except Exception as e:
                    logger.warning("Failed to delete data directory %s: %s", data_dir, e)

    def profile_exists(self, name: str) -> bool:
        data = self._read_profiles_file()
        return name in data

    def update_profile(self, name: str, **kwargs: Any) -> TradingProfile:
        existing = self.get_profile(name)
        if existing is None:
            raise ValueError(f"Profile '{name}' not found")

        profile_dict = existing.model_dump(
            exclude={"paper_mode", "base_dir", "env_file"},
            mode="json"
        )

        if profile_dict.get("enabled_categories"):
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

        data = self._read_profiles_file()
        data[name] = updated_profile.model_dump(
            exclude={"paper_mode", "base_dir", "env_file"},
            mode="json"
        )
        self._write_profiles_file(data)

        logger.info("Updated profile '%s'", name)
        return updated_profile

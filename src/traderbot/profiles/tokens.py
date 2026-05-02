"""Token generation, resolution, and revocation for agent-profile binding."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_KEYRING_SERVICE_PREFIX = "traderbot.tokens."
_TOKENS_FILE = Path.home() / ".traderbot" / "tokens.enc"

# Global keyring instance (can be overridden for testing)
_keyring_instance: Any | None = None


def _get_keyring() -> Any:
    """Get keyring module (real or mock)."""
    if _keyring_instance is not None:
        return _keyring_instance
    return __import__("keyring")


def set_keyring(keyring_module: Any) -> None:
    """Set keyring module for testing."""
    global _keyring_instance
    _keyring_instance = keyring_module


def _keyring_available() -> bool:
    try:
        kr = _get_keyring()
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


def _derive_or_create_key() -> bytes:
    key_file = Path.home() / ".traderbot" / ".token_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        key_file.chmod(0o600)
        return base64.urlsafe_b64decode(key_file.read_text().strip())
    key = os.urandom(32)
    key_file.write_text(base64.urlsafe_b64encode(key).decode())
    key_file.chmod(0o600)
    return key


def _encrypt_data(data: str, key: bytes) -> bytes:
    from cryptography.fernet import Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key).encrypt(data.encode())


def _decrypt_data(data: bytes, key: bytes) -> str:
    from cryptography.fernet import Fernet
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key).decrypt(data).decode()


def _load_tokens_file() -> list[dict]:
    if not _TOKENS_FILE.exists():
        return []
    try:
        key = _derive_or_create_key()
        encrypted = _TOKENS_FILE.read_bytes()
        decrypted = _decrypt_data(encrypted, key)
        return json.loads(decrypted)
    except Exception as e:
        logger.warning("Failed to load tokens file: %s", e)
        return []


def _save_tokens_file(tokens: list[dict]) -> None:
    _TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = _derive_or_create_key()
    encrypted = _encrypt_data(json.dumps(tokens), key)
    _TOKENS_FILE.write_bytes(encrypted)
    _TOKENS_FILE.chmod(0o600)


def generate_token() -> str:
    """Generate 12-char opaque token with ~72 bits entropy.
    
    Returns:
        URL-safe token string (12 characters)
    """
    return secrets.token_urlsafe(9)[:12]


def assign_token(profile_name: str, agent_id: str, token: str) -> None:
    # Check if profile already has a token
    existing_token = get_profile_token(profile_name)
    if existing_token is not None:
        raise ValueError(f"Profile '{profile_name}' already has a token assigned")
    
    data = {
        "token": token,
        "profile": profile_name,
        "agent": agent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if _keyring_available():
        kr = _get_keyring()
        service = f"{_KEYRING_SERVICE_PREFIX}{token}"
        kr.set_password(service, "token", json.dumps(data))
    else:
        tokens = _load_tokens_file()
        tokens.append(data)
        _save_tokens_file(tokens)
    
    logger.info("Assigned token to profile '%s' for agent '%s'", profile_name, agent_id)


def resolve_token(token: str) -> tuple[str, str] | None:
    if _keyring_available():
        kr = _get_keyring()
        service = f"{_KEYRING_SERVICE_PREFIX}{token}"
        try:
            data_json = kr.get_password(service, "token")
            if data_json is None:
                return None
            data = json.loads(data_json)
            return (data["profile"], data["agent"])
        except Exception as e:
            logger.debug("Failed to resolve token from keyring: %s", e)
            return None
    else:
        tokens = _load_tokens_file()
        for entry in tokens:
            if entry["token"] == token:
                return (entry["profile"], entry["agent"])
        return None


def revoke_token(token: str) -> None:
    if _keyring_available():
        kr = _get_keyring()
        service = f"{_KEYRING_SERVICE_PREFIX}{token}"
        try:
            kr.delete_password(service, "token")
            logger.info("Revoked token: %s", token)
        except Exception as e:
            logger.debug("Failed to revoke token (may not exist): %s", e)
    else:
        tokens = _load_tokens_file()
        tokens = [t for t in tokens if t["token"] != token]
        _save_tokens_file(tokens)
        logger.info("Revoked token: %s", token)


def list_assignments() -> list[dict[str, str]]:
    if _keyring_available():
        kr = _get_keyring()
        assignments: list[dict[str, str]] = []
        if hasattr(kr, "_store"):
            for (service, username) in kr._store.keys():
                if service.startswith(_KEYRING_SERVICE_PREFIX) and username == "token":
                    token = service[len(_KEYRING_SERVICE_PREFIX):]
                    try:
                        data_json = kr.get_password(service, "token")
                        if data_json:
                            data = json.loads(data_json)
                            assignments.append({
                                "token": token,
                                "profile": data["profile"],
                                "agent": data["agent"],
                                "created_at": data["created_at"],
                            })
                    except Exception as e:
                        logger.warning("Failed to parse token data for %s: %s", token, e)
        else:
            logger.warning("list_assignments() not fully supported with real keyring backend")
        return assignments
    else:
        return _load_tokens_file()


def get_profile_token(profile_name: str) -> str | None:
    assignments = list_assignments()
    for assignment in assignments:
        if assignment["profile"] == profile_name:
            return assignment["token"]
    return None

# Made with Bob

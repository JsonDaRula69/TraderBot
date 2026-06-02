"""Token generation, resolution, revocation, and rotation for agent-profile binding."""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from traderbot.fileops import set_dir_owner_only, set_file_owner_only
from traderbot.paths import get_data_dir

if TYPE_CHECKING:
    from pathlib import Path

TOKEN_TTL_DAYS = 30

logger = logging.getLogger(__name__)


def _get_keys_dir() -> Path:
    keys_dir = get_data_dir() / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    set_dir_owner_only(keys_dir)
    return keys_dir


class TokenAlreadyAssignedError(ValueError):
    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        super().__init__(f"Profile '{profile_name}' already has a token assigned")


def _mask_token(token: str) -> str:
    return "****" + token[-4:] if len(token) > 4 else "****"


_TOKENS_FILE = get_data_dir() / "tokens.enc"


def _derive_or_create_key() -> bytes:
    key_file = _get_keys_dir() / "token.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    set_dir_owner_only(key_file.parent)
    if key_file.exists():
        set_file_owner_only(key_file)
        return base64.urlsafe_b64decode(key_file.read_text().strip())
    key = os.urandom(32)
    # Atomic creation with O_CREAT|O_EXCL to prevent race
    try:
        fd = os.open(str(key_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        set_file_owner_only(key_file)
        return base64.urlsafe_b64decode(key_file.read_text().strip())
    try:
        os.write(fd, base64.urlsafe_b64encode(key))
    finally:
        os.close(fd)
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
    set_file_owner_only(_TOKENS_FILE)


def generate_token() -> str:
    """Generate 12-char opaque token with ~72 bits entropy."""
    return secrets.token_urlsafe(9)[:12]


def assign_token(
    profile_name: str,
    agent_id: str,
    token: str,
    force: bool = False,
    ttl_days: int = TOKEN_TTL_DAYS,
) -> None:
    existing_token = get_profile_token(profile_name)
    if existing_token is not None and not force:
        raise TokenAlreadyAssignedError(profile_name)

    if existing_token is not None and force:
        revoke_token(existing_token)

    now = datetime.now(UTC)
    data = {
        "token": token,
        "profile": profile_name,
        "agent": agent_id,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
    }
    tokens = _load_tokens_file()
    tokens.append(data)
    _save_tokens_file(tokens)
    logger.info("Assigned token to profile '%s' for agent '%s'", profile_name, agent_id)


def resolve_token(token: str) -> tuple[str, str] | None:
    tokens = _load_tokens_file()
    now = datetime.now(UTC)
    for entry in tokens:
        if hmac.compare_digest(entry["token"], token):
            expires_str = entry.get("expires_at")
            if expires_str is not None:
                expires = datetime.fromisoformat(expires_str)
                if expires < now:
                    logger.warning(
                        "Token for profile '%s' has expired (expired %s)",
                        entry["profile"],
                        expires.isoformat(),
                    )
                    return None
            return (entry["profile"], entry["agent"])
    return None


def revoke_token(token: str) -> None:
    tokens = _load_tokens_file()
    tokens = [t for t in tokens if t["token"] != token]
    _save_tokens_file(tokens)
    logger.info("Revoked token: %s", _mask_token(token))


def list_assignments() -> list[dict[str, str]]:
    return _load_tokens_file()


def get_profile_token(profile_name: str) -> str | None:
    assignments = list_assignments()
    for assignment in assignments:
        if assignment["profile"] == profile_name:
            return assignment["token"]
    return None


def rotate_token(profile_name: str, ttl_days: int = TOKEN_TTL_DAYS) -> tuple[str, str] | None:
    """Replace a profile's token with a new one, invalidating the old token.

    Returns:
        Tuple of (new_token, agent_id) if the profile had a token, None otherwise.
    """
    tokens = _load_tokens_file()
    old_token: str | None = None
    agent_id: str = "unknown"

    for entry in tokens:
        if entry["profile"] == profile_name:
            old_token = entry["token"]
            agent_id = entry.get("agent", "unknown")
            break

    if old_token is None:
        return None

    tokens = [t for t in tokens if t["token"] != old_token]

    new_token = generate_token()
    now = datetime.now(UTC)
    tokens.append(
        {
            "token": new_token,
            "profile": profile_name,
            "agent": agent_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
        }
    )
    _save_tokens_file(tokens)
    logger.info(
        "Rotated token for profile '%s': %s -> %s",
        profile_name,
        _mask_token(old_token),
        _mask_token(new_token),
    )
    return new_token, agent_id

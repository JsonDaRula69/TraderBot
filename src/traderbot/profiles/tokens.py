"""Token generation, resolution, and revocation for agent-profile binding."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)


def _get_keys_dir() -> Path:
    keys_dir = get_data_dir() / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    keys_dir.chmod(0o700)
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
    key_file.parent.chmod(0o700)
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
    """Generate 16-char opaque token with ~96 bits entropy."""
    return secrets.token_urlsafe(12)[:16]


def create_token(profile_name: str, agent_id: str, force: bool = False) -> str:
    """Create or replace a profile-agent token. Returns the new token."""
    existing = get_token_for_profile(profile_name)
    if existing is not None and not force:
        raise TokenAlreadyAssignedError(profile_name)

    if existing is not None and force:
        revoke_token(existing)

    token = generate_token()
    data = {"token": token, "profile": profile_name, "agent": agent_id}
    tokens = _load_tokens_file()
    tokens.append(data)
    _save_tokens_file(tokens)
    logger.info("Created token for profile '%s' (agent '%s')", profile_name, agent_id)
    return token


def resolve_token(token: str) -> tuple[str, str] | None:
    """Resolve a token to (profile_name, agent_id) or None if invalid."""
    tokens = _load_tokens_file()
    for entry in tokens:
        if entry["token"] == token or (len(token) >= 4 and entry["token"].endswith(token)):
            return (entry["profile"], entry["agent"])
    return None


def revoke_token(token: str) -> None:
    """Revoke a token from the tokens file."""
    tokens = _load_tokens_file()
    tokens = [t for t in tokens if t["token"] != token]
    _save_tokens_file(tokens)
    logger.info("Revoked token: %s", _mask_token(token))


def get_token_for_profile(profile_name: str) -> str | None:
    """Return the token assigned to a profile, if any."""
    tokens = _load_tokens_file()
    for entry in tokens:
        if entry["profile"] == profile_name:
            return entry["token"]
    return None


def list_tokens() -> list[dict[str, str]]:
    """Return all token assignments."""
    return _load_tokens_file()

"""Token generation, resolution, and revocation for agent-profile binding."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from datetime import UTC, datetime

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)


class TokenAlreadyAssignedError(ValueError):
    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        super().__init__(f"Profile '{profile_name}' already has a token assigned")


def _mask_token(token: str) -> str:
    return "****" + token[-4:] if len(token) > 4 else "****"


_TOKENS_FILE = get_data_dir() / "tokens.enc"


def _derive_or_create_key() -> bytes:
    key_file = get_data_dir() / ".token_key"
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
    """Generate 12-char opaque token with ~72 bits entropy."""
    return secrets.token_urlsafe(9)[:12]


def assign_token(profile_name: str, agent_id: str, token: str, force: bool = False) -> None:
    existing_token = get_profile_token(profile_name)
    if existing_token is not None and not force:
        raise TokenAlreadyAssignedError(profile_name)

    if existing_token is not None and force:
        revoke_token(existing_token)

    data = {
        "token": token,
        "profile": profile_name,
        "agent": agent_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    tokens = _load_tokens_file()
    tokens.append(data)
    _save_tokens_file(tokens)
    logger.info("Assigned token to profile '%s' for agent '%s'", profile_name, agent_id)


def resolve_token(token: str) -> tuple[str, str] | None:
    tokens = _load_tokens_file()
    for entry in tokens:
        if entry["token"] == token:
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

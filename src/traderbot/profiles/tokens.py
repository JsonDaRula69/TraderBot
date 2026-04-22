"""Token generation, resolution, and revocation for agent-profile binding."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_KEYRING_SERVICE_PREFIX = "traderbot.tokens."

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


def generate_token() -> str:
    """Generate 12-char opaque token with ~72 bits entropy.
    
    Returns:
        URL-safe token string (12 characters)
    """
    return secrets.token_urlsafe(9)[:12]


def assign_token(profile_name: str, agent_id: str, token: str) -> None:
    """Store token→profile mapping in keyring.
    
    Args:
        profile_name: Name of the trading profile
        agent_id: Unique identifier for the agent
        token: Token string to assign
        
    Raises:
        ValueError: If profile already has a token assigned (one-to-one mapping)
    """
    # Check if profile already has a token
    existing_token = get_profile_token(profile_name)
    if existing_token is not None:
        raise ValueError(f"Profile '{profile_name}' already has a token assigned")
    
    kr = _get_keyring()
    service = f"{_KEYRING_SERVICE_PREFIX}{token}"
    
    # Store as JSON with profile, agent, and timestamp
    data = {
        "profile": profile_name,
        "agent": agent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    kr.set_password(service, "token", json.dumps(data))
    logger.info("Assigned token to profile '%s' for agent '%s'", profile_name, agent_id)


def resolve_token(token: str) -> tuple[str, str] | None:
    """Return (profile_name, agent_id) or None if invalid/revoked.
    
    Args:
        token: Token string to resolve
        
    Returns:
        Tuple of (profile_name, agent_id) if valid, None otherwise
    """
    kr = _get_keyring()
    service = f"{_KEYRING_SERVICE_PREFIX}{token}"
    
    try:
        data_json = kr.get_password(service, "token")
        if data_json is None:
            return None
        
        data = json.loads(data_json)
        return (data["profile"], data["agent"])
    except Exception as e:
        logger.debug("Failed to resolve token: %s", e)
        return None


def revoke_token(token: str) -> None:
    """Delete token from keyring.
    
    Args:
        token: Token string to revoke
    """
    kr = _get_keyring()
    service = f"{_KEYRING_SERVICE_PREFIX}{token}"
    
    try:
        kr.delete_password(service, "token")
        logger.info("Revoked token: %s", token)
    except Exception as e:
        logger.debug("Failed to revoke token (may not exist): %s", e)


def list_assignments() -> list[dict[str, str]]:
    """Return all token assignments.
    
    Returns:
        List of dicts with keys: token, profile, agent, created_at
    """
    kr = _get_keyring()
    assignments: list[dict[str, str]] = []
    
    # For mock keyring, iterate the store directly
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
        # Real keyring case - we'd need an index similar to ProfileRegistry
        # For now, this is a limitation of the real keyring backend
        logger.warning("list_assignments() not fully supported with real keyring backend")
    
    return assignments


def get_profile_token(profile_name: str) -> str | None:
    """Get token assigned to profile (one-to-one mapping).
    
    Args:
        profile_name: Name of the trading profile
        
    Returns:
        Token string if found, None otherwise
    """
    # Iterate all assignments to find the one for this profile
    assignments = list_assignments()
    for assignment in assignments:
        if assignment["profile"] == profile_name:
            return assignment["token"]
    return None

# Made with Bob

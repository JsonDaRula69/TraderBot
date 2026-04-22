"""Tests for token generation, resolution, and revocation."""

import pytest
from datetime import datetime
from traderbot.profiles.tokens import (
    generate_token,
    assign_token,
    resolve_token,
    revoke_token,
    list_assignments,
    get_profile_token,
    set_keyring,
)


class MockKeyring:
    """Mock keyring for testing."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key in self._store:
            del self._store[key]


@pytest.fixture(autouse=True)
def mock_keyring() -> MockKeyring:
    """Provide a mock keyring for all tests."""
    kr = MockKeyring()
    set_keyring(kr)
    yield kr
    set_keyring(None)  # Reset after test


def test_generate_token():
    """Token should be 12 chars and URL-safe."""
    token = generate_token()
    assert len(token) == 12
    # URL-safe chars: A-Z, a-z, 0-9, -, _
    assert all(c.isalnum() or c in "-_" for c in token)


def test_assign_and_resolve_token():
    """Assigned token should resolve to correct profile and agent."""
    token = generate_token()
    profile_name = "test-profile"
    agent_id = "test-agent-123"
    
    assign_token(profile_name, agent_id, token)
    result = resolve_token(token)
    
    assert result is not None
    assert result[0] == profile_name
    assert result[1] == agent_id
    
    # Cleanup
    revoke_token(token)


def test_resolve_invalid_token():
    """Invalid token should return None."""
    result = resolve_token("invalid-token-xyz")
    assert result is None


def test_revoke_token():
    """Revoked token should not resolve."""
    token = generate_token()
    profile_name = "revoke-test"
    agent_id = "agent-456"
    
    assign_token(profile_name, agent_id, token)
    assert resolve_token(token) is not None
    
    revoke_token(token)
    assert resolve_token(token) is None


def test_list_assignments():
    """List should return all active token assignments."""
    token1 = generate_token()
    token2 = generate_token()
    
    assign_token("profile1", "agent1", token1)
    assign_token("profile2", "agent2", token2)
    
    assignments = list_assignments()
    
    # Should contain at least our two tokens
    tokens = [a["token"] for a in assignments]
    assert token1 in tokens
    assert token2 in tokens
    
    # Verify structure
    assignment1 = next(a for a in assignments if a["token"] == token1)
    assert assignment1["profile"] == "profile1"
    assert assignment1["agent"] == "agent1"
    assert "created_at" in assignment1
    
    # Cleanup
    revoke_token(token1)
    revoke_token(token2)


def test_get_profile_token():
    """Should return token assigned to profile."""
    token = generate_token()
    profile_name = "get-token-test"
    agent_id = "agent-789"
    
    assign_token(profile_name, agent_id, token)
    
    retrieved_token = get_profile_token(profile_name)
    assert retrieved_token == token
    
    # Cleanup
    revoke_token(token)


def test_get_profile_token_not_found():
    """Should return None for profile without token."""
    result = get_profile_token("nonexistent-profile")
    assert result is None


def test_assign_second_token_to_same_profile():
    """Assigning second token to same profile should raise ValueError."""
    token1 = generate_token()
    token2 = generate_token()
    profile_name = "single-token-profile"
    
    assign_token(profile_name, "agent1", token1)
    
    with pytest.raises(ValueError, match="already has a token assigned"):
        assign_token(profile_name, "agent2", token2)
    
    # Cleanup
    revoke_token(token1)


def test_token_storage_format():
    """Token should be stored with correct JSON structure."""
    token = generate_token()
    profile_name = "format-test"
    agent_id = "agent-format"
    
    assign_token(profile_name, agent_id, token)
    
    # Resolve and verify structure
    result = resolve_token(token)
    assert result is not None
    
    # List and verify created_at is ISO8601
    assignments = list_assignments()
    assignment = next(a for a in assignments if a["token"] == token)
    
    # Verify ISO8601 format by parsing
    created_at = assignment["created_at"]
    datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    
    # Cleanup
    revoke_token(token)

# Made with Bob

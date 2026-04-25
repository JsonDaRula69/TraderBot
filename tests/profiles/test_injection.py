"""Tests for token injection into OpenClaw agent TOOLS.md files

Tests token injection, removal, and retrieval from OpenClaw agent TOOLS.md files.
"""

import tempfile
from pathlib import Path

import pytest

from traderbot.profiles.injection import (
    get_token_from_tools,
    inject_token,
    remove_token_from_tools,
)


@pytest.fixture
def temp_agent_dir(tmp_path: Path) -> Path:
    """Create a temporary agent directory structure"""
    agent_dir = tmp_path / ".openclaw" / "workspace" / "test-agent"
    agent_dir.mkdir(parents=True)
    return agent_dir


@pytest.fixture
def tools_with_env_section(temp_agent_dir: Path) -> Path:
    """Create TOOLS.md with existing environment variables section"""
    tools_path = temp_agent_dir / "TOOLS.md"
    content = """# Agent Tools

This file describes available tools.

## Environment Variables

The following environment variables are available:
- `OTHER_VAR`: Some other variable

## Other Section

More content here.
"""
    tools_path.write_text(content)
    return temp_agent_dir


@pytest.fixture
def tools_without_env_section(temp_agent_dir: Path) -> Path:
    """Create TOOLS.md without environment variables section"""
    tools_path = temp_agent_dir / "TOOLS.md"
    content = """# Agent Tools

This file describes available tools.

## Other Section

More content here.
"""
    tools_path.write_text(content)
    return temp_agent_dir


@pytest.fixture
def tools_with_token(temp_agent_dir: Path) -> Path:
    """Create TOOLS.md with token already injected"""
    tools_path = temp_agent_dir / "TOOLS.md"
    content = """# Agent Tools

This file describes available tools.

## Environment Variables

The following environment variables are available:
- `TRADERBOT_PROFILE_TOKEN`: Your assigned profile token (do not modify)
- `OTHER_VAR`: Some other variable

## Other Section

More content here.
"""
    tools_path.write_text(content)
    return temp_agent_dir


def test_inject_token_into_existing_env_section(tools_with_env_section: Path) -> None:
    """Inject token into TOOLS.md with existing environment variables section"""
    token = "test-token-12345"
    inject_token(str(tools_with_env_section), token)

    tools_path = tools_with_env_section / "TOOLS.md"
    content = tools_path.read_text()

    # Token should be added
    assert f"TRADERBOT_PROFILE_TOKEN={token}" in content
    # Other content should be preserved
    assert "OTHER_VAR" in content
    assert "Other Section" in content


def test_inject_token_creates_env_section(tools_without_env_section: Path) -> None:
    """Inject token into TOOLS.md without environment variables section"""
    token = "test-token-67890"
    inject_token(str(tools_without_env_section), token)

    tools_path = tools_without_env_section / "TOOLS.md"
    content = tools_path.read_text()

    # Environment Variables section should be created
    assert "## Environment Variables" in content
    # Token should be added
    assert f"TRADERBOT_PROFILE_TOKEN={token}" in content
    # Other content should be preserved
    assert "Other Section" in content


def test_remove_token_from_tools(tools_with_token: Path) -> None:
    """Remove token from TOOLS.md preserving other content"""
    remove_token_from_tools(str(tools_with_token))

    tools_path = tools_with_token / "TOOLS.md"
    content = tools_path.read_text()

    # Token line should be removed
    assert "TRADERBOT_PROFILE_TOKEN" not in content
    # Other content should be preserved
    assert "OTHER_VAR" in content
    assert "Other Section" in content
    assert "## Environment Variables" in content


def test_get_token_from_tools_returns_token(tools_with_token: Path) -> None:
    """Get token from TOOLS.md returns correct token"""
    # First inject a known token
    token = "known-token-abc123"
    inject_token(str(tools_with_token), token)

    # Then retrieve it
    retrieved_token = get_token_from_tools(str(tools_with_token))
    assert retrieved_token == token


def test_get_token_from_tools_returns_none(tools_without_env_section: Path) -> None:
    """Get token from TOOLS.md without token returns None"""
    token = get_token_from_tools(str(tools_without_env_section))
    assert token is None


def test_inject_token_twice_is_idempotent(tools_with_env_section: Path) -> None:
    """Injecting token twice replaces the first (idempotent)"""
    first_token = "first-token-111"
    second_token = "second-token-222"

    # Inject first token
    inject_token(str(tools_with_env_section), first_token)
    tools_path = tools_with_env_section / "TOOLS.md"
    content_after_first = tools_path.read_text()
    assert f"TRADERBOT_PROFILE_TOKEN={first_token}" in content_after_first

    # Inject second token
    inject_token(str(tools_with_env_section), second_token)
    content_after_second = tools_path.read_text()

    # Second token should replace first
    assert f"TRADERBOT_PROFILE_TOKEN={second_token}" in content_after_second
    assert first_token not in content_after_second
    # Should only appear once
    assert content_after_second.count("TRADERBOT_PROFILE_TOKEN") == 1


def test_inject_token_creates_tools_md_if_missing(temp_agent_dir: Path) -> None:
    """Inject token creates TOOLS.md if it doesn't exist"""
    token = "new-token-999"
    inject_token(str(temp_agent_dir), token)

    tools_path = temp_agent_dir / "TOOLS.md"
    assert tools_path.exists()

    content = tools_path.read_text()
    assert "## Environment Variables" in content
    assert f"TRADERBOT_PROFILE_TOKEN={token}" in content


def test_inject_token_nonexistent_directory_raises_error() -> None:
    """Inject token into nonexistent directory raises FileNotFoundError"""
    with pytest.raises(FileNotFoundError):
        inject_token("/nonexistent/path", "token")


def test_remove_token_from_nonexistent_tools_is_noop(temp_agent_dir: Path) -> None:
    """Remove token from nonexistent TOOLS.md is a no-op"""
    # Should not raise an error
    remove_token_from_tools(str(temp_agent_dir))


def test_get_token_from_nonexistent_tools_returns_none(temp_agent_dir: Path) -> None:
    """Get token from nonexistent TOOLS.md returns None"""
    token = get_token_from_tools(str(temp_agent_dir))
    assert token is None

# Made with Bob

"""Tests for OpenClaw agent auto-discovery."""

import pytest
from pathlib import Path
from traderbot.profiles.discovery import (
    discover_agents,
    get_agent_identity,
    list_agent_dirs,
)


@pytest.fixture
def workspace_dir(tmp_path):
    """Create a temporary workspace directory."""
    workspace = tmp_path / ".openclaw" / "workspace"
    workspace.mkdir(parents=True)
    return workspace


@pytest.fixture
def agent_with_identity(workspace_dir):
    """Create an agent directory with valid IDENTITY.md."""
    agent_dir = workspace_dir / "molty"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text(
        "# Agent Identity\n"
        "- **Agent ID**: molty\n"
        "- **Name**: Molty the Trader\n"
    )
    return agent_dir


@pytest.fixture
def agent_with_malformed_identity(workspace_dir):
    """Create an agent directory with malformed IDENTITY.md."""
    agent_dir = workspace_dir / "broken"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text("This is not a valid identity file\n")
    return agent_dir


@pytest.fixture
def agent_without_identity(workspace_dir):
    """Create an agent directory without IDENTITY.md."""
    agent_dir = workspace_dir / "empty"
    agent_dir.mkdir()
    return agent_dir


@pytest.fixture
def multi_agent_workspace(workspace_dir):
    """Create workspace with multiple agents."""
    # Agent 1: molty
    molty_dir = workspace_dir / "molty"
    molty_dir.mkdir()
    (molty_dir / "IDENTITY.md").write_text(
        "# Agent Identity\n"
        "- **Agent ID**: molty\n"
        "- **Name**: Molty the Trader\n"
    )
    
    # Agent 2: bob
    bob_dir = workspace_dir / "bob"
    bob_dir.mkdir()
    (bob_dir / "IDENTITY.md").write_text(
        "# Agent Identity\n"
        "- **Agent ID**: bob\n"
        "- **Name**: Bob the Builder\n"
    )
    
    # Agent 3: broken (malformed)
    broken_dir = workspace_dir / "broken"
    broken_dir.mkdir()
    (broken_dir / "IDENTITY.md").write_text("Invalid content\n")
    
    # Agent 4: empty (no IDENTITY.md)
    empty_dir = workspace_dir / "empty"
    empty_dir.mkdir()
    
    return workspace_dir


def test_get_agent_identity_valid(agent_with_identity):
    """Test getting agent identity from valid IDENTITY.md."""
    result = get_agent_identity(str(agent_with_identity))
    
    assert result is not None
    assert result["agent_id"] == "molty"
    assert result["name"] == "Molty the Trader"


def test_get_agent_identity_missing_file(agent_without_identity):
    """Test getting agent identity when IDENTITY.md is missing."""
    result = get_agent_identity(str(agent_without_identity))
    
    assert result is None


def test_get_agent_identity_malformed(agent_with_malformed_identity):
    """Test getting agent identity from malformed IDENTITY.md."""
    result = get_agent_identity(str(agent_with_malformed_identity))
    
    assert result is None


def test_get_agent_identity_nonexistent_dir():
    """Test getting agent identity from nonexistent directory."""
    result = get_agent_identity("/nonexistent/path")
    
    assert result is None


def test_list_agent_dirs_empty(workspace_dir):
    """Test listing agent directories in empty workspace."""
    result = list_agent_dirs(str(workspace_dir))
    
    assert result == []


def test_list_agent_dirs_with_agents(multi_agent_workspace):
    """Test listing agent directories with multiple agents."""
    result = list_agent_dirs(str(multi_agent_workspace))
    
    assert len(result) == 4
    agent_names = [Path(p).name for p in result]
    assert "molty" in agent_names
    assert "bob" in agent_names
    assert "broken" in agent_names
    assert "empty" in agent_names


def test_list_agent_dirs_nonexistent():
    """Test listing agent directories in nonexistent workspace."""
    result = list_agent_dirs("/nonexistent/workspace")
    
    assert result == []


def test_discover_agents_empty_workspace(workspace_dir):
    """Test discovering agents in empty workspace."""
    result = discover_agents(str(workspace_dir))
    
    assert result == []


def test_discover_agents_single_valid(agent_with_identity, workspace_dir):
    """Test discovering single valid agent."""
    result = discover_agents(str(workspace_dir))
    
    assert len(result) == 1
    assert result[0]["agent_id"] == "molty"
    assert result[0]["name"] == "Molty the Trader"
    assert "molty" in result[0]["path"]


def test_discover_agents_multi_workspace(multi_agent_workspace):
    """Test discovering agents in workspace with multiple agents."""
    result = discover_agents(str(multi_agent_workspace))
    
    # Should only return valid agents (molty and bob)
    assert len(result) == 2
    
    agent_ids = [a["agent_id"] for a in result]
    assert "molty" in agent_ids
    assert "bob" in agent_ids
    
    # Verify full structure
    molty = next(a for a in result if a["agent_id"] == "molty")
    assert molty["name"] == "Molty the Trader"
    assert "molty" in molty["path"]
    
    bob = next(a for a in result if a["agent_id"] == "bob")
    assert bob["name"] == "Bob the Builder"
    assert "bob" in bob["path"]


def test_discover_agents_filters_invalid(multi_agent_workspace):
    """Test that discover_agents filters out invalid agents."""
    result = discover_agents(str(multi_agent_workspace))
    
    # Should not include 'broken' or 'empty'
    agent_ids = [a["agent_id"] for a in result]
    assert "broken" not in agent_ids
    assert "empty" not in agent_ids


def test_discover_agents_nonexistent_workspace():
    """Test discovering agents in nonexistent workspace."""
    result = discover_agents("/nonexistent/workspace")
    
    assert result == []


def test_get_agent_identity_with_extra_whitespace(workspace_dir):
    """Test parsing IDENTITY.md with extra whitespace."""
    agent_dir = workspace_dir / "whitespace"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text(
        "# Agent Identity\n"
        "- **Agent ID**:   molty   \n"
        "- **Name**:   Molty the Trader   \n"
    )
    
    result = get_agent_identity(str(agent_dir))
    
    assert result is not None
    assert result["agent_id"] == "molty"
    assert result["name"] == "Molty the Trader"


def test_get_agent_identity_case_insensitive_headers(workspace_dir):
    """Test parsing IDENTITY.md with different case headers."""
    agent_dir = workspace_dir / "casetest"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text(
        "# agent identity\n"
        "- **agent id**: molty\n"
        "- **name**: Molty the Trader\n"
    )
    
    result = get_agent_identity(str(agent_dir))
    
    assert result is not None
    assert result["agent_id"] == "molty"
    assert result["name"] == "Molty the Trader"

# Made with Bob

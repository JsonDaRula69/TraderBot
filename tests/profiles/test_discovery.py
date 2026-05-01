"""Tests for OpenClaw agent auto-discovery."""

import json
import pytest
from pathlib import Path
from traderbot.profiles.discovery import (
    discover_agents,
    get_agent_identity,
    list_agent_dirs,
    _discover_from_config,
    _discover_from_agent_dirs,
)


@pytest.fixture
def workspace_dir(tmp_path):
    workspace = tmp_path / ".openclaw" / "workspace"
    workspace.mkdir(parents=True)
    return workspace


@pytest.fixture
def openclaw_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    openclaw_dir = home / ".openclaw"
    openclaw_dir.mkdir()
    return openclaw_dir


@pytest.fixture
def agent_with_identity(workspace_dir):
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
    agent_dir = workspace_dir / "broken"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text("This is not a valid identity file\n")
    return agent_dir


@pytest.fixture
def agent_without_identity(workspace_dir):
    agent_dir = workspace_dir / "empty"
    agent_dir.mkdir()
    return agent_dir


@pytest.fixture
def multi_agent_workspace(workspace_dir):
    molty_dir = workspace_dir / "molty"
    molty_dir.mkdir()
    (molty_dir / "IDENTITY.md").write_text(
        "# Agent Identity\n"
        "- **Agent ID**: molty\n"
        "- **Name**: Molty the Trader\n",
    )

    bob_dir = workspace_dir / "bob"
    bob_dir.mkdir()
    (bob_dir / "IDENTITY.md").write_text(
        "# Agent Identity\n"
        "- **Agent ID**: bob\n"
        "- **Name**: Bob the Builder\n",
    )

    broken_dir = workspace_dir / "broken"
    broken_dir.mkdir()
    (broken_dir / "IDENTITY.md").write_text("Invalid content\n")

    empty_dir = workspace_dir / "empty"
    empty_dir.mkdir()

    return workspace_dir


def test_get_agent_identity_valid(agent_with_identity):
    result = get_agent_identity(str(agent_with_identity))
    assert isinstance(result, dict)
    assert result["agent_id"] == "molty"
    assert result["name"] == "Molty the Trader"


def test_get_agent_identity_missing_file(agent_without_identity):
    result = get_agent_identity(str(agent_without_identity))
    assert result is None


def test_get_agent_identity_malformed(agent_with_malformed_identity):
    result = get_agent_identity(str(agent_with_malformed_identity))
    assert result is None


def test_get_agent_identity_nonexistent_dir():
    result = get_agent_identity("/nonexistent/path")
    assert result is None


def test_list_agent_dirs_empty(workspace_dir):
    result = list_agent_dirs(str(workspace_dir))
    assert result == []


def test_list_agent_dirs_with_agents(multi_agent_workspace):
    result = list_agent_dirs(str(multi_agent_workspace))
    assert len(result) == 4
    agent_names = [Path(p).name for p in result]
    assert "molty" in agent_names
    assert "bob" in agent_names
    assert "broken" in agent_names
    assert "empty" in agent_names


def test_list_agent_dirs_nonexistent():
    result = list_agent_dirs("/nonexistent/workspace")
    assert result == []


def test_discover_agents_empty_workspace(workspace_dir, monkeypatch):
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_config", lambda: [])
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_agent_dirs", lambda: [])
    result = discover_agents(str(workspace_dir))
    assert result == []


def test_discover_agents_single_valid(agent_with_identity, workspace_dir, monkeypatch):
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_config", lambda: [])
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_agent_dirs", lambda: [])
    result = discover_agents(str(workspace_dir))
    assert len(result) == 1
    assert result[0]["agent_id"] == "molty"
    assert result[0]["name"] == "Molty the Trader"
    assert "molty" in result[0]["path"]


def test_discover_agents_multi_workspace(multi_agent_workspace, monkeypatch):
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_config", lambda: [])
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_agent_dirs", lambda: [])
    result = discover_agents(str(multi_agent_workspace))
    assert len(result) == 2
    agent_ids = [a["agent_id"] for a in result]
    assert "molty" in agent_ids
    assert "bob" in agent_ids

    molty = next(a for a in result if a["agent_id"] == "molty")
    assert molty["name"] == "Molty the Trader"
    assert "molty" in molty["path"]

    bob = next(a for a in result if a["agent_id"] == "bob")
    assert bob["name"] == "Bob the Builder"
    assert "bob" in bob["path"]


def test_discover_agents_filters_invalid(multi_agent_workspace):
    result = discover_agents(str(multi_agent_workspace))
    agent_ids = [a["agent_id"] for a in result]
    assert "broken" not in agent_ids
    assert "empty" not in agent_ids


def test_discover_agents_nonexistent_workspace(monkeypatch):
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_config", lambda: [])
    monkeypatch.setattr("traderbot.profiles.discovery._discover_from_agent_dirs", lambda: [])
    result = discover_agents("/nonexistent/workspace")
    assert result == []


def test_discover_from_config(openclaw_home, monkeypatch):
    config_path = openclaw_home / "openclaw.json"
    config_path.write_text(json.dumps({
        "agents": {
            "list": [
                {"id": "work", "name": "Work Agent", "workspace": str(openclaw_home / "workspace-work")},
                {"id": "personal", "name": "Personal Agent", "workspace": str(openclaw_home / "workspace-personal")},
            ]
        }
    }))

    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_dir", lambda: openclaw_home)
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_config", lambda: config_path)

    # Create actual workspace directories with IDENTITY.md (per OpenClaw: workspace contains identity files)
    import pathlib as P
    work_ws = openclaw_home / "workspace-work"
    work_ws.mkdir(parents=True)
    (work_ws / "IDENTITY.md").write_text(
        "# Agent Identity\n- **Agent ID**: work\n- **Name**: Work Agent\n"
    )
    personal_ws = openclaw_home / "workspace-personal"
    personal_ws.mkdir(parents=True)
    (personal_ws / "IDENTITY.md").write_text(
        "# Agent Identity\n- **Agent ID**: personal\n- **Name**: Personal Agent\n"
    )

    results = _discover_from_config()
    assert len(results) == 2
    assert results[0]["agent_id"] == "work"
    assert results[0]["name"] == "Work Agent"
    assert results[1]["agent_id"] == "personal"


def test_discover_from_config_no_file(openclaw_home, monkeypatch):
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_dir", lambda: openclaw_home)
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_config", lambda: openclaw_home / "openclaw.json")
    results = _discover_from_config()
    assert results == []


def test_discover_from_config_invalid_json(openclaw_home, monkeypatch):
    config_path = openclaw_home / "openclaw.json"
    config_path.write_text("not json")
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_dir", lambda: openclaw_home)
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_config", lambda: config_path)
    results = _discover_from_config()
    assert results == []


def test_discover_from_agent_dirs(openclaw_home, monkeypatch):
    agents_dir = openclaw_home / "agents"
    work_dir = agents_dir / "work"
    work_dir.mkdir(parents=True)
    (work_dir / "IDENTITY.md").write_text(
        "# Agent Identity\n"
        "- **Agent ID**: work\n"
        "- **Name**: Work Agent\n",
    )

    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_dir", lambda: openclaw_home)

    results = _discover_from_agent_dirs()
    assert len(results) == 1
    assert results[0]["agent_id"] == "work"


def test_discover_from_config_no_agents_list(openclaw_home, monkeypatch):
    config_path = openclaw_home / "openclaw.json"
    config_path.write_text(json.dumps({"agents": {}}))
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_dir", lambda: openclaw_home)
    monkeypatch.setattr("traderbot.profiles.discovery._get_openclaw_config", lambda: config_path)
    results = _discover_from_config()
    assert results == []


def test_get_agent_identity_with_extra_whitespace(workspace_dir):
    agent_dir = workspace_dir / "whitespace"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text(
        "# Agent Identity\n"
        "- **Agent ID**:   molty   \n"
        "- **Name**:   Molty the Trader   \n",
    )
    result = get_agent_identity(str(agent_dir))
    assert isinstance(result, dict)
    assert result["agent_id"] == "molty"
    assert result["name"] == "Molty the Trader"


def test_get_agent_identity_case_insensitive_headers(workspace_dir):
    agent_dir = workspace_dir / "casetest"
    agent_dir.mkdir()
    identity_file = agent_dir / "IDENTITY.md"
    identity_file.write_text(
        "# agent identity\n"
        "- **agent id**: molty\n"
        "- **name**: Molty the Trader\n",
    )
    result = get_agent_identity(str(agent_dir))
    assert isinstance(result, dict)
    assert result["agent_id"] == "molty"
    assert result["name"] == "Molty the Trader"

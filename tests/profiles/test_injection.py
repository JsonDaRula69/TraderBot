"""Tests for token injection into OpenClaw agent TOOLS.md files

Tests token injection, removal, and retrieval from OpenClaw agent TOOLS.md files.
Token values are never written to TOOLS.md — only the env var name reference.
"""

from pathlib import Path

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.injection import (
    get_token_from_tools,
    inject_token,
    propagate_workspace_files,
    remove_token_from_tools,
)
from traderbot.profiles.models import TradingProfile


@pytest.fixture
def temp_agent_dir(tmp_path: Path) -> Path:
    agent_dir = tmp_path / ".openclaw" / "workspace" / "test-agent"
    agent_dir.mkdir(parents=True)
    return agent_dir


@pytest.fixture
def tools_with_env_section(temp_agent_dir: Path) -> Path:
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
    tools_path = temp_agent_dir / "TOOLS.md"
    content = """# Agent Tools

This file describes available tools.

## Environment Variables

The following environment variables are available:
- `TRADERBOT_PROFILE_TOKEN`: Your assigned profile token (read from environment variable, do not modify)
- `OTHER_VAR`: Some other variable

## Other Section

More content here.
"""
    tools_path.write_text(content)
    return temp_agent_dir


def test_inject_token_into_existing_env_section(tools_with_env_section: Path) -> None:
    inject_token(str(tools_with_env_section), "test-token-12345")

    tools_path = tools_with_env_section / "TOOLS.md"
    content = tools_path.read_text()

    assert "TRADERBOT_PROFILE_TOKEN" in content
    assert "do not modify" in content
    assert "OTHER_VAR" in content
    assert "Other Section" in content


def test_inject_token_creates_env_section(tools_without_env_section: Path) -> Path:
    inject_token(str(tools_without_env_section), "test-token-67890")

    tools_path = tools_without_env_section / "TOOLS.md"
    content = tools_path.read_text()

    assert "## Environment Variables" in content
    assert "TRADERBOT_PROFILE_TOKEN" in content
    assert "Other Section" in content


def test_remove_token_from_tools(tools_with_token: Path) -> None:
    remove_token_from_tools(str(tools_with_token))

    tools_path = tools_with_token / "TOOLS.md"
    content = tools_path.read_text()

    assert "TRADERBOT_PROFILE_TOKEN" not in content
    assert "OTHER_VAR" in content
    assert "Other Section" in content
    assert "## Environment Variables" in content


def test_get_token_from_tools_returns_env_var_name(tools_with_token: Path) -> None:
    result = get_token_from_tools(str(tools_with_token))
    assert result == "TRADERBOT_PROFILE_TOKEN"


def test_get_token_from_tools_returns_none(tools_without_env_section: Path) -> None:
    result = get_token_from_tools(str(tools_without_env_section))
    assert result is None


def test_inject_token_twice_is_idempotent(tools_with_env_section: Path) -> None:
    inject_token(str(tools_with_env_section), "first-token-111")
    tools_path = tools_with_env_section / "TOOLS.md"
    content_after_first = tools_path.read_text()
    assert "TRADERBOT_PROFILE_TOKEN" in content_after_first

    inject_token(str(tools_with_env_section), "second-token-222")
    content_after_second = tools_path.read_text()

    assert "TRADERBOT_PROFILE_TOKEN" in content_after_second
    assert content_after_second.count("TRADERBOT_PROFILE_TOKEN") == 1


def test_inject_token_creates_tools_md_if_missing(temp_agent_dir: Path) -> None:
    inject_token(str(temp_agent_dir), "new-token-999")

    tools_path = temp_agent_dir / "TOOLS.md"
    assert tools_path.exists()

    content = tools_path.read_text()
    assert "## Environment Variables" in content
    assert "TRADERBOT_PROFILE_TOKEN" in content


def test_inject_token_nonexistent_directory_raises_error() -> None:
    with pytest.raises(FileNotFoundError):
        inject_token("/nonexistent/path", "token")


def test_remove_token_from_nonexistent_tools_is_noop(temp_agent_dir: Path) -> None:
    remove_token_from_tools(str(temp_agent_dir))


def test_get_token_from_nonexistent_tools_returns_none(temp_agent_dir: Path) -> None:
    result = get_token_from_tools(str(temp_agent_dir))
    assert result is None


def test_inject_token_never_writes_token_value(temp_agent_dir: Path) -> None:
    token_value = "super-secret-token-abc"
    inject_token(str(temp_agent_dir), token_value)

    tools_path = temp_agent_dir / "TOOLS.md"
    content = tools_path.read_text()

    assert token_value not in content
    assert "TRADERBOT_PROFILE_TOKEN" in content


class TestPropagateWorkspaceFiles:
    @pytest.fixture
    def profile(self) -> TradingProfile:
        return TradingProfile(
            name="test_agent",
            mode="paper",
            description="Test profile for propagation",
            enabled_categories=[MarketCategory.CRYPTO],
            risk_multiplier=0.5,
            max_position_per_market_pct=0.03,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=3,
            min_liquidity_threshold=2000,
            min_edge_pct=1.0,
        )

    @pytest.fixture
    def template_dir(self, tmp_path: Path) -> Path:
        tdir = tmp_path / ".openclaw" / "workspace"
        tdir.mkdir(parents=True)
        (tdir / "AGENTS.md").write_text(
            "# Agent Rules\n\n"
            "<!-- TRADERBOT_RULES_START -->\n"
            "rule one\nrule two\n"
            "<!-- TRADERBOT_RULES_END -->\n"
        )
        (tdir / "SOUL.md").write_text(
            "<!-- TRADERBOT_SOUL_START -->\n"
            "be disciplined\n"
            "<!-- TRADERBOT_SOUL_END -->\n"
        )
        (tdir / "TOOLS.md").write_text(
            "# Agent Tools\n\n"
            "<!-- TRADERBOT_TOOLS_START -->\n"
            "tool config\n"
            "<!-- TRADERBOT_TOOLS_END -->\n"
        )
        (tdir / "IDENTITY.md").write_text(
            "# Identity\n\n"
            "<!-- TRADERBOT_PROFILE_START -->\n"
            "old profile\n"
            "<!-- TRADERBOT_PROFILE_END -->\n"
        )
        (tdir / "USER.md").write_text("default user template\n")
        (tdir / "MEMORY.md").write_text("default memory template\n")
        (tdir / "BOOTSTRAP.md").write_text(
            "<!-- TRADERBOT_BOOTSTRAP_START -->\n"
            "bootstrap content\n"
            "<!-- TRADERBOT_BOOTSTRAP_END -->\n"
        )
        learnings = tdir / ".learnings"
        learnings.mkdir()
        (learnings / "LEARNINGS.md").write_text("default learnings\n")
        return tdir

    def _call_propagate(self, profile, target_dir, template_dir):
        import traderbot.profiles.injection as inj_mod
        fake_file = str(template_dir.parent.parent / "src" / "traderbot" / "profiles" / "injection.py")
        original_file = inj_mod.__file__
        inj_mod.__file__ = fake_file
        try:
            propagate_workspace_files(profile, target_dir)
        finally:
            inj_mod.__file__ = original_file

    def test_real_templates_create_files(self, tmp_path: Path, profile: TradingProfile):
        target = tmp_path / "real-workspace"
        propagate_workspace_files(profile, target)
        assert target.exists()
        assert (target / "AGENTS.md").exists()
        assert (target / "SOUL.md").exists()
        assert (target / "IDENTITY.md").exists()
        identity = (target / "IDENTITY.md").read_text()
        assert "- **Name**: test_agent" in identity

    def test_fenced_merge_preserves_custom_content(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        (target / "AGENTS.md").write_text(
            "# My Agent\n\n"
            "<!-- TRADERBOT_RULES_START -->\n"
            "old rule\n"
            "<!-- TRADERBOT_RULES_END -->\n"
            "\n# Custom additions\n"
        )
        self._call_propagate(profile, target, template_dir)
        content = (target / "AGENTS.md").read_text()
        assert "rule one" in content
        assert "rule two" in content
        assert "old rule" not in content
        assert "Custom additions" in content

    def test_init_if_missing_skips_existing(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        (target / "USER.md").write_text("my custom user data")
        self._call_propagate(profile, target, template_dir)
        assert (target / "USER.md").read_text() == "my custom user data"

    def test_init_if_missing_deploys_absent(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        self._call_propagate(profile, target, template_dir)
        assert (target / "MEMORY.md").exists()
        assert "default memory template" in (target / "MEMORY.md").read_text()

    def test_creates_target_dir(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "new-workspace"
        self._call_propagate(profile, target, template_dir)
        assert target.exists()

    def test_identity_injection(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        self._call_propagate(profile, target, template_dir)
        content = (target / "IDENTITY.md").read_text()
        assert "- **Name**: test_agent" in content
        assert "- **Risk Multiplier**: 0.5" in content

    def test_no_shutil_import(self):
        import traderbot.profiles.injection as inj
        assert not hasattr(inj, "shutil")

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


def test_inject_token_is_noop(tools_with_env_section: Path) -> None:
    """inject_token is a no-op after token-injection removal for security."""
    original = (tools_with_env_section / "TOOLS.md").read_text()
    inject_token(str(tools_with_env_section), "some-token")

    content = (tools_with_env_section / "TOOLS.md").read_text()
    assert content == original
    assert "TRADERBOT_PROFILE_TOKEN" not in content


def test_inject_token_does_not_create_file(temp_agent_dir: Path) -> None:
    inject_token(str(temp_agent_dir), "new-token-999")
    assert not (temp_agent_dir / "TOOLS.md").exists()


def test_inject_token_nonexistent_directory_is_noop() -> None:
    """inject_token is a no-op, so nonexistent directory does not raise."""
    inject_token("/nonexistent/path", "token")


def test_remove_token_from_tools_is_noop(tools_with_token: Path) -> None:
    """remove_token_from_tools is a no-op after token-injection removal."""
    original = (tools_with_token / "TOOLS.md").read_text()
    remove_token_from_tools(str(tools_with_token))
    content = (tools_with_token / "TOOLS.md").read_text()
    assert content == original


def test_get_token_from_tools_returns_none_when_token_present(tools_with_token: Path) -> None:
    result = get_token_from_tools(str(tools_with_token))
    assert result is None


def test_inject_token_nonexistent_directory_is_noop() -> None:
    """inject_token is a no-op, so nonexistent directory does not raise."""
    inject_token("/nonexistent/path", "token")


def test_remove_token_from_nonexistent_tools_is_noop(temp_agent_dir: Path) -> None:
    remove_token_from_tools(str(temp_agent_dir))


def test_get_token_from_nonexistent_tools_returns_none(temp_agent_dir: Path) -> None:
    result = get_token_from_tools(str(temp_agent_dir))
    assert result is None


def test_inject_token_never_writes_token_value(temp_agent_dir: Path) -> None:
    token_value = "super-secret-token-abc"
    inject_token(str(temp_agent_dir), token_value)
    # inject_token is a no-op, so the file should not exist
    assert not (temp_agent_dir / "TOOLS.md").exists()


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

    def test_fenced_merge_preserves_custom_content(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        (target / "AGENTS.md").write_text(
            "# My Agent\n\n"
            "<!-- TRADERBOT_RULES_START -->\n"
            "old rule\n"
            "<!-- TRADERBOT_RULES_END -->\n\n"
            "# Custom additions\n"
        )
        self._call_propagate(profile, target, template_dir)

        merged = (target / "AGENTS.md").read_text()
        assert "old rule" in merged
        assert "# Custom additions" in merged

    def test_init_if_missing_deploys_absent(
        self, tmp_path: Path, profile: TradingProfile, template_dir: Path
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        (target / "AGENTS.md").write_text("existing agents content\n")
        init_if_missing(template_dir / "MEMORY.md", target / "MEMORY.md")
        assert (target / "MEMORY.md").exists()
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
        self, tmp_path: Path, profile: TradingProfile
    ):
        target = tmp_path / "agent-workspace"
        target.mkdir()
        (target / "IDENTITY.md").write_text(
            "# Identity\n\n<!-- TRADERBOT_PROFILE_START -->\n<!-- TRADERBOT_PROFILE_END -->\n"
        )
        from traderbot.profiles.injection_strategies import inject_profile_into_identity
        inject_profile_into_identity(profile, target / "IDENTITY.md")
        content = (target / "IDENTITY.md").read_text()
        assert "test_agent" in content

    def test_shutil_imported_for_copy(self) -> None:
        """propagate_workspace_files imports shutil for directory copies."""
        import traderbot.profiles.injection as inj
        assert hasattr(inj, "shutil")

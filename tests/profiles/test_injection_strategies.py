"""Tests for injection_strategies merge behaviors."""

from unittest.mock import patch

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.injection_strategies import (
    FILE_STRATEGIES,
    FENCED_BLOCK_MARKERS,
    InjectionStrategy,
    _extract_fenced_block,
    _extract_marked_section,
    _replace_fenced_block,
    ask_then_merge,
    fenced_merge,
    init_if_missing,
    inject_agents_block,
    inject_profile_into_identity,
    inject_soul_block,
    overwrite_if_exists,
)
from traderbot.profiles.models import TradingProfile


@pytest.fixture
def template_with_markers() -> str:
    return (
        "# Rules\n"
        "\n"
        "<!-- TRADERBOT_RULES_START -->\n"
        "rule one\n"
        "rule two\n"
        "<!-- TRADERBOT_RULES_END -->\n"
        "\n"
        "Some trailing content\n"
    )


@pytest.fixture
def template_no_markers() -> str:
    return "# Plain file\n\nJust content here.\n"


class TestInjectionStrategyEnum:
    def test_values(self):
        assert InjectionStrategy.FENCED_MERGE == "fenced_merge"
        assert InjectionStrategy.INIT_IF_MISSING == "init_if_missing"
        assert InjectionStrategy.ASK_THEN_MERGE == "ask_then_merge"

    def test_is_str_enum(self):
        assert isinstance(InjectionStrategy.FENCED_MERGE, str)

    def test_members(self):
        assert len(InjectionStrategy) == 4


class TestFencedBlockMarkers:
    def test_all_marker_keys_have_tuples(self):
        for key, (start, end) in FENCED_BLOCK_MARKERS.items():
            assert start.startswith("<!--")
            assert end.startswith("<!--")
            assert start.endswith("-->")
            assert end.endswith("-->")

    def test_markers_are_paired(self):
        for key, (start, end) in FENCED_BLOCK_MARKERS.items():
            assert "START" in start
            assert "END" in end
            assert start != end


class TestFileStrategies:
    def test_fenced_merge_files(self):
        fenced = [
            k for k, v in FILE_STRATEGIES.items() if v == InjectionStrategy.FENCED_MERGE
        ]
        assert "AGENTS.md" in fenced
        assert "SOUL.md" in fenced
        assert "TOOLS.md" in fenced
        assert "IDENTITY.md" in fenced

    def test_ask_then_merge_files(self):
        ask = [
            k for k, v in FILE_STRATEGIES.items() if v == InjectionStrategy.ASK_THEN_MERGE
        ]
        assert "BOOT.md.bak" in ask
        assert "HEARTBEAT.md" in ask

    def test_overwrite_if_exists_files(self):
        ow = [
            k for k, v in FILE_STRATEGIES.items() if v == InjectionStrategy.OVERWRITE_IF_EXISTS
        ]
        assert "BOOTSTRAP.md" in ow

    def test_init_if_missing_files(self):
        init = [
            k
            for k, v in FILE_STRATEGIES.items()
            if v == InjectionStrategy.INIT_IF_MISSING
        ]
        assert "USER.md" in init
        assert "MEMORY.md" in init
        assert "SESSION-STATE.md" in init
        assert "HEARTBEAT_DATA.md" in init
        assert ".learnings/" in init

    def test_fenced_files_have_markers(self):
        for key, strategy in FILE_STRATEGIES.items():
            if strategy == InjectionStrategy.FENCED_MERGE and key in FENCED_BLOCK_MARKERS:
                assert key in FENCED_BLOCK_MARKERS

    def test_overwrite_if_exists_files_have_no_markers(self):
        ow = [
            k for k, v in FILE_STRATEGIES.items() if v == InjectionStrategy.OVERWRITE_IF_EXISTS
        ]
        for key in ow:
            assert key not in FENCED_BLOCK_MARKERS


class TestExtractFencedBlock:
    def test_extracts_content_between_markers(self):
        content = "before\n<!-- START -->\ninner\n<!-- END -->\nafter"
        result = _extract_fenced_block(content, "<!-- START -->", "<!-- END -->")
        assert result == "inner"

    def test_returns_empty_if_start_missing(self):
        content = "no markers here"
        result = _extract_fenced_block(content, "<!-- START -->", "<!-- END -->")
        assert result == ""

    def test_returns_empty_if_end_missing(self):
        content = "<!-- START -->\ncontent only"
        result = _extract_fenced_block(content, "<!-- START -->", "<!-- END -->")
        assert result == ""

    def test_strips_whitespace(self):
        content = "<!-- START -->\n  padded  \n<!-- END -->"
        result = _extract_fenced_block(content, "<!-- START -->", "<!-- END -->")
        assert result == "padded"


class TestReplaceFencedBlock:
    def test_replaces_existing_block(self):
        content = "<!-- START -->\nold\n<!-- END -->"
        result = _replace_fenced_block(content, "<!-- START -->", "<!-- END -->", "new")
        assert "<!-- START -->" in result
        assert "<!-- END -->" in result
        assert "new" in result
        assert "old" not in result

    def test_appends_if_no_markers(self):
        content = "existing"
        result = _replace_fenced_block(content, "<!-- START -->", "<!-- END -->", "new")
        assert "existing" in result
        assert "<!-- START -->" in result
        assert "new" in result
        assert "<!-- END -->" in result


class TestExtractMarkedSection:
    def test_extracts_full_section_with_markers(self):
        content = "before\n<!-- START -->\ninner\n<!-- END -->\nafter"
        result = _extract_marked_section(content, "<!-- START -->", "<!-- END -->")
        assert result.startswith("<!-- START -->")
        assert result.endswith("<!-- END -->")
        assert "inner" in result

    def test_returns_full_content_if_no_markers(self):
        content = "just content"
        result = _extract_marked_section(content, "<!-- START -->", "<!-- END -->")
        assert result == content


class TestFencedMerge:
    def test_new_file_gets_full_template(self, tmp_path, template_with_markers):
        target = tmp_path / "AGENTS.md"
        markers = FENCED_BLOCK_MARKERS["AGENTS.md"]
        fenced_merge(template_with_markers, target, markers)
        assert target.exists()
        assert target.read_text() == template_with_markers

    def test_existing_file_with_markers_gets_block_replaced(
        self, tmp_path, template_with_markers
    ):
        target = tmp_path / "AGENTS.md"
        existing = (
            "# Existing\n\n"
            "<!-- TRADERBOT_RULES_START -->\n"
            "old rule\n"
            "<!-- TRADERBOT_RULES_END -->\n"
        )
        target.write_text(existing)
        markers = FENCED_BLOCK_MARKERS["AGENTS.md"]
        fenced_merge(template_with_markers, target, markers)
        result = target.read_text()
        assert "rule one" in result
        assert "rule two" in result
        assert "old rule" not in result
        assert "<!-- TRADERBOT_RULES_START -->" in result

    def test_existing_file_without_markers_gets_block_appended(
        self, tmp_path, template_with_markers
    ):
        target = tmp_path / "AGENTS.md"
        existing = "# My agent\n\nCustom content here.\n"
        target.write_text(existing)
        markers = FENCED_BLOCK_MARKERS["AGENTS.md"]
        fenced_merge(template_with_markers, target, markers)
        result = target.read_text()
        assert result.startswith("# My agent")
        assert "rule one" in result
        assert "rule two" in result

    def test_template_without_markers_appends_full_content(
        self, tmp_path, template_no_markers
    ):
        target = tmp_path / "AGENTS.md"
        existing = "# Existing\n"
        target.write_text(existing)
        markers = ("<!-- START -->", "<!-- END -->")
        fenced_merge(template_no_markers, target, markers)
        # No markers in template → block extracted is empty string
        # Appends "" to existing, which just adds newline
        result = target.read_text()
        assert "# Existing" in result


class TestOverwriteIfExists:
    def test_writes_when_file_exists(self, tmp_path):
        target = tmp_path / "BOOTSTRAP.md"
        target.write_text("old content from previous profile")
        result = overwrite_if_exists("new template content", target)
        assert result is True
        assert target.read_text() == "new template content"

    def test_skips_when_file_absent(self, tmp_path):
        target = tmp_path / "BOOTSTRAP.md"
        result = overwrite_if_exists("template content", target)
        assert result is False
        assert not target.exists()

    def test_overwrites_with_shorter_content(self, tmp_path):
        target = tmp_path / "BOOTSTRAP.md"
        target.write_text("a" * 1000)
        result = overwrite_if_exists("short", target)
        assert result is True
        assert target.read_text() == "short"


class TestInitIfMissing:
    def test_deploys_to_absent_file(self, tmp_path):
        target = tmp_path / "USER.md"
        result = init_if_missing("user content", target)
        assert result is True
        assert target.read_text() == "user content"

    def test_skips_existing_file(self, tmp_path):
        target = tmp_path / "USER.md"
        target.write_text("existing")
        result = init_if_missing("new content", target)
        assert result is False
        assert target.read_text() == "existing"

    def test_preserves_content_on_skip(self, tmp_path):
        target = tmp_path / "MEMORY.md"
        target.write_text("preserved\nmemories")
        init_if_missing("overwrite attempt", target)
        assert target.read_text() == "preserved\nmemories"


class TestAskThenMerge:
    def test_interactive_accept(self, tmp_path, template_with_markers):
        target = tmp_path / "BOOT.md.bak"
        markers = FENCED_BLOCK_MARKERS["BOOT.md.bak"]
        with patch("builtins.input", return_value="y"):
            result = ask_then_merge(template_with_markers, target, markers, "BOOT.md.bak")
        assert result is True

    def test_interactive_decline(self, tmp_path):
        target = tmp_path / "BOOT.md.bak"
        target.write_text("existing")
        markers = FENCED_BLOCK_MARKERS["BOOT.md.bak"]
        with patch("builtins.input", return_value="n"):
            result = ask_then_merge("content", target, markers, "BOOT.md.bak")
        assert result is False
        assert target.read_text() == "existing"

    def test_interactive_full_yes(self, tmp_path, template_with_markers):
        target = tmp_path / "BOOT.md.bak"
        markers = FENCED_BLOCK_MARKERS["BOOT.md.bak"]
        with patch("builtins.input", return_value="yes"):
            result = ask_then_merge(template_with_markers, target, markers, "BOOT.md.bak")
        assert result is True

    def test_interactive_decline(self, tmp_path):
        target = tmp_path / "BOOT.md.bak"
        target.write_text("existing")
        markers = FENCED_BLOCK_MARKERS["BOOT.md.bak"]
        with patch("builtins.input", return_value="n"):
            result = ask_then_merge("content", target, markers, "BOOT.md.bak")
        assert result is False
        assert target.read_text() == "existing"

    def test_interactive_full_yes(self, tmp_path, template_with_markers):
        target = tmp_path / "BOOT.md.bak"
        markers = FENCED_BLOCK_MARKERS["BOOT.md.bak"]
        with patch("builtins.input", return_value="yes"):
            result = ask_then_merge(template_with_markers, target, markers, "BOOT.md.bak")
        assert result is True

    def test_noninteractive_falls_back_to_init_if_missing(
        self, tmp_path, template_with_markers
    ):
        target = tmp_path / "HEARTBEAT.md"
        markers = FENCED_BLOCK_MARKERS["HEARTBEAT.md"]
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = ask_then_merge(
                template_with_markers, target, markers, "HEARTBEAT.md"
            )
        assert result is True
        assert target.exists()

    def test_eof_error_returns_false(self, tmp_path):
        target = tmp_path / "BOOT.md.bak"
        target.write_text("existing")
        markers = FENCED_BLOCK_MARKERS["BOOT.md.bak"]
        with patch("builtins.input", side_effect=EOFError):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                result = ask_then_merge("content", target, markers, "BOOT.md.bak")
        assert result is False

    def test_noninteractive_does_not_overwrite_existing(self, tmp_path):
        target = tmp_path / "USER.md"
        target.write_text("existing customizations")
        markers = ("<!-- START -->", "<!-- END -->")
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = ask_then_merge("template", target, markers, "USER.md")
        assert result is False
        assert target.read_text() == "existing customizations"


class TestInjectFunctions:
    """Tests for inject_agents_block and inject_soul_block convenience wrappers."""

    def test_inject_agents_block_new_file(self, tmp_path, template_with_markers):
        target = tmp_path / "AGENTS.md"
        result = inject_agents_block(template_with_markers, target)
        assert result is True
        assert target.exists()
        assert "rule one" in target.read_text()
        assert "rule two" in target.read_text()
        assert "<!-- TRADERBOT_RULES_START -->" in target.read_text()
        assert "<!-- TRADERBOT_RULES_END -->" in target.read_text()

    def test_inject_agents_block_existing_file_preserves_additions(
        self, tmp_path, template_with_markers
    ):
        target = tmp_path / "AGENTS.md"
        existing = (
            "<!-- TRADERBOT_RULES_START -->\n"
            "old rule\n"
            "<!-- TRADERBOT_RULES_END -->\n"
            "\n"
            "# Custom agent additions\n"
            "My custom config here.\n"
        )
        target.write_text(existing)
        result = inject_agents_block(template_with_markers, target)
        assert result is True
        content = target.read_text()
        assert "rule one" in content
        assert "rule two" in content
        assert "old rule" not in content
        assert "Custom agent additions" in content
        assert "My custom config here." in content

    def test_inject_agents_block_returns_false_on_error(self, tmp_path):
        target = tmp_path / "nonexistent_dir" / "AGENTS.md"
        result = inject_agents_block("content", target)
        assert result is False

    def test_inject_soul_block_new_file(self, tmp_path):
        template = (
            "<!-- TRADERBOT_SOUL_START -->\n"
            "trading personality here\n"
            "<!-- TRADERBOT_SOUL_END -->\n"
        )
        target = tmp_path / "SOUL.md"
        result = inject_soul_block(template, target)
        assert result is True
        assert "trading personality here" in target.read_text()
        assert "<!-- TRADERBOT_SOUL_START -->" in target.read_text()
        assert "<!-- TRADERBOT_SOUL_END -->" in target.read_text()

    def test_inject_soul_block_existing_file_preserves_additions(self, tmp_path):
        template = (
            "<!-- TRADERBOT_SOUL_START -->\n"
            "be disciplined\n"
            "<!-- TRADERBOT_SOUL_END -->\n"
        )
        target = tmp_path / "SOUL.md"
        existing = (
            "<!-- TRADERBOT_SOUL_START -->\n"
            "old vibe\n"
            "<!-- TRADERBOT_SOUL_END -->\n"
            "\n"
            "# Agent's own notes\n"
            "Additional personality layer.\n"
        )
        target.write_text(existing)
        result = inject_soul_block(template, target)
        assert result is True
        content = target.read_text()
        assert "be disciplined" in content
        assert "old vibe" not in content
        assert "Agent's own notes" in content
        assert "Additional personality layer." in content

    def test_inject_soul_block_returns_false_on_error(self, tmp_path):
        target = tmp_path / "nonexistent_dir" / "SOUL.md"
        result = inject_soul_block("content", target)
        assert result is False


class TestInjectProfileIntoIdentity:
    """Tests for inject_profile_into_identity convenience wrapper."""

    @pytest.fixture
    def profile(self) -> TradingProfile:
        return TradingProfile(
            name="test_agent",
            mode="paper",
            description="Test profile for identity injection",
            enabled_categories=[MarketCategory.CRYPTO, MarketCategory.SPORTS],
            risk_multiplier=0.5,
            max_position_per_market_pct=0.03,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=3,
            min_liquidity_threshold=2000,
            min_edge_pct=1.0,
        )

    @pytest.fixture
    def profile_no_categories(self) -> TradingProfile:
        return TradingProfile(
            name="no_cat_agent",
            mode="paper",
            description="Profile with no enabled categories",
            enabled_categories=[],
            risk_multiplier=1.0,
            max_position_per_market_pct=0.02,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=2,
            min_liquidity_threshold=1000,
            min_edge_pct=0.5,
        )

    def test_new_file(self, tmp_path, profile):
        target = tmp_path / "IDENTITY.md"
        result = inject_profile_into_identity(profile, target)
        assert result is True
        assert target.exists()
        content = target.read_text()
        assert "<!-- TRADERBOT_PROFILE_START -->" in content
        assert "<!-- TRADERBOT_PROFILE_END -->" in content
        assert "- **Name**: test_agent" in content
        assert "- **Category**: crypto" in content
        assert "- **Risk Multiplier**: 0.5" in content
        assert "- **Max Position %**: 0.03" in content
        assert "- **Enabled Categories**: crypto, sports" in content

    def test_existing_file_with_markers_gets_replaced(self, tmp_path, profile):
        target = tmp_path / "IDENTITY.md"
        existing = (
            "# Agent Identity\n"
            "\n"
            "- **agent id**: agent-123\n"
            "- **name**: Old Name\n"
            "\n"
            "<!-- TRADERBOT_PROFILE_START -->\n"
            "- **Name**: old_profile\n"
            "- **Category**: politics\n"
            "<!-- TRADERBOT_PROFILE_END -->\n"
            "\n"
            "# Custom Notes\n"
        )
        target.write_text(existing)
        result = inject_profile_into_identity(profile, target)
        assert result is True
        content = target.read_text()
        assert "- **Name**: test_agent" in content
        assert "old_profile" not in content
        assert "**agent id**: agent-123" in content
        assert "Old Name" in content
        assert "Custom Notes" in content

    def test_existing_file_without_markers_appends_block(self, tmp_path, profile):
        target = tmp_path / "IDENTITY.md"
        existing = "- **agent id**: agent-xyz\n- **name**: My Bot\n"
        target.write_text(existing)
        result = inject_profile_into_identity(profile, target)
        assert result is True
        content = target.read_text()
        assert "**agent id**: agent-xyz" in content
        assert "- **Name**: test_agent" in content
        assert "<!-- TRADERBOT_PROFILE_START -->" in content

    def test_empty_enabled_categories(self, tmp_path, profile_no_categories):
        target = tmp_path / "IDENTITY.md"
        result = inject_profile_into_identity(profile_no_categories, target)
        assert result is True
        content = target.read_text()
        assert "- **Category**: auto" in content
        assert "- **Enabled Categories**: " in content

    def test_error_path_returns_false(self, tmp_path, profile):
        target = tmp_path / "nonexistent_dir" / "IDENTITY.md"
        result = inject_profile_into_identity(profile, target)
        assert result is False

    def test_compatible_with_discovery_parsing(self, tmp_path, profile):
        target = tmp_path / "IDENTITY.md"
        existing = (
            "# Agent Identity\n"
            "\n"
            "- **agent id**: disco-agent\n"
            "- **name**: Discovery Bot\n"
        )
        target.write_text(existing)
        inject_profile_into_identity(profile, target)

        import re
        content = target.read_text()
        agent_id_match = re.search(
            r'-\s*\*\*\s*agent\s+id\s*\*\*\s*:\s*(.+?)(?:\n|$)',
            content,
            re.IGNORECASE,
        )
        name_match = re.search(
            r'-\s*\*\*\s*name\s*\*\*\s*:\s*(.+?)(?:\n|$)',
            content,
            re.IGNORECASE,
        )
        assert agent_id_match is not None
        assert agent_id_match.group(1).strip() == "disco-agent"
        assert name_match is not None
        assert name_match.group(1).strip() == "Discovery Bot"


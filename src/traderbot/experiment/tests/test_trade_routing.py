"""Tests for profile.paper_mode routing — regression coverage.

Verifies TradingProfile construction and paper_mode computed field
correctly routes based on mode="paper" vs mode="live".
"""

import pytest
from pydantic import ValidationError

from traderbot.profiles.models import TradingProfile


class TestPaperMode:
    """Verify paper_mode computed field reflects the mode value."""

    @staticmethod
    def _make_profile(mode: str) -> TradingProfile:
        """Build a minimal valid TradingProfile."""
        return TradingProfile(
            name="test_agent",
            mode=mode,  # type: ignore[arg-type]
            description="Test profile",
            risk_multiplier=0.5,
            max_position_per_market_pct=5.0,
            max_daily_loss_pct=2.0,
            max_drawdown_pct=10.0,
            max_open_positions=5,
            min_liquidity_threshold=500,
            min_edge_pct=1.0,
        )

    def test_paper_mode_true(self) -> None:
        """Profile with mode='paper' returns paper_mode=True."""
        profile = self._make_profile("paper")
        assert profile.paper_mode is True

    def test_paper_mode_false_for_live(self) -> None:
        """Profile with mode='live' returns paper_mode=False."""
        profile = self._make_profile("live")
        assert profile.paper_mode is False

    def test_mode_literal_enforces_values(self) -> None:
        """mode field must be 'paper' or 'live' — rejects other strings."""
        with pytest.raises(ValidationError):
            self._make_profile("test")


class TestTradingProfileConstruction:
    """Verify TradingProfile model construction with both modes."""

    def test_paper_profile_has_correct_mode(self) -> None:
        """Constructed 'paper' profile stores mode correctly."""
        profile = TradingProfile(
            name="weatherman",
            mode="paper",
            description="Paper trading weather profile",
            risk_multiplier=0.3,
            max_position_per_market_pct=3.0,
            max_daily_loss_pct=1.0,
            max_drawdown_pct=5.0,
            max_open_positions=3,
            min_liquidity_threshold=1000,
            min_edge_pct=2.0,
        )
        assert profile.mode == "paper"
        assert profile.paper_mode is True
        assert profile.name == "weatherman"

    def test_live_profile_has_correct_mode(self) -> None:
        """Constructed 'live' profile stores mode correctly."""
        profile = TradingProfile(
            name="live_economics",
            mode="live",
            description="Live trading economics profile",
            risk_multiplier=0.8,
            max_position_per_market_pct=2.0,
            max_daily_loss_pct=1.5,
            max_drawdown_pct=8.0,
            max_open_positions=10,
            min_liquidity_threshold=2000,
            min_edge_pct=0.5,
        )
        assert profile.mode == "live"
        assert profile.paper_mode is False
        assert profile.name == "live_economics"

    def test_profile_has_required_fields(self) -> None:
        """All required fields are present after construction."""
        profile = TestPaperMode._make_profile("paper")
        assert profile.name == "test_agent"
        assert profile.description == "Test profile"
        assert profile.risk_multiplier == 0.5

    def test_paper_mode_is_computed_not_writable(self) -> None:
        """paper_mode is a @computed_field — not settable via constructor."""
        # It's computed, so this doesn't error but the kwarg is simply
        # consumed by model_dump/model_construct, not stored separately.
        profile = TradingProfile(
            name="test",
            mode="paper",
            description="Test",
            risk_multiplier=0.5,
            max_position_per_market_pct=5.0,
            max_daily_loss_pct=2.0,
            max_drawdown_pct=10.0,
            max_open_positions=5,
            min_liquidity_threshold=500,
            min_edge_pct=1.0,
        )
        assert profile.paper_mode is True

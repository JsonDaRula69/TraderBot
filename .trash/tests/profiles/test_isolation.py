"""Tests for per-profile data isolation path resolution."""

from pathlib import Path
from typing import Any

import pytest

from traderbot.profiles.isolation import (
    ensure_profile_dirs,
    get_profile_audit_path,
    get_profile_chroma_path,
    get_profile_db_path,
)
from traderbot.profiles.models import TradingProfile


@pytest.fixture
def paper_profile() -> TradingProfile:
    """Create a paper trading profile for testing."""
    return TradingProfile(
        name="test-paper",
        mode="paper",
        description="Test paper profile",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.04,
        max_daily_loss_pct=0.015,
        max_drawdown_pct=0.08,
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )


@pytest.fixture
def live_profile() -> TradingProfile:
    """Create a live trading profile for testing."""
    return TradingProfile(
        name="test-live",
        mode="live",
        description="Test live profile",
        risk_multiplier=0.3,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=3,
        min_liquidity_threshold=2000,
        min_edge_pct=0.04,
    )


def test_get_profile_db_path_paper(paper_profile: TradingProfile) -> None:
    """Get profile DB path returns correct path with paper base_dir."""
    path = get_profile_db_path(paper_profile, "decisions.db")
    assert path.as_posix().endswith("/.traderbot/paper-test-paper/db/decisions.db")
    assert "/.traderbot/paper-test-paper" in path.as_posix()


def test_get_profile_db_path_live(live_profile: TradingProfile) -> None:
    """Get profile DB path returns correct path with live base_dir."""
    path = get_profile_db_path(live_profile, "learnings.db")
    assert path.as_posix().endswith("/.traderbot/live-test-live/db/learnings.db")
    assert "/.traderbot/live-test-live" in path.as_posix()


def test_get_profile_chroma_path_paper(paper_profile: TradingProfile) -> None:
    """Get profile ChromaDB path returns correct path."""
    path = get_profile_chroma_path(paper_profile)
    assert path.as_posix().endswith("/.traderbot/paper-test-paper/chroma")
    assert "/.traderbot/paper-test-paper" in path.as_posix()


def test_get_profile_chroma_path_live(live_profile: TradingProfile) -> None:
    """Get profile ChromaDB path returns correct path."""
    path = get_profile_chroma_path(live_profile)
    assert path.as_posix().endswith("/.traderbot/live-test-live/chroma")
    assert "/.traderbot/live-test-live" in path.as_posix()


def test_get_profile_audit_path_paper(paper_profile: TradingProfile) -> None:
    """Get profile audit path returns correct path."""
    path = get_profile_audit_path(paper_profile)
    assert path.as_posix().endswith("/.traderbot/paper-test-paper/audit")
    assert "/.traderbot/paper-test-paper" in path.as_posix()


def test_get_profile_audit_path_live(live_profile: TradingProfile) -> None:
    """Get profile audit path returns correct path."""
    path = get_profile_audit_path(live_profile)
    assert path.as_posix().endswith("/.traderbot/live-test-live/audit")
    assert "/.traderbot/live-test-live" in path.as_posix()


def test_ensure_profile_dirs_creates_all(
    paper_profile: TradingProfile, tmp_path: Path, monkeypatch: Any
) -> None:
    """Ensure profile dirs creates all directories."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    ensure_profile_dirs(paper_profile)

    # Check all directories exist
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "db").exists()
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "chroma").exists()
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "audit").exists()

    # Check they are directories
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "db").is_dir()
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "chroma").is_dir()
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "audit").is_dir()


def test_ensure_profile_dirs_idempotent(
    paper_profile: TradingProfile, tmp_path: Path, monkeypatch: Any
) -> None:
    """Ensure profile dirs is idempotent (can be called multiple times)."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Call twice
    ensure_profile_dirs(paper_profile)
    ensure_profile_dirs(paper_profile)

    # Should still work
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "db").exists()
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "chroma").exists()
    assert (tmp_path / ".traderbot" / "paper-test-paper" / "audit").exists()


# Made with Bob

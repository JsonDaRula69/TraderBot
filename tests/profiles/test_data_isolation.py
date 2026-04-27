"""Integration tests for per-profile data isolation."""

import sqlite3
from pathlib import Path

import pytest

from traderbot.db import decisions, learnings, positions
from traderbot.kalshi.models import Decision, Position
from traderbot.profiles.isolation import ensure_profile_dirs, get_profile_db_path
from traderbot.profiles.models import TradingProfile


@pytest.fixture
def profile1() -> TradingProfile:
    """Create first test profile."""
    return TradingProfile(
        name="profile1",
        mode="paper",
        description="Test profile 1",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.04,
        max_daily_loss_pct=0.015,
        max_drawdown_pct=0.08,
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )


@pytest.fixture
def profile2() -> TradingProfile:
    """Create second test profile (live mode for isolation)."""
    return TradingProfile(
        name="profile2",
        mode="live",
        description="Test profile 2",
        risk_multiplier=0.3,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=3,
        min_liquidity_threshold=2000,
        min_edge_pct=0.04,
    )


@pytest.fixture
def sample_decision() -> Decision:
    """Create a sample decision for testing."""
    from datetime import UTC, datetime
    return Decision(
        timestamp=datetime.now(UTC),
        ticker="TEST-MARKET",
        direction="yes",
        quantity=10,
        price=5000,
        signal_strength=0.8,
        confidence=0.7,
        edge_estimate=0.15,
        risk_checks={"position_size": True, "daily_loss": True},
        outcome="executed",
    )


@pytest.fixture
def sample_position() -> Position:
    """Create a sample position for testing."""
    return Position(
        ticker="TEST-MARKET",
        quantity=10,
        avg_price=5000,
    )


def test_decision_isolation(profile1: TradingProfile, profile2: TradingProfile, sample_decision: Decision, tmp_path: Path) -> None:
    """Create decision in profile1 → not visible in profile2."""
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        ensure_profile_dirs(profile1)
        ensure_profile_dirs(profile2)
        
        # Create decision in profile1
        db_path1 = get_profile_db_path(profile1, "decisions.db")
        conn1 = sqlite3.connect(db_path1)
        conn1.row_factory = sqlite3.Row
        decisions.init_table(conn1)
        decision_id = decisions.insert(conn1, sample_decision)
        conn1.close()
        
        # Verify it exists in profile1
        conn1 = sqlite3.connect(db_path1)
        conn1.row_factory = sqlite3.Row
        assert decisions.count(conn1) == 1
        retrieved = decisions.get(conn1, decision_id)
        assert retrieved is not None
        assert retrieved.ticker == "TEST-MARKET"
        conn1.close()
        
        # Verify it does NOT exist in profile2
        db_path2 = get_profile_db_path(profile2, "decisions.db")
        conn2 = sqlite3.connect(db_path2)
        conn2.row_factory = sqlite3.Row
        decisions.init_table(conn2)
        assert decisions.count(conn2) == 0
        conn2.close()
    finally:
        os.chdir(original_cwd)


def test_learning_isolation(profile1: TradingProfile, profile2: TradingProfile, tmp_path: Path) -> None:
    """Create learning in profile1 → not visible in profile2."""
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        ensure_profile_dirs(profile1)
        ensure_profile_dirs(profile2)
        
        # Create learning in profile1
        db_path1 = get_profile_db_path(profile1, "learnings.db")
        conn1 = sqlite3.connect(db_path1)
        conn1.row_factory = sqlite3.Row
        learnings.init_table(conn1)
        learning_id = learnings.record_pattern(
            conn1,
            learnings.LearningCategory.MARKET_BEHAVIOR,
            "Test pattern",
            "Test evidence",
            0.8,
        )
        conn1.close()
        
        # Verify it exists in profile1
        conn1 = sqlite3.connect(db_path1)
        conn1.row_factory = sqlite3.Row
        assert learnings.count(conn1) == 1
        retrieved = learnings.get(conn1, learning_id)
        assert retrieved is not None
        assert retrieved.summary == "Test pattern"
        conn1.close()
        
        # Verify it does NOT exist in profile2
        db_path2 = get_profile_db_path(profile2, "learnings.db")
        conn2 = sqlite3.connect(db_path2)
        conn2.row_factory = sqlite3.Row
        learnings.init_table(conn2)
        assert learnings.count(conn2) == 0
        conn2.close()
    finally:
        os.chdir(original_cwd)


def test_position_isolation(profile1: TradingProfile, profile2: TradingProfile, sample_position: Position, tmp_path: Path) -> None:
    """Create position in profile1 → not visible in profile2."""
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        ensure_profile_dirs(profile1)
        ensure_profile_dirs(profile2)
        
        # Create position in profile1
        db_path1 = get_profile_db_path(profile1, "positions.db")
        conn1 = sqlite3.connect(db_path1)
        conn1.row_factory = sqlite3.Row
        positions.init_table(conn1)
        positions.upsert(conn1, sample_position)
        conn1.close()
        
        # Verify it exists in profile1
        conn1 = sqlite3.connect(db_path1)
        conn1.row_factory = sqlite3.Row
        retrieved = positions.get(conn1, "TEST-MARKET")
        assert retrieved is not None
        assert retrieved.quantity == 10
        conn1.close()
        
        # Verify it does NOT exist in profile2
        db_path2 = get_profile_db_path(profile2, "positions.db")
        conn2 = sqlite3.connect(db_path2)
        conn2.row_factory = sqlite3.Row
        positions.init_table(conn2)
        retrieved2 = positions.get(conn2, "TEST-MARKET")
        assert retrieved2 is None
        conn2.close()
    finally:
        os.chdir(original_cwd)


def test_no_profile_uses_default_paths(sample_decision: Decision, tmp_path: Path) -> None:
    """No profile → uses default paths (backward compatibility)."""
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        
        # Create decision without profile (uses default path)
        default_db = tmp_path / "decisions.db"
        conn = sqlite3.connect(default_db)
        conn.row_factory = sqlite3.Row
        decisions.init_table(conn)
        decision_id = decisions.insert(conn, sample_decision)
        conn.close()
        
        # Verify it exists
        conn = sqlite3.connect(default_db)
        conn.row_factory = sqlite3.Row
        assert decisions.count(conn) == 1
        retrieved = decisions.get(conn, decision_id)
        assert retrieved is not None
        conn.close()
    finally:
        os.chdir(original_cwd)


class TestProfileDataIsolationNegative:
    """Negative tests: Profile A CANNOT read Profile B's data."""

    def test_profile_a_cannot_read_profile_b_decisions(
        self, profile1: TradingProfile, profile2: TradingProfile, sample_decision: Decision, tmp_path: Path
    ) -> None:
        """Decisions stored in profile1 DB are invisible to profile2."""
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ensure_profile_dirs(profile1)
            ensure_profile_dirs(profile2)

            db_path1 = get_profile_db_path(profile1, "decisions.db")
            conn1 = sqlite3.connect(db_path1)
            conn1.row_factory = sqlite3.Row
            decisions.init_table(conn1)
            decisions.insert(conn1, sample_decision)
            conn1.close()

            db_path2 = get_profile_db_path(profile2, "decisions.db")
            conn2 = sqlite3.connect(db_path2)
            conn2.row_factory = sqlite3.Row
            decisions.init_table(conn2)
            assert decisions.count(conn2) == 0
            conn2.close()
        finally:
            os.chdir(original_cwd)


class TestKeyringCredentialIsolation:
    """Verify Profile A's keyring credentials are NOT accessible from Profile B's namespace."""

    def test_profile_a_credentials_not_in_profile_b_namespace(self) -> None:
        from traderbot.profiles.auth import ProfileAuthStore
        from traderbot.profiles.models import TradingProfile

        class MockKeyring:
            def __init__(self):
                self._store: dict[tuple[str, str], str] = {}

            def set_password(self, service: str, username: str, password: str) -> None:
                self._store[(service, username)] = password

            def get_password(self, service: str, username: str) -> str | None:
                return self._store.get((service, username))

            def delete_password(self, service: str, username: str) -> None:
                self._store.pop((service, username), None)

        mock_kr = MockKeyring()

        profile_a = TradingProfile(
            name="alpha", mode="paper", description="A",
            risk_multiplier=0.5, max_position_per_market_pct=0.05,
            max_daily_loss_pct=0.02, max_drawdown_pct=0.10,
            max_open_positions=5, min_liquidity_threshold=1000, min_edge_pct=0.03,
        )
        profile_b = TradingProfile(
            name="beta", mode="paper", description="B",
            risk_multiplier=0.5, max_position_per_market_pct=0.05,
            max_daily_loss_pct=0.02, max_drawdown_pct=0.10,
            max_open_positions=5, min_liquidity_threshold=1000, min_edge_pct=0.03,
        )

        auth_a = ProfileAuthStore(profile_a, keyring_module=mock_kr)
        auth_b = ProfileAuthStore(profile_b, keyring_module=mock_kr)

        auth_a.set_credentials("kalshi", "key_a", "secret_a")

        assert auth_a.get_credentials("kalshi") == ("key_a", "secret_a")
        assert auth_b.get_credentials("kalshi") is None

    def test_profile_b_writes_do_not_overwrite_a(self) -> None:
        from traderbot.profiles.auth import ProfileAuthStore
        from traderbot.profiles.models import TradingProfile

        class MockKeyring:
            def __init__(self):
                self._store: dict[tuple[str, str], str] = {}

            def set_password(self, service: str, username: str, password: str) -> None:
                self._store[(service, username)] = password

            def get_password(self, service: str, username: str) -> str | None:
                return self._store.get((service, username))

            def delete_password(self, service: str, username: str) -> None:
                self._store.pop((service, username), None)

        mock_kr = MockKeyring()

        profile_a = TradingProfile(
            name="alpha", mode="paper", description="A",
            risk_multiplier=0.5, max_position_per_market_pct=0.05,
            max_daily_loss_pct=0.02, max_drawdown_pct=0.10,
            max_open_positions=5, min_liquidity_threshold=1000, min_edge_pct=0.03,
        )
        profile_b = TradingProfile(
            name="beta", mode="paper", description="B",
            risk_multiplier=0.5, max_position_per_market_pct=0.05,
            max_daily_loss_pct=0.02, max_drawdown_pct=0.10,
            max_open_positions=5, min_liquidity_threshold=1000, min_edge_pct=0.03,
        )

        auth_a = ProfileAuthStore(profile_a, keyring_module=mock_kr)
        auth_b = ProfileAuthStore(profile_b, keyring_module=mock_kr)

        auth_a.set_credentials("kalshi", "key_a", "secret_a")
        auth_b.set_credentials("kalshi", "key_b", "secret_b")

        assert auth_a.get_credentials("kalshi") == ("key_a", "secret_a")
        assert auth_b.get_credentials("kalshi") == ("key_b", "secret_b")


class TestRevokedTokenResolution:
    """When TRADERBOT_PROFILE_TOKEN is set to a revoked token, resolution FAILS."""

    def test_revoked_token_returns_none(self) -> None:
        from traderbot.profiles.tokens import revoke_token, resolve_token, set_keyring

        class MockKeyring:
            def __init__(self):
                self._store: dict[tuple[str, str], str] = {}

            def set_password(self, service: str, username: str, password: str) -> None:
                self._store[(service, username)] = password

            def get_password(self, service: str, username: str) -> str | None:
                return self._store.get((service, username))

            def delete_password(self, service: str, username: str) -> None:
                self._store.pop((service, username), None)

        mock_kr = MockKeyring()
        set_keyring(mock_kr)

        from traderbot.profiles.tokens import assign_token, generate_token
        token = generate_token()
        assign_token("test_profile", "test_agent", token)

        result = resolve_token(token)
        assert result is not None

        revoke_token(token)
        result_after_revoke = resolve_token(token)
        assert result_after_revoke is None

        set_keyring(None)


    def test_nonexistent_token_returns_none(self) -> None:
        from traderbot.profiles.tokens import resolve_token, set_keyring

        class MockKeyring:
            def __init__(self):
                self._store: dict[tuple[str, str], str] = {}

            def set_password(self, service: str, username: str, password: str) -> None:
                self._store[(service, username)] = password

            def get_password(self, service: str, username: str) -> str | None:
                return self._store.get((service, username))

            def delete_password(self, service: str, username: str) -> None:
                self._store.pop((service, username), None)

        mock_kr = MockKeyring()
        set_keyring(mock_kr)

        result = resolve_token("nonexistent_token_12345")
        assert result is None

        set_keyring(None)

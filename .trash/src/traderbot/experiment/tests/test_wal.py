"""Tests for WalStatus and WalAction enums — regression coverage for recent bug fixes.

These tests verify the enum definitions in traderbot.wal remain correct,
covering the addition of REJECTED and EXECUTED statuses.
"""


from traderbot.wal import WalAction, WalStatus


class TestWalStatus:
    """Verify all WalStatus enum members exist and have correct values."""

    def test_all_statuses_exist(self) -> None:
        """All expected WalStatus members must be present."""
        expected = {
            "PENDING",
            "COMPLETED",
            "REJECTED",
            "EXECUTED",
            "CANCELLED",
            "EXPIRED",
        }
        actual = set(WalStatus.__members__.keys())
        assert actual == expected, f"WalStatus members mismatch: {actual} != {expected}"

    def test_rejected_exists(self) -> None:
        """WalStatus.REJECTED must exist (recent bug fix)."""
        assert hasattr(WalStatus, "REJECTED")
        assert WalStatus.REJECTED == "REJECTED"

    def test_executed_exists(self) -> None:
        """WalStatus.EXECUTED must exist (recent bug fix)."""
        assert hasattr(WalStatus, "EXECUTED")
        assert WalStatus.EXECUTED == "EXECUTED"

    def test_pending_value(self) -> None:
        """WalStatus.PENDING retains correct value."""
        assert WalStatus.PENDING == "PENDING"

    def test_completed_value(self) -> None:
        """WalStatus.COMPLETED retains correct value."""
        assert WalStatus.COMPLETED == "COMPLETED"

    def test_cancelled_value(self) -> None:
        """WalStatus.CANCELLED retains correct value."""
        assert WalStatus.CANCELLED == "CANCELLED"

    def test_expired_value(self) -> None:
        """WalStatus.EXPIRED retains correct value."""
        assert WalStatus.EXPIRED == "EXPIRED"

    def test_statuses_are_strings(self) -> None:
        """All WalStatus values must be usable as strings."""
        for status in WalStatus:
            assert isinstance(status.value, str)
            assert status == status.value


class TestWalAction:
    """Verify WalAction enum members exist and have correct values."""

    def test_buy_exists(self) -> None:
        """WalAction.BUY must exist."""
        assert hasattr(WalAction, "BUY")
        assert WalAction.BUY == "BUY"

    def test_sell_exists(self) -> None:
        """WalAction.SELL must exist."""
        assert hasattr(WalAction, "SELL")
        assert WalAction.SELL == "SELL"

    def test_buy_is_not_sell(self) -> None:
        """BUY and SELL are distinct enum values."""
        assert WalAction.BUY != WalAction.SELL

    def test_actions_are_strings(self) -> None:
        """All WalAction values must be usable as strings."""
        for action in WalAction:
            assert isinstance(action.value, str)

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traderbot.deploy.backfill_window import calendar_window


def test_calendar_window_clamps_day_at_month_boundary() -> None:
    window = calendar_window(6, datetime(2026, 8, 31, 14, 15, tzinfo=UTC))

    assert window.start == datetime(2026, 2, 28, 14, 15, tzinfo=UTC)
    assert window.end == datetime(2026, 8, 31, 14, 15, tzinfo=UTC)


@pytest.mark.parametrize("months", [True, False, 0, -1, 61, 1.5, "6"])
def test_calendar_window_rejects_invalid_months(months: int) -> None:
    with pytest.raises(ValueError):
        _ = calendar_window(months, datetime(2026, 8, 11, tzinfo=UTC))


def test_calendar_window_rejects_naive_clock() -> None:
    with pytest.raises(ValueError):
        _ = calendar_window(6, datetime(2026, 8, 11))

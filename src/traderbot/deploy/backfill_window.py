from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import override


@dataclass(frozen=True, slots=True)
class BackfillWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class BackfillWindowError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return f"invalid backfill window: {self.reason}"


def calendar_window(months: int, now: datetime) -> BackfillWindow:
    if type(months) is not int or not 1 <= months <= 60:
        raise BackfillWindowError("months must be an integer between 1 and 60")
    if now.tzinfo is None or now.utcoffset() is None:
        raise BackfillWindowError("clock must return an aware datetime")
    end = now.astimezone(UTC)
    absolute_month = end.year * 12 + end.month - 1 - months
    year, zero_based_month = divmod(absolute_month, 12)
    month = zero_based_month + 1
    day = min(end.day, calendar.monthrange(year, month)[1])
    return BackfillWindow(start=end.replace(year=year, month=month, day=day), end=end)


__all__ = ["BackfillWindow", "BackfillWindowError", "calendar_window"]

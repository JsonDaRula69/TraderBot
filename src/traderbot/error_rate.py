"""Error rate monitoring and surge detection."""

from __future__ import annotations

import threading
import time


class ErrorRateMonitor:
    """Track error occurrence rate and detect surges.

    Thread-safe monitor that records error timestamps and computes
    per-minute rates over a sliding window.

    Parameters
    ----------
    threshold:
        Maximum errors allowed within *window_seconds* before
        :meth:`is_surge` returns ``True``.
    window_seconds:
        Sliding window duration in seconds.
    """

    def __init__(self, threshold: int = 10, window_seconds: int = 60) -> None:
        self.threshold = threshold
        self.window_seconds = window_seconds
        self._errors: list[float] = []
        self._lock = threading.Lock()

    def record(self, error_code: int = 0) -> None:
        """Record an error occurrence at the current time."""
        now = time.monotonic()
        with self._lock:
            self._errors.append(now)
            self._prune(now)

    def is_surge(self) -> bool:
        """Return ``True`` if error count within the window exceeds the threshold."""
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            return len(self._errors) > self.threshold

    def rate(self) -> float:
        """Return errors per minute within the current window."""
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if not self._errors:
                return 0.0
            elapsed_minutes = self.window_seconds / 60.0
            return len(self._errors) / elapsed_minutes

    def reset(self) -> None:
        """Clear all recorded errors."""
        with self._lock:
            self._errors.clear()

    def _prune(self, now: float) -> None:
        """Remove timestamps outside the sliding window (caller must hold the lock)."""
        cutoff = now - self.window_seconds
        while self._errors and self._errors[0] < cutoff:
            self._errors.pop(0)

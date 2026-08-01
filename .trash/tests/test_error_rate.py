"""Tests for traderbot.error_rate — ErrorRateMonitor."""

from __future__ import annotations

import threading
import time

from traderbot.error_rate import ErrorRateMonitor


class TestErrorRateMonitorRecord:
    def test_record_increases_count(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=60)
        assert not monitor.is_surge()
        monitor.record()
        monitor.record()
        assert len(monitor._errors) == 2

    def test_record_with_error_code(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=60)
        monitor.record(error_code=3000)
        monitor.record(error_code=5000)
        assert len(monitor._errors) == 2


class TestErrorRateMonitorIsSurge:
    def test_no_errors_no_surge(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=60)
        assert not monitor.is_surge()

    def test_below_threshold_no_surge(self):
        monitor = ErrorRateMonitor(threshold=5, window_seconds=60)
        for _ in range(5):
            monitor.record()
        assert not monitor.is_surge()

    def test_at_threshold_no_surge(self):
        monitor = ErrorRateMonitor(threshold=5, window_seconds=60)
        for _ in range(5):
            monitor.record()
        assert not monitor.is_surge()

    def test_above_threshold_is_surge(self):
        monitor = ErrorRateMonitor(threshold=5, window_seconds=60)
        for _ in range(6):
            monitor.record()
        assert monitor.is_surge()

    def test_default_threshold(self):
        monitor = ErrorRateMonitor()
        assert monitor.threshold == 10
        assert monitor.window_seconds == 60


class TestErrorRateMonitorRate:
    def test_rate_zero_when_empty(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=60)
        assert monitor.rate() == 0.0

    def test_rate_computation(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=60)
        for _ in range(6):
            monitor.record()
        rate = monitor.rate()
        assert rate == 6.0

    def test_rate_per_minute(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=300)
        for _ in range(12):
            monitor.record()
        rate = monitor.rate()
        assert rate == 2.4


class TestErrorRateMonitorReset:
    def test_reset_clears_errors(self):
        monitor = ErrorRateMonitor(threshold=5, window_seconds=60)
        for _ in range(10):
            monitor.record()
        assert monitor.is_surge()
        monitor.reset()
        assert not monitor.is_surge()
        assert monitor.rate() == 0.0


class TestErrorRateMonitorWindowExpiry:
    def test_old_errors_expire(self):
        monitor = ErrorRateMonitor(threshold=5, window_seconds=1)
        for _ in range(10):
            monitor.record()
        assert monitor.is_surge()
        time.sleep(1.1)
        assert not monitor.is_surge()

    def test_mixed_old_and_new(self):
        monitor = ErrorRateMonitor(threshold=5, window_seconds=2)
        for _ in range(3):
            monitor.record()
        time.sleep(0.6)
        for _ in range(3):
            monitor.record()
        monitor.is_surge()
        assert len(monitor._errors) >= 3

    def test_rate_drops_after_window(self):
        monitor = ErrorRateMonitor(threshold=10, window_seconds=1)
        for _ in range(5):
            monitor.record()
        assert monitor.rate() > 0
        time.sleep(1.1)
        assert monitor.rate() == 0.0


class TestErrorRateMonitorThreadSafety:
    def test_concurrent_records(self):
        monitor = ErrorRateMonitor(threshold=100, window_seconds=60)
        errors_per_thread = 20
        num_threads = 5

        def record_errors():
            for _ in range(errors_per_thread):
                monitor.record()

        threads = [threading.Thread(target=record_errors) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(monitor._errors) == errors_per_thread * num_threads

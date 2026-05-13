from __future__ import annotations

import logging

import pytest  # noqa: TC002

from traderbot.logging_config import (
    configure_root_logger,
    get_logger,
    log_cache_event,
    log_market_event,
    log_reconciliation_event,
    log_settlement_event,
)


class TestConfigureRootLogger:
    def test_idempotent_configuration_no_error(self) -> None:
        configure_root_logger()
        configure_root_logger()

    def test_adds_stream_handler(self) -> None:
        configure_root_logger()
        stream_handlers = [
            h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler)
        ]
        assert any(isinstance(h, logging.StreamHandler) for h in stream_handlers)


class TestGetLogger:
    def test_returns_logger(self) -> None:
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"


class TestLogFormatters:
    def test_log_market_event(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="test_market"):
            logger = logging.getLogger("test_market")
            log_market_event(logger, "order_placed", "BTC-100K", side="yes", qty=10)
            assert "market" in caplog.text
            assert "order_placed" in caplog.text
            assert "BTC-100K" in caplog.text

    def test_log_cache_event(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="test_cache"):
            logger = logging.getLogger("test_cache")
            log_cache_event(logger, "get_market", "TEST", hit=True)
            assert "cache" in caplog.text
            assert "TEST" in caplog.text

    def test_log_settlement_event(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="test_settle"):
            logger = logging.getLogger("test_settle")
            log_settlement_event(logger, "TEST-MKT", outcome=True, source="startup")
            assert "settlement" in caplog.text
            assert "TEST-MKT" in caplog.text

    def test_log_reconciliation_event(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="test_recon"):
            logger = logging.getLogger("test_recon")
            log_reconciliation_event(logger, "DRIFT-MKT", drift_cents=500, paper_side="yes")
            assert "reconciliation" in caplog.text
            assert "DRIFT-MKT" in caplog.text

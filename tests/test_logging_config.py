from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from traderbot.logging_config import (
    configure_root_logger,
    get_logger,
    log_cache_event,
    log_market_event,
    log_reconciliation_event,
    log_settlement_event,
)


class TestConfigureRootLogger:
    def test_configures_stderr_handler(self) -> None:
        configure_root_logger()
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert any(
            isinstance(h, logging.StreamHandler) for h in root.handlers
        )

    def test_idempotent(self) -> None:
        configure_root_logger()
        root = logging.getLogger()
        count = len(root.handlers)
        configure_root_logger()
        assert len(root.handlers) == count


class TestGetLogger:
    def test_returns_logger_with_name(self) -> None:
        logger = get_logger("test.mymodule")
        assert logger.name == "test.mymodule"
        assert isinstance(logger, logging.Logger)


class TestLogMarketEvent:
    def test_calls_info(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        log_market_event(mock_logger, "created", "TEST-MKT1")
        mock_logger.info.assert_called_once()


class TestLogCacheEvent:
    def test_calls_debug(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        log_cache_event(mock_logger, "get_market", "TEST-MKT1", hit=True)
        mock_logger.debug.assert_called_once()


class TestLogSettlementEvent:
    def test_calls_info(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        log_settlement_event(mock_logger, "TEST-MKT1", outcome=True)
        mock_logger.info.assert_called_once()


class TestLogReconciliationEvent:
    def test_calls_warning(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        log_reconciliation_event(mock_logger, "TEST-MKT1", drift_cents=50)
        mock_logger.warning.assert_called_once()

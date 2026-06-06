"""Tests for traderbot.logging_config — JSON format, rotation, per-module levels, correlation ID."""

from __future__ import annotations

import json
import logging
import logging.handlers
from unittest.mock import MagicMock

import pytest

from traderbot.logging_config import (
    configure_root_logger,
    correlation_id,
    log_cache_event,
    log_market_event,
    log_reconciliation_event,
    log_settlement_event,
    operation_id_var,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Reset the root logger and the module-level guard between tests."""
    import traderbot.logging_config as _mod

    # Reset the idempotency guard
    _mod._root_logger_configured = False

    root = logging.getLogger()
    # Preserve only handlers that were there before us (e.g. pytest's)
    original_handlers = list(root.handlers)
    original_level = root.level

    yield

    # Remove any handlers we added
    root.handlers = original_handlers
    root.setLevel(original_level)


@pytest.fixture()
def _clean_env(monkeypatch):
    """Ensure no TraderBot log env vars leak between tests."""
    for key in ("TRADERBOT_LOG_FORMAT", "TRADERBOT_LOG_FILE", "TRADERBOT_LOG_LEVELS"):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# configure_root_logger — baseline (backward compat)
# ---------------------------------------------------------------------------

class TestConfigureRootLoggerBaseline:
    def test_configures_stderr_handler(self, _clean_env) -> None:
        configure_root_logger()
        root = logging.getLogger()
        assert root.level == logging.INFO
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert any(isinstance(h, logging.StreamHandler) for h in stream_handlers)

    def test_idempotent(self, _clean_env) -> None:
        configure_root_logger()
        root = logging.getLogger()
        count = len(root.handlers)
        configure_root_logger()
        assert len(root.handlers) == count

    def test_default_format_is_pipe_delimited(self, _clean_env, caplog) -> None:
        configure_root_logger()
        with caplog.at_level(logging.INFO, logger="test_default_fmt"):
            logger = logging.getLogger("test_default_fmt")
            logger.info("hello world")
        lines = caplog.text.strip().splitlines()
        assert len(lines) >= 1
        # Pipe-delimited format uses " | " separators, NOT JSON
        assert " | " in lines[-1]
        with pytest.raises(json.JSONDecodeError):
            json.loads(lines[-1])


# ---------------------------------------------------------------------------
# TRADERBOT_LOG_FORMAT=json
# ---------------------------------------------------------------------------

class TestJsonFormat:
    def test_json_env_produces_valid_json(self, monkeypatch, _clean_env, caplog) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_FORMAT", "json")
        configure_root_logger()
        with caplog.at_level(logging.INFO, logger="test_json_fmt"):
            logger = logging.getLogger("test_json_fmt")
            logger.info("test message")
        lines = caplog.text.strip().splitlines()
        assert len(lines) >= 1
        obj = json.loads(lines[-1])
        assert "timestamp" in obj
        assert "level" in obj
        assert "name" in obj
        assert "message" in obj
        assert "operation_id" in obj
        assert obj["message"] == "test message"
        assert obj["name"] == "test_json_fmt"
        assert obj["level"] == "INFO"

    def test_json_operation_id_empty_by_default(self, monkeypatch, _clean_env, caplog) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_FORMAT", "json")
        configure_root_logger()
        with caplog.at_level(logging.INFO, logger="test_json_oid"):
            logging.getLogger("test_json_oid").info("no op id")
        lines = caplog.text.strip().splitlines()
        obj = json.loads(lines[-1])
        assert obj["operation_id"] == ""

    def test_json_timestamp_is_iso8601(self, monkeypatch, _clean_env, caplog) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_FORMAT", "json")
        configure_root_logger()
        with caplog.at_level(logging.INFO, logger="test_json_ts"):
            logging.getLogger("test_json_ts").info("ts check")
        lines = caplog.text.strip().splitlines()
        obj = json.loads(lines[-1])
        # ISO 8601 with timezone
        ts = obj["timestamp"]
        assert "+" in ts or ts.endswith("Z"), f"timestamp lacks timezone: {ts}"


# ---------------------------------------------------------------------------
# TRADERBOT_LOG_FILE (RotatingFileHandler)
# ---------------------------------------------------------------------------

class TestFileRotation:
    def test_file_handler_attached(self, monkeypatch, tmp_path, _clean_env) -> None:
        log_path = str(tmp_path / "test.log")
        monkeypatch.setenv("TRADERBOT_LOG_FILE", log_path)
        configure_root_logger()
        root = logging.getLogger()
        rfh_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rfh_handlers) == 1
        assert rfh_handlers[0].maxBytes == 10 * 1024 * 1024
        assert rfh_handlers[0].backupCount == 5

    def test_file_handler_writes_to_file(self, monkeypatch, tmp_path, _clean_env) -> None:
        log_path = str(tmp_path / "test.log")
        monkeypatch.setenv("TRADERBOT_LOG_FILE", log_path)
        configure_root_logger()
        logger = logging.getLogger("test_file_write")
        logger.info("file write test")
        # Flush the handler
        for h in logging.getLogger().handlers:
            if isinstance(h, logging.handlers.RotatingFileHandler):
                h.flush()
        with open(log_path) as f:
            content = f.read()
        assert "file write test" in content

    def test_no_file_handler_without_env(self, _clean_env) -> None:
        configure_root_logger()
        rfh_handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rfh_handlers) == 0


# ---------------------------------------------------------------------------
# TRADERBOT_LOG_LEVELS (per-module overrides)
# ---------------------------------------------------------------------------

class TestPerModuleLevels:
    def test_module_level_override(self, monkeypatch, _clean_env) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_LEVELS", "test_mod_a=DEBUG,test_mod_b=WARNING")
        configure_root_logger()
        logger_a = logging.getLogger("test_mod_a")
        logger_b = logging.getLogger("test_mod_b")
        assert logger_a.level == logging.DEBUG
        assert logger_b.level == logging.WARNING

    def test_empty_levels_env_is_noop(self, monkeypatch, _clean_env) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_LEVELS", "")
        configure_root_logger()  # should not raise
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_malformed_pair_is_skipped(self, monkeypatch, _clean_env) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_LEVELS", "INVALIDFORMAT,other=INFO")
        configure_root_logger()  # should not raise
        logger_other = logging.getLogger("other")
        assert logger_other.level == logging.INFO


# ---------------------------------------------------------------------------
# correlation_id context manager
# ---------------------------------------------------------------------------

class TestCorrelationId:
    def test_sets_and_resets_operation_id(self) -> None:
        assert operation_id_var.get("") == ""
        with correlation_id("op-123"):
            assert operation_id_var.get("") == "op-123"
        assert operation_id_var.get("") == ""

    def test_correlation_id_in_json_log(self, monkeypatch, _clean_env, caplog) -> None:
        monkeypatch.setenv("TRADERBOT_LOG_FORMAT", "json")
        configure_root_logger()
        with correlation_id("corr-abc"), caplog.at_level(logging.INFO, logger="test_corr_json"):
            logging.getLogger("test_corr_json").info("with corr id")
        lines = caplog.text.strip().splitlines()
        obj = json.loads(lines[-1])
        assert obj["operation_id"] == "corr-abc"

    def test_correlation_id_nests_properly(self) -> None:
        with correlation_id("outer"):
            assert operation_id_var.get("") == "outer"
            with correlation_id("inner"):
                assert operation_id_var.get("") == "inner"
            assert operation_id_var.get("") == "outer"
        assert operation_id_var.get("") == ""

    def test_correlation_id_restores_on_exception(self) -> None:
        assert operation_id_var.get("") == ""
        try:
            with correlation_id("fail-op"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert operation_id_var.get("") == ""


# ---------------------------------------------------------------------------
# Structured event helpers (unchanged)
# ---------------------------------------------------------------------------

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

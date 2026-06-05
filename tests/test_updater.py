"""Tests for traderbot.updater — auto-update checker."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from traderbot.updater import (
    apply_update,
    check_for_updates,
    fetch_latest_version,
    get_current_version,
)


class TestGetCurrentVersion:
    def test_reads_version_file(self) -> None:
        with patch.object(Path, "read_text", return_value="0.08.50\n"):
            result = get_current_version()
        assert result == "0.08.50"

    def test_strips_v_prefix(self) -> None:
        with patch.object(Path, "read_text", return_value="v0.09.00\n"):
            result = get_current_version()
        assert result == "0.09.00"

    def test_strips_whitespace(self) -> None:
        with patch.object(Path, "read_text", return_value="  0.08.50  \n"):
            result = get_current_version()
        assert result == "0.08.50"

    def test_fallback_to_importlib(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            with patch("importlib.metadata.version", return_value="0.10.00"):
                result = get_current_version()
        assert result == "0.10.00"

    def test_fallback_to_zero(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            with patch("importlib.metadata.version", side_effect=Exception("no package")):
                result = get_current_version()
        assert result == "0.0.0"


class TestFetchLatestVersion:
    def test_success_returns_version_and_url(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ref": "refs/tags/v0.09.00", "node_id": "abc", "url": "", "object": {"sha": "abc", "type": "commit", "url": ""}},
            {"ref": "refs/tags/v0.08.00", "node_id": "abc", "url": "", "object": {"sha": "abc", "type": "commit", "url": ""}},
        ]
        cache_file = MagicMock()
        cache_file.exists.return_value = False
        with patch("traderbot.updater.httpx.get", return_value=mock_response):
            with patch("traderbot.updater.Path.exists", return_value=False):
                result = fetch_latest_version()
        assert result is not None
        assert result[0] == "0.09.00"
        assert result[1] == ""

    def test_uses_cache_within_ttl(self) -> None:
        cache_data = json.dumps({"tag": "0.09.00", "url": "", "ts": time.time()})
        with patch("traderbot.updater.Path.exists", return_value=True):
            with patch.object(Path, "read_text", return_value=cache_data):
                result = fetch_latest_version(cache_ttl_seconds=3600)
        assert result is not None
        assert result[0] == "0.09.00"

    def test_ignores_expired_cache(self) -> None:
        cache_data = json.dumps({"tag": "0.08.00", "url": "", "ts": time.time() - 7200})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ref": "refs/tags/v0.09.00", "object": {"sha": "abc"}},
        ]
        with patch("traderbot.updater.Path.exists", return_value=True):
            with patch.object(Path, "read_text", return_value=cache_data):
                with patch("traderbot.updater.httpx.get", return_value=mock_response):
                    result = fetch_latest_version(cache_ttl_seconds=3600)
        assert result is not None
        assert result[0] == "0.09.00"

    def test_returns_none_on_404(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        with patch("traderbot.updater.httpx.get", return_value=mock_response):
            with patch("traderbot.updater.Path.exists", return_value=False):
                result = fetch_latest_version()
        assert result is None

    def test_403_with_stale_cache_returns_stale(self) -> None:
        cache_data = json.dumps({"tag": "0.08.00", "url": "", "ts": time.time() - 200})
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("403", request=MagicMock(), response=mock_response)
        with patch("traderbot.updater.Path.exists", return_value=True):
            with patch.object(Path, "read_text", return_value=cache_data):
                with patch("traderbot.updater.httpx.get", return_value=mock_response):
                    result = fetch_latest_version(cache_ttl_seconds=3600)
        assert result is not None
        assert result[0] == "0.08.00"


class TestCheckForUpdates:
    def test_no_update_when_current_latest_match(self) -> None:
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60, auto_apply=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg):
            with patch("traderbot.updater.get_current_version", return_value="0.08.50"):
                with patch("traderbot.updater.fetch_latest_version", return_value=("0.08.50", "")):
                    with patch("traderbot.updater.Path.exists", return_value=False):
                        result = check_for_updates()
        assert result is None

    def test_returns_update_when_latest_newer(self) -> None:
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60, auto_apply=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg):
            with patch("traderbot.updater.get_current_version", return_value="0.08.50"):
                with patch("traderbot.updater.fetch_latest_version", return_value=("0.09.00", "https://example.com")):
                    with patch("traderbot.updater.Path.exists", return_value=False):
                        result = check_for_updates(silent=True)
        assert result is not None
        assert result["current"] == "0.08.50"
        assert result["latest"] == "0.09.00"

    def test_force_bypasses_interval_marker(self) -> None:
        interval_ts = str(time.time() - 30)
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60, auto_apply=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg):
            with patch("traderbot.updater.get_current_version", return_value="0.08.50"):
                with patch("traderbot.updater.fetch_latest_version", return_value=("0.09.00", "")):
                    with patch.object(Path, "read_text", return_value=interval_ts):
                        with patch("traderbot.updater.Path.exists", return_value=True):
                            result = check_for_updates(force=True, silent=True)
        assert result is not None

    def test_interval_marker_blocks_early_recheck(self) -> None:
        interval_ts = str(time.time() - 120)
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg):
            with patch("traderbot.updater.get_current_version", return_value="0.08.50"):
                with patch("traderbot.updater.Path.exists", return_value=True):
                    with patch.object(Path, "read_text", return_value=interval_ts):
                        result = check_for_updates()
        assert result is None

    def test_disabled_config_returns_none(self) -> None:
        mock_cfg = MagicMock(enabled=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg):
            result = check_for_updates()
        assert result is None


class TestApplyUpdate:
    def test_success_returns_true(self) -> None:
        import subprocess
        mock_status = MagicMock()
        mock_status.returncode = 0
        with patch("subprocess.run", return_value=mock_status):
            with patch("traderbot.updater.Path.exists", return_value=True):
                result = apply_update(restart=False)
        assert result is True

    def test_missing_bootstrap_returns_false(self) -> None:
        with patch("traderbot.updater.Path.exists", return_value=False):
            result = apply_update(restart=False)
        assert result is False

    def test_failure_returns_false(self) -> None:
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            with patch("traderbot.updater.Path.exists", return_value=True):
                result = apply_update(restart=False)
        assert result is False
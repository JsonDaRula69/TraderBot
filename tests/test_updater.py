"""Tests for traderbot.updater — auto-update checker."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from traderbot.updater import (
    apply_update,
    check_for_updates,
    fetch_latest_version,
    get_current_version,
)


class TestGetCurrentVersion:
    def test_reads_version_file(self, tmp_path: Path) -> None:
        version_file = tmp_path / "VERSION"
        version_file.write_text("0.08.50\n")
        with patch("importlib.metadata.version", side_effect=Exception("no package")), patch("traderbot.paths.get_source_root", return_value=tmp_path):
            result = get_current_version()
        assert result == "0.08.50"

    def test_strips_v_prefix(self, tmp_path: Path) -> None:
        version_file = tmp_path / "VERSION"
        version_file.write_text("v0.09.00\n")
        with patch("importlib.metadata.version", side_effect=Exception("no package")), patch("traderbot.paths.get_source_root", return_value=tmp_path):
            result = get_current_version()
        assert result == "0.09.00"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        version_file = tmp_path / "VERSION"
        version_file.write_text("  0.08.50  \n")
        with patch("importlib.metadata.version", side_effect=Exception("no package")), patch("traderbot.paths.get_source_root", return_value=tmp_path):
            result = get_current_version()
        assert result == "0.08.50"

    def test_fallback_to_importlib(self) -> None:
        with patch("importlib.metadata.version", return_value="0.10.00"):
            result = get_current_version()
        assert result == "0.10.00"

    def test_fallback_to_zero(self) -> None:
        with patch("importlib.metadata.version", side_effect=Exception("no package")), patch("traderbot.paths.get_source_root", side_effect=FileNotFoundError):
            result = get_current_version()
        assert result == "0.0.0"


class TestFetchLatestVersion:
    def test_success_returns_version_and_url(self, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "ref": "refs/tags/v0.09.00",
                "node_id": "abc",
                "url": "",
                "object": {"sha": "abc", "type": "commit", "url": ""},
            },
            {
                "ref": "refs/tags/v0.08.00",
                "node_id": "abc",
                "url": "",
                "object": {"sha": "abc", "type": "commit", "url": ""},
            },
        ]
        with patch("traderbot.updater.httpx.get", return_value=mock_response), patch("traderbot.updater.CACHE_DIR", tmp_path):
            result = fetch_latest_version()
        assert result is not None
        assert result[0] == "0.09.00"
        assert result[1] == ""

    def test_uses_cache_within_ttl(self, tmp_path: Path) -> None:
        cache_data = json.dumps({"tag": "0.09.00", "url": "", "ts": time.time()})
        cache_file = tmp_path / ".update_cache.json"
        cache_file.write_text(cache_data)
        with patch("traderbot.updater.CACHE_DIR", tmp_path):
            result = fetch_latest_version(cache_ttl_seconds=3600)
        assert result is not None
        assert result[0] == "0.09.00"

    def test_ignores_expired_cache(self, tmp_path: Path) -> None:
        cache_data = json.dumps({"tag": "0.08.00", "url": "", "ts": time.time() - 7200})
        cache_file = tmp_path / ".update_cache.json"
        cache_file.write_text(cache_data)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ref": "refs/tags/v0.09.00", "object": {"sha": "abc"}},
        ]
        with patch("traderbot.updater.CACHE_DIR", tmp_path), patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = fetch_latest_version(cache_ttl_seconds=3600)
        assert result is not None
        assert result[0] == "0.09.00"

    def test_returns_none_on_404(self, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=mock_response
        )
        with patch("traderbot.updater.httpx.get", return_value=mock_response), patch("traderbot.updater.CACHE_DIR", tmp_path):
            result = fetch_latest_version()
        assert result is None

    def test_handles_corrupted_tags_gracefully(self, tmp_path: Path) -> None:
        """Tags with trailing garbage should be skipped, not crash."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"ref": "refs/tags/v0.15.07", "object": {"sha": "abc"}},
            {"ref": "refs/tags/v0.15.06", "object": {"sha": "abc"}},
            {"ref": "refs/tags/v0.10.156)", "object": {"sha": "abc"}},
            {"ref": "refs/tags/v0.10.155", "object": {"sha": "abc"}},
        ]
        with patch("traderbot.updater.httpx.get", return_value=mock_response), patch("traderbot.updater.CACHE_DIR", tmp_path):
            result = fetch_latest_version()
        assert result is not None
        assert result[0] == "0.15.07"

        # Fresh cache prevents API call — 403 fallback is unreachable.
        cache_data = json.dumps({"tag": "0.08.00", "url": "", "ts": time.time() - 200})
        cache_file = tmp_path / ".update_cache.json"
        cache_file.write_text(cache_data)
        with patch("traderbot.updater.CACHE_DIR", tmp_path):
            result = fetch_latest_version(cache_ttl_seconds=3600)
        assert result is not None
        assert result[0] == "0.08.00"


class TestCheckForUpdates:
    def test_no_update_when_current_latest_match(self, tmp_path: Path) -> None:
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60, auto_apply=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg), patch("traderbot.updater.get_current_version", return_value="0.08.50"), patch("traderbot.updater.fetch_latest_version", return_value=("0.08.50", "")), patch("traderbot.updater.CACHE_DIR", tmp_path):
            result = check_for_updates()
        assert result is None

    def test_returns_update_when_latest_newer(self, tmp_path: Path) -> None:
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60, auto_apply=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg), patch("traderbot.updater.get_current_version", return_value="0.08.50"), patch(
                    "traderbot.updater.fetch_latest_version",
                    return_value=("0.09.00", "https://example.com"),
                ), patch("traderbot.updater.CACHE_DIR", tmp_path):
                        result = check_for_updates(silent=True)
        assert result is not None
        assert result["current"] == "0.08.50"
        assert result["latest"] == "0.09.00"

    def test_force_bypasses_interval_marker(self, tmp_path: Path) -> None:
        interval_ts = str(time.time() - 30)
        (tmp_path / ".update_check_ts").write_text(interval_ts)
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60, auto_apply=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg), patch("traderbot.updater.get_current_version", return_value="0.08.50"), patch("traderbot.updater.fetch_latest_version", return_value=("0.09.00", "")), patch("traderbot.updater.CACHE_DIR", tmp_path):
                        result = check_for_updates(force=True, silent=True)
        assert result is not None

    def test_interval_marker_blocks_early_recheck(self, tmp_path: Path) -> None:
        interval_ts = str(time.time() - 120)
        (tmp_path / ".update_check_ts").write_text(interval_ts)
        mock_cfg = MagicMock(enabled=True, check_interval_minutes=60)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg), patch("traderbot.updater.CACHE_DIR", tmp_path):
                result = check_for_updates()
        assert result is None

    def test_disabled_config_returns_none(self) -> None:
        mock_cfg = MagicMock(enabled=False)
        with patch("traderbot.update_config.UpdateConfig.load", return_value=mock_cfg):
            result = check_for_updates()
        assert result is None


class TestApplyUpdate:
    def test_success_returns_true(self, tmp_path: Path) -> None:

        (tmp_path / "VERSION").write_text("0.14.81\n")
        bootstrap_dir = tmp_path / "install"
        bootstrap_dir.mkdir()
        (bootstrap_dir / "traderbot-update.py").write_text("# update script\n")
        mock_status = MagicMock()
        mock_status.returncode = 0
        with (
            patch("subprocess.run", return_value=mock_status),
            patch("traderbot.paths.get_source_root", return_value=tmp_path),
        ):
            result = apply_update(restart=False)
        assert result is True

    def test_missing_bootstrap_returns_false(self) -> None:
        import subprocess

        with (
            patch("traderbot.paths.get_source_root", side_effect=FileNotFoundError),
            patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "pip")),
        ):
            result = apply_update(restart=False)
        assert result is False

    def test_failure_returns_false(self, tmp_path: Path) -> None:
        import subprocess

        (tmp_path / "VERSION").write_text("0.14.81\n")
        bootstrap_dir = tmp_path / "install"
        bootstrap_dir.mkdir()
        (bootstrap_dir / "traderbot-update.py").write_text("# update script\n")
        with (
            patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")),
            patch("traderbot.paths.get_source_root", return_value=tmp_path),
        ):
            result = apply_update(restart=False)
        assert result is False

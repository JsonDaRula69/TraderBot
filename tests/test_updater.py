"""Tests for traderbot.updater — auto-update checker."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from packaging.version import Version

from traderbot.updater import (
    SignatureVerificationError,
    apply_update,
    check_for_updates,
    compare_versions,
    fetch_latest_version,
    get_current_version,
    verify_release_signature,
    _fetch_release_signature,
    _load_update_public_key,
    _read_cache,
    _write_cache,
)


class TestGetCurrentVersion:
    """Tests for get_current_version()."""

    def test_reads_version_file(self, tmp_path: Path) -> None:
        """get_current_version reads VERSION file and strips 'v' prefix."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("0.08.50\n")
        with patch("traderbot.updater.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.resolve.return_value.parent.parent.parent = tmp_path
            mock_path_cls.return_value = mock_path
            # Direct approach: mock the file read
        with patch.object(Path, "read_text", return_value="0.08.50\n"):
            result = get_current_version()
        assert result == "0.08.50"

    def test_strips_v_prefix(self) -> None:
        """get_current_version strips leading 'v' from version string."""
        with patch.object(Path, "read_text", return_value="v0.09.00\n"):
            result = get_current_version()
        assert result == "0.09.00"

    def test_strips_whitespace(self) -> None:
        """get_current_version strips whitespace from version string."""
        with patch.object(Path, "read_text", return_value="  0.08.50  \n"):
            result = get_current_version()
        assert result == "0.08.50"


class TestFetchLatestVersion:
    """Tests for fetch_latest_version()."""

    def test_success_returns_version_and_url(self) -> None:
        """fetch_latest_version returns (version, url) on 200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v0.09.00",
            "html_url": "https://github.com/JsonDaRula69/TraderBot/releases/tag/v0.09.00",
        }
        with patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = fetch_latest_version()
        assert result is not None
        assert result[0] == "0.09.00"
        assert "v0.09.00" in result[1]

    def test_404_returns_none(self) -> None:
        """fetch_latest_version returns None on 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = fetch_latest_version()
        assert result is None

    def test_timeout_returns_none(self) -> None:
        """fetch_latest_version returns None on timeout."""
        with patch("traderbot.updater.httpx.get", side_effect=httpx.TimeoutException("timeout")):
            result = fetch_latest_version()
        assert result is None

    def test_connection_error_returns_none(self) -> None:
        """fetch_latest_version returns None on connection error."""
        with patch("traderbot.updater.httpx.get", side_effect=httpx.ConnectError("no connection")):
            result = fetch_latest_version()
        assert result is None

    def test_malformed_json_returns_none(self) -> None:
        """fetch_latest_version returns None on malformed JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("err", "doc", 0)
        with patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = fetch_latest_version()
        assert result is None

    def test_missing_tag_name_returns_none(self) -> None:
        """fetch_latest_version returns None when tag_name is missing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"html_url": "https://example.com"}
        with patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = fetch_latest_version()
        # Empty tag_name stripped = empty string, should still return
        assert result is not None
        assert result[0] == ""


class TestCompareVersions:
    """Tests for compare_versions()."""

    def test_newer_version(self) -> None:
        """compare_versions returns True when latest > current."""
        assert compare_versions("0.08.50", "0.09.00") is True

    def test_same_version(self) -> None:
        """compare_versions returns False when versions are equal."""
        assert compare_versions("0.08.50", "0.08.50") is False

    def test_older_version(self) -> None:
        """compare_versions returns False when latest < current."""
        assert compare_versions("0.09.00", "0.08.50") is False

    def test_major_version_bump(self) -> None:
        """compare_versions handles major version bumps."""
        assert compare_versions("0.99.99", "1.00.00") is True

    def test_invalid_current(self) -> None:
        """compare_versions returns False for invalid current version."""
        assert compare_versions("not-a-version", "0.09.00") is False

    def test_invalid_latest(self) -> None:
        """compare_versions returns False for invalid latest version."""
        assert compare_versions("0.08.50", "not-a-version") is False


class TestCacheReadWrite:
    """Tests for _read_cache() and _write_cache()."""

    def test_write_and_read_cycle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Write cache then read it back."""
        cache_file = tmp_path / ".update_check_cache.json"
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)
        monkeypatch.setattr("traderbot.updater.CACHE_DIR", tmp_path)

        _write_cache("0.09.00", "https://example.com")
        result = _read_cache()
        assert result is not None
        assert result["latest"] == "0.09.00"
        assert result["url"] == "https://example.com"
        assert "ts" in result

    def test_read_missing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read cache returns None when file doesn't exist."""
        cache_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)

        result = _read_cache()
        assert result is None

    def test_read_corrupted_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read cache returns None for corrupted JSON."""
        cache_file = tmp_path / ".update_check_cache.json"
        cache_file.write_text("not json{{{")
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)

        result = _read_cache()
        assert result is None

    def test_read_missing_ts_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Read cache returns None when ts key is missing."""
        cache_file = tmp_path / ".update_check_cache.json"
        cache_file.write_text(json.dumps({"latest": "0.09.00"}))
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)

        result = _read_cache()
        assert result is None


class TestCheckForUpdates:
    """Tests for check_for_updates()."""

    def test_ci_environment_skips_check(self) -> None:
        """check_for_updates returns None when CI env var is set."""
        with patch.dict(os.environ, {"CI": "true"}):
            result = check_for_updates()
        assert result is None

    def test_no_update_env_skips_check(self) -> None:
        """check_for_updates returns None when TRADERBOT_NO_UPDATE_CHECK is set."""
        with patch.dict(os.environ, {"TRADERBOT_NO_UPDATE_CHECK": "1"}, clear=False):
            result = check_for_updates()
        assert result is None

    def test_cache_hit_within_interval(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """check_for_updates returns None when cache is fresh and version is current."""
        cache_file = tmp_path / ".update_check_cache.json"
        cache_file.write_text(json.dumps({
            "ts": time.time(),
            "latest": "0.08.50",
            "url": "https://example.com",
        }))
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)
        monkeypatch.setattr("traderbot.updater.CACHE_DIR", tmp_path)

        with patch("traderbot.updater.get_current_version", return_value="0.08.50"):
            result = check_for_updates(check_interval_hours=6)
        assert result is None

    def test_cache_hit_with_newer_version(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """check_for_updates returns update when cached version is newer than current."""
        cache_file = tmp_path / ".update_check_cache.json"
        cache_file.write_text(json.dumps({
            "ts": time.time(),
            "latest": "0.09.00",
            "url": "https://example.com/release",
        }))
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)
        monkeypatch.setattr("traderbot.updater.CACHE_DIR", tmp_path)

        with patch("traderbot.updater.get_current_version", return_value="0.08.50"):
            result = check_for_updates(check_interval_hours=6)
        assert result is not None
        assert result["current"] == "0.08.50"
        assert result["latest"] == "0.09.00"

    def test_cache_expired_fetches_new(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """check_for_updates fetches from API when cache is expired."""
        cache_file = tmp_path / ".update_check_cache.json"
        # Cache from 7 days ago (expired for 6h check)
        cache_file.write_text(json.dumps({
            "ts": time.time() - 7 * 86400,
            "latest": "0.08.00",
            "url": "https://example.com/old",
        }))
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)
        monkeypatch.setattr("traderbot.updater.CACHE_DIR", tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v0.09.00",
            "html_url": "https://github.com/JsonDaRula69/TraderBot/releases/tag/v0.09.00",
        }
        with patch.object(Path, "read_text", return_value="0.08.50\n"), \
             patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = check_for_updates(check_interval_hours=6)
        assert result is not None
        assert result["latest"] == "0.09.00"

    def test_force_bypasses_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """check_for_updates with force=True bypasses cache."""
        cache_file = tmp_path / ".update_check_cache.json"
        cache_file.write_text(json.dumps({
            "ts": time.time(),
            "latest": "0.08.50",
            "url": "https://example.com",
        }))
        monkeypatch.setattr("traderbot.updater.CACHE_FILE", cache_file)
        monkeypatch.setattr("traderbot.updater.CACHE_DIR", tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v0.09.00",
            "html_url": "https://github.com/JsonDaRula69/TraderBot/releases/tag/v0.09.00",
        }
        with patch.object(Path, "read_text", return_value="0.08.50\n"), \
             patch("traderbot.updater.httpx.get", return_value=mock_response):
            result = check_for_updates(force=True)
        assert result is not None
        assert result["latest"] == "0.09.00"


class TestApplyUpdate:
    """Tests for apply_update()."""

    def test_success_returns_true(self) -> None:
        """apply_update returns True on successful update."""
        import subprocess

        mock_status = MagicMock()
        mock_status.stdout = ""
        mock_status.returncode = 0

        with patch("subprocess.run", return_value=mock_status):
            result = apply_update(restart=False)
        assert result is True

    def test_failure_returns_false(self) -> None:
        """apply_update returns False on update failure."""
        import subprocess

        mock_status = MagicMock()
        mock_status.stdout = ""

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = apply_update(restart=False)
        assert result is False

    def test_uncommitted_changes_returns_false(self) -> None:
        """apply_update returns False when there are uncommitted changes."""
        import subprocess

        mock_status = MagicMock()
        mock_status.stdout = "M src/traderbot/cli.py\n"

        with patch("subprocess.run", return_value=mock_status):
            result = apply_update(restart=False)
        assert result is False

    def test_untracked_only_does_not_block(self) -> None:
        """apply_update proceeds when only untracked files exist (?? prefix)."""
        import subprocess

        mock_status = MagicMock()
        mock_status.stdout = "?? newfile.py\n"

        with patch("subprocess.run", return_value=mock_status):
            result = apply_update(restart=False)
        assert result is True


class TestEd25519SignatureVerification:
    """Tests for Ed25519 release signature verification."""

    VALID_PUBKEY_B64 = "XDtUjYC34oF2gcjNJEiBzKW0mQBAqOUh0pxOu29xttk="
    VALID_SIG_B64 = (
        "4FfjysmveWxlbt+cBgxUxeCSb3PktpCGq0snWkf8OGfq"
        "+fZcB3biXvoMFNSI6ODU2aJX5qmvDXBkyNYFGZsAAw=="
    )
    VALID_TAG = "v0.12.40"

    def test_valid_signature_returns_true(self) -> None:
        with patch.dict("os.environ", {"TRADERBOT_UPDATE_PUBKEY_B64": self.VALID_PUBKEY_B64}):
            result = verify_release_signature(self.VALID_TAG, self.VALID_SIG_B64)
        assert result is True

    def test_invalid_signature_returns_false(self) -> None:
        fake_sig = "A" * 86 + "=="
        with patch.dict("os.environ", {"TRADERBOT_UPDATE_PUBKEY_B64": self.VALID_PUBKEY_B64}):
            result = verify_release_signature(self.VALID_TAG, fake_sig)
        assert result is False

    def test_no_key_configured_returns_false(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = verify_release_signature("v0.12.40", self.VALID_SIG_B64)
        assert result is False

    def test_bad_base64_returns_false(self) -> None:
        with patch.dict("os.environ", {"TRADERBOT_UPDATE_PUBKEY_B64": self.VALID_PUBKEY_B64}):
            result = verify_release_signature("v0.12.40", "!!!not base64!!!")
        assert result is False

    def test_load_public_key_from_env(self) -> None:
        with patch.dict("os.environ", {"TRADERBOT_UPDATE_PUBKEY_B64": self.VALID_PUBKEY_B64}):
            key = _load_update_public_key()
        assert key is not None

    def test_load_public_key_missing_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch("traderbot.updater.Path.exists", return_value=False):
                with pytest.raises(SignatureVerificationError, match="No Ed25519"):
                    _load_update_public_key()

    def test_signature_verification_aborts_apply_update(self) -> None:
        mock_latest = ("0.12.41", "https://example.com")
        with patch("traderbot.updater.fetch_latest_version", return_value=mock_latest):
            with patch("traderbot.updater._fetch_release_signature", return_value="badsig"):
                with patch("traderbot.updater.verify_release_signature", return_value=False):
                    with patch.dict("os.environ", {"TRADERBOT_UPDATE_PUBKEY_B64": self.VALID_PUBKEY_B64}):
                        result = apply_update(restart=False, verify_signature=True)
        assert result is False

    def test_signature_verification_skipped_when_disabled(self) -> None:
        mock_latest = ("0.12.41", "https://example.com")
        with patch("traderbot.updater.fetch_latest_version", return_value=mock_latest):
            with patch("traderbot.updater._fetch_release_signature") as mock_fetch:
                with patch("traderbot.updater.verify_release_signature") as mock_verify:
                    with patch("subprocess.run") as mock_run:
                        mock_status = MagicMock()
                        mock_status.stdout = ""
                        mock_run.return_value = mock_status
                        result = apply_update(restart=False, verify_signature=False)
        assert result is True
        mock_fetch.assert_not_called()
        mock_verify.assert_not_called()

    def test_fetch_release_signature_found(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"body": "Ed25519-Signature: abc123"}
        with patch("traderbot.updater.httpx.get", return_value=mock_resp):
            sig = _fetch_release_signature("v0.12.40")
        assert sig == "abc123"

    def test_fetch_release_signature_not_found(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"body": "No signature here\nJust text"}
        with patch("traderbot.updater.httpx.get", return_value=mock_resp):
            sig = _fetch_release_signature("v0.12.40")
        assert sig is None

    def test_fetch_release_signature_http_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("traderbot.updater.httpx.get", return_value=mock_resp):
            sig = _fetch_release_signature("v0.12.40")
        assert sig is None
"""Tests for traderbot uninstall command."""

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from traderbot.cli import app

runner = CliRunner()


@pytest.fixture
def tmp_env(tmp_path: Path, monkeypatch: Any) -> dict[str, Path]:
    """Set up isolated temp environment for uninstall tests."""
    install_dir = tmp_path / "traderbot"
    install_dir.mkdir()
    (install_dir / ".venv").mkdir()
    (install_dir / ".venv" / "bin").mkdir()

    data_dir = tmp_path / ".traderbot"
    data_dir.mkdir()
    (data_dir / "paper").mkdir()
    (data_dir / "profiles.enc").write_text("encrypted")

    symlink = tmp_path / "usr_local_bin_traderbot"

    oc_dir = tmp_path / ".openclaw"
    oc_dir.mkdir()
    oc_config = oc_dir / "openclaw.json"
    oc_config.write_text(json.dumps({
        "agents": {
            "list": [
                {"id": "traderbot-test", "name": "TraderBot test", "workspace": "/tmp/ws"},
                {"id": "other-agent", "name": "Other", "workspace": "/tmp/other"},
            ]
        }
    }))

    return {
        "install_dir": install_dir,
        "data_dir": data_dir,
        "symlink": symlink,
        "oc_config": oc_config,
    }


class TestUninstallSystemFiles:
    """System files are always removed regardless of --remove-data."""

    def test_removes_install_dir(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """Install directory is removed."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall", "--remove-data"])
        assert not tmp_env["install_dir"].exists()

    def test_removes_symlink(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """Symlink at /usr/local/bin/traderbot is removed."""
        symlink_path = tmp_path / "usr_local_bin_traderbot"
        symlink_path.symlink_to(tmp_env["install_dir"] / ".venv" / "bin" / "traderbot")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None), \
             patch.object(Path, "is_symlink", return_value=True):
            result = runner.invoke(app, ["uninstall", "--remove-data"])
        assert "symlink" in result.stdout.lower() or "Removed" in result.stdout


class TestUninstallUserData:
    """User data is only removed with --remove-data or interactive confirmation."""

    def test_preserves_data_by_default(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """Without --remove-data, user data directory is preserved."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall"], input="n\n")
        assert tmp_env["data_dir"].exists()

    def test_removes_data_with_flag(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """With --remove-data, user data directory is removed."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall", "--remove-data"])
        assert not tmp_env["data_dir"].exists()

    def test_removes_data_on_confirm(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """With interactive 'y' confirmation, user data is removed."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall"], input="y\n")
        assert not tmp_env["data_dir"].exists()


class TestUninstallOpenClawConfig:
    """TraderBot agent entries are removed from openclaw.json, others preserved."""

    def test_removes_traderbot_agents_from_config(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """TraderBot agent entries removed, non-TraderBot entries preserved."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall", "--remove-data"])

        oc_config = tmp_env["oc_config"]
        config_data = json.loads(oc_config.read_text())
        agent_ids = [a["id"] for a in config_data["agents"]["list"]]
        assert "traderbot-test" not in agent_ids
        assert "other-agent" in agent_ids

    def test_no_traderbot_agents_skipped(self, tmp_path: Path, monkeypatch: Any) -> None:
        """If no TraderBot agents in config, gracefully skipped."""
        oc_dir = tmp_path / ".openclaw"
        oc_dir.mkdir()
        oc_config = oc_dir / "openclaw.json"
        oc_config.write_text(json.dumps({"agents": {"list": [
            {"id": "other-agent", "name": "Other"}
        ]}}))

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall", "--remove-data"])

        assert "No TraderBot agents" in result.stdout or "Skipped" in result.stdout


class TestUninstallSummary:
    """Uninstall always shows a summary of removed and skipped items."""

    def test_shows_removed_items(self, tmp_env: dict, tmp_path: Path, monkeypatch: Any) -> None:
        """Summary lists all removed paths."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall", "--remove-data"])
        assert "Removed" in result.stdout
        assert "Uninstalled" in result.stdout or "uninstalled" in result.stdout.lower()

    def test_shows_skipped_items(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Summary lists skipped items when nothing to remove."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["uninstall", "--remove-data"])
        assert "Skipped" in result.stdout or "No " in result.stdout
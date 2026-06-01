"""Tests for traderbot.update_config — auto-update configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from traderbot.update_config import UpdateConfig


class TestUpdateConfigDefaults:
    """Tests for default configuration values."""

    def test_default_enabled_is_true(self) -> None:
        config = UpdateConfig()
        assert config.enabled is True

    def test_default_check_on_startup_is_true(self) -> None:
        config = UpdateConfig()
        assert config.check_on_startup is True

    def test_default_check_interval_is_30(self) -> None:
        config = UpdateConfig()
        assert config.check_interval_minutes == 30

    def test_default_auto_apply_is_false(self) -> None:
        config = UpdateConfig()
        assert config.auto_apply is False

    def test_default_include_prerelease_is_false(self) -> None:
        config = UpdateConfig()
        assert config.include_prerelease is False


class TestUpdateConfigValidation:
    """Tests for field validation constraints."""

    def test_check_interval_minimum_1(self) -> None:
        with pytest.raises(ValidationError):
            UpdateConfig(check_interval_minutes=0)

    def test_check_interval_maximum_10080(self) -> None:
        with pytest.raises(ValidationError):
            UpdateConfig(check_interval_minutes=10081)

    def test_check_interval_boundary_1(self) -> None:
        config = UpdateConfig(check_interval_minutes=1)
        assert config.check_interval_minutes == 1

    def test_check_interval_boundary_10080(self) -> None:
        config = UpdateConfig(check_interval_minutes=10080)
        assert config.check_interval_minutes == 10080

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            UpdateConfig(enabled=True, unknown_field="value")


class TestUpdateConfigLoad:
    """Tests for loading config from disk."""

    def test_load_returns_defaults_when_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Load returns defaults when config file doesn't exist."""
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", tmp_path / "nonexistent.json")
        config = UpdateConfig.load()
        assert config.enabled is True
        assert config.check_interval_minutes == 30

    def test_load_reads_valid_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Load reads and validates config from disk."""
        config_file = tmp_path / "update_config.json"
        config_file.write_text(json.dumps({
            "enabled": False,
            "check_on_startup": False,
            "check_interval_minutes": 1440,
            "auto_apply": True,
            "include_prerelease": True,
        }))
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", config_file)
        config = UpdateConfig.load()
        assert config.enabled is False
        assert config.check_on_startup is False
        assert config.check_interval_minutes == 1440
        assert config.auto_apply is True
        assert config.include_prerelease is True

    def test_load_returns_defaults_for_corrupted_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Load returns defaults when config file contains invalid JSON."""
        config_file = tmp_path / "update_config.json"
        config_file.write_text("not json{{{")
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", config_file)
        config = UpdateConfig.load()
        assert config.enabled is True
        assert config.check_interval_minutes == 30

    def test_load_returns_defaults_for_invalid_values(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Load returns defaults when config file has invalid field values."""
        config_file = tmp_path / "update_config.json"
        config_file.write_text(json.dumps({"check_interval_minutes": 99999}))
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", config_file)
        config = UpdateConfig.load()
        assert config.check_interval_minutes == 30


class TestUpdateConfigSave:
    """Tests for persisting config to disk."""

    def test_save_creates_parent_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Save creates parent directory if it doesn't exist."""
        config_path = tmp_path / "subdir" / "update_config.json"
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", config_path)
        config = UpdateConfig(enabled=False)
        config.save()
        assert config_path.exists()

    def test_save_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Save then load produces identical config."""
        config_path = tmp_path / "update_config.json"
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", config_path)
        original = UpdateConfig(
            enabled=False,
            check_on_startup=False,
            check_interval_minutes=1440,
            auto_apply=True,
            include_prerelease=True,
        )
        original.save()
        loaded = UpdateConfig.load()
        assert loaded.enabled is False
        assert loaded.check_on_startup is False
        assert loaded.check_interval_minutes == 1440
        assert loaded.auto_apply is True
        assert loaded.include_prerelease is True

    def test_save_produces_valid_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Save produces parseable JSON."""
        config_path = tmp_path / "update_config.json"
        monkeypatch.setattr("traderbot.update_config.CONFIG_PATH", config_path)
        config = UpdateConfig()
        config.save()
        data = json.loads(config_path.read_text())
        assert "enabled" in data
        assert "check_interval_minutes" in data
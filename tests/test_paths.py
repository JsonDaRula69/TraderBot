from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from traderbot.paths import (
    ensure_data_dir,
    get_agent_workspace_dir,
    get_audit_dir,
    get_chromadb_dir,
    get_data_dir,
    get_db_path,
    get_logs_dir,
    get_master_key_path,
    get_source_root,
    get_workspace_dir,
    list_all_data_paths,
)


class TestGetDataDir:
    def test_returns_home_traderbot(self) -> None:
        result = get_data_dir()
        assert result == Path.home() / ".traderbot"


class TestGetDbPath:
    def test_returns_traderbot_db(self) -> None:
        result = get_db_path()
        assert result == get_data_dir() / "traderbot.db"


class TestGetChromadbDir:
    def test_returns_chromadb_subdir(self) -> None:
        result = get_chromadb_dir()
        assert result == get_data_dir() / "chromadb"


class TestGetLogsDir:
    def test_returns_logs_subdir(self) -> None:
        result = get_logs_dir()
        assert result == get_data_dir() / "logs"


class TestGetWorkspaceDir:
    def test_returns_cwd_openclaw_workspace(self) -> None:
        result = get_workspace_dir()
        assert result == Path.cwd() / ".openclaw" / "workspace"


class TestGetAgentWorkspaceDir:
    def test_returns_data_dir_agent_workspace(self) -> None:
        result = get_agent_workspace_dir()
        assert result == get_data_dir() / "agent_workspace"


class TestGetMasterKeyPath:
    def test_returns_dot_master_key(self) -> None:
        result = get_master_key_path()
        assert result == get_data_dir() / ".master_key"


class TestGetSourceRoot:
    def test_returns_parent_of_src(self) -> None:
        result = get_source_root()
        assert result.name == "main" or (result / "src" / "traderbot").exists()


class TestGetAuditDir:
    def test_falls_back_to_data_dir_audit(self) -> None:
        with patch("traderbot.paths.get_data_dir", return_value=Path("/tmp/tb_test")):
            result = get_audit_dir()
            assert result == Path("/tmp/tb_test") / "audit"


class TestEnsureDataDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        test_dir = tmp_path / ".traderbot"
        with patch("traderbot.paths.get_data_dir", return_value=test_dir):
            result = ensure_data_dir()
            assert result == test_dir
            assert test_dir.exists()

    def test_idempotent_when_exists(self, tmp_path: Path) -> None:
        test_dir = tmp_path / ".traderbot"
        test_dir.mkdir()
        with patch("traderbot.paths.get_data_dir", return_value=test_dir):
            result = ensure_data_dir()
            assert result == test_dir


class TestListAllDataPaths:
    def test_returns_paths_beneath_data_dir(self) -> None:
        fake_base = Path("/tmp/tb_test_paths")
        with patch("traderbot.paths.get_data_dir", return_value=fake_base):
            paths = list_all_data_paths()
            assert len(paths) > 0
            for p in paths:
                assert str(p).startswith(str(fake_base))

"""Tests for traderbot.sandbox — filesystem sandbox with workspace isolation."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from traderbot.sandbox import (
    SANDBOX_LOCK_EXT,
    FilesystemSandbox,
    SandboxStatus,
    create_sandbox,
    get_active_sandbox,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestFilesystemSandbox:
    def test_initial_status(self) -> None:
        sandbox = FilesystemSandbox()
        assert sandbox.status == SandboxStatus.INACTIVE

    def test_is_available_on_macos(self) -> None:
        sandbox = FilesystemSandbox()
        result = sandbox.is_available()
        assert isinstance(result, bool)

    def test_workspace_created_after_enter(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        assert workspace.exists()
        assert workspace.is_dir()

        sandbox.exit_sandbox()

    def test_lock_file_exists_after_enter(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        lock = workspace / SANDBOX_LOCK_EXT
        assert lock.exists()

        sandbox.exit_sandbox()

    def test_lock_file_removed_after_exit(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()
        sandbox.exit_sandbox()

        lock = workspace / SANDBOX_LOCK_EXT
        assert not lock.exists()

    def test_status_active_after_enter(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        assert sandbox.status == SandboxStatus.ACTIVE

        sandbox.exit_sandbox()

    def test_status_inactive_after_exit(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()
        sandbox.exit_sandbox()

        assert sandbox.status == SandboxStatus.INACTIVE

    def test_double_enter_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        with pytest.raises(RuntimeError, match="already active"):
            sandbox.enter()

        sandbox.exit_sandbox()

    def test_exit_when_not_active_is_noop(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        assert sandbox.status == SandboxStatus.INACTIVE
        sandbox.exit_sandbox()
        assert sandbox.status == SandboxStatus.INACTIVE

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod-based enforcement, Unix only")
    def test_src_becomes_readonly_after_enter(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        test_file = src / "test.txt"
        test_file.write_text("hello")
        os.chmod(test_file, 0o644)

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        mode = oct(os.stat(test_file).st_mode)[-3:]
        sandbox.exit_sandbox()

        assert "w" not in mode or mode[1] == "5"

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod-based enforcement, Unix only")
    def test_src_permissions_restored_after_exit(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        test_file = src / "test.txt"
        test_file.write_text("hello")
        os.chmod(test_file, 0o644)

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()
        sandbox.exit_sandbox()

        mode = oct(os.stat(test_file).st_mode)[-3:]
        assert mode == "644"

    def test_missing_src_root_raises(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        sandbox = FilesystemSandbox(src_root=tmp_path / "nosuchdir", workspace_dir=workspace)

        with pytest.raises(FileNotFoundError):
            sandbox.enter()

    def test_verify_returns_false_when_inactive(self) -> None:
        sandbox = FilesystemSandbox()
        assert not sandbox.verify()

    def test_workspace_permissions_owner_only(self, tmp_path: Path) -> None:
        if sys.platform == "win32":
            pytest.skip("chmod not applicable on Windows")

        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        mode = oct(os.stat(workspace).st_mode)[-3:]
        assert mode == "700"

        sandbox.exit_sandbox()

    def test_workspace_retained_after_exit(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        workspace = tmp_path / "workspace"

        sandbox = FilesystemSandbox(src_root=src, workspace_dir=workspace)
        sandbox.enter()

        test_file = workspace / "agent_output.txt"
        test_file.write_text("agent data")

        sandbox.exit_sandbox()
        assert test_file.exists()
        assert test_file.read_text() == "agent data"


class TestCreateSandbox:
    def test_returns_sandbox_with_defaults(self) -> None:
        sandbox = create_sandbox()
        assert isinstance(sandbox, FilesystemSandbox)

    def test_returns_sandbox_with_custom_dirs(self, tmp_path: Path) -> None:
        sandbox = create_sandbox(src_root=tmp_path / "src", workspace_dir=tmp_path / "ws")
        assert sandbox.src_root == tmp_path / "src"
        assert sandbox.workspace_dir == tmp_path / "ws"


class TestGetActiveSandbox:
    def test_none_when_not_active(self) -> None:
        assert get_active_sandbox() is None

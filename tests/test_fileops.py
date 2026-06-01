from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from traderbot.fileops import (
    LOCK_EXCLUSIVE,
    LOCK_NON_BLOCKING,
    LOCK_SHARED,
    lock_file,
    set_dir_owner_only,
    set_file_owner_only,
    unlock_file,
)


class TestLockConstants:
    def test_lock_flags_exist(self) -> None:
        assert LOCK_SHARED is not None
        assert LOCK_EXCLUSIVE is not None
        assert LOCK_NON_BLOCKING is not None


class TestLockFile:
    def test_lock_and_unlock(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test")
            f.flush()
            lock_file(f, LOCK_SHARED)
            unlock_file(f)


class TestSetFileOwnerOnly:
    def test_calls_chmod_on_unix(self) -> None:
        if sys.platform == "win32":
            pytest.skip("No chmod on Windows")

        fake_path = MagicMock()
        set_file_owner_only(fake_path)
        fake_path.chmod.assert_called_once_with(0o600)


class TestSetDirOwnerOnly:
    def test_calls_chmod_on_unix(self) -> None:
        if sys.platform == "win32":
            pytest.skip("No chmod on Windows")

        fake_path = MagicMock()
        set_dir_owner_only(fake_path)
        fake_path.chmod.assert_called_once_with(0o700)

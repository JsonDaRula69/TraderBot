"""Characterization coverage for the pre-Phase-4 CLI and path defaults."""

from pathlib import Path
from unittest import mock

import pytest

from traderbot.cli import main
from traderbot.paths import get_data_dir


def test_daemon_parser_preserves_existing_defaults() -> None:
    # Given: the existing daemon subcommand parser
    with mock.patch("traderbot.cli.daemon_main") as daemon_main:
        # When: daemon is parsed without optional arguments
        exit_code = main(["daemon"])

    # Then: the established daemon defaults are forwarded unchanged
    assert exit_code == 0
    daemon_main.assert_called_once_with(
        ["--host", "127.0.0.1", "--port", "8765", "--environment", "production"]
    )


def test_data_dir_defaults_to_home_traderbot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: no data-directory override and an isolated home directory
    monkeypatch.delenv("TRADERBOT_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    # When: the data directory is resolved
    data_dir = get_data_dir()

    # Then: the historical ~/.traderbot default is preserved
    assert data_dir == tmp_path / ".traderbot"

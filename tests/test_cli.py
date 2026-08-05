"""Tests for the traderbot service CLI (DD-022)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from traderbot.cli import main
from traderbot.services.deploy import deploy_service, service_status


def test_cli_status_reports_not_installed() -> None:
    code = main(["service", "status"])
    assert code == 0


def test_cli_unknown_command_errors() -> None:
    try:
        main(["service", "frobnicate"])
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_service_status_no_manager() -> None:
    with mock.patch("traderbot.services.deploy.detect_service_manager", return_value="none"):
        assert service_status() == "not installed"


def test_deploy_writes_template_to_destination(tmp_path: Path) -> None:
    with (
        mock.patch("traderbot.services.deploy.detect_service_manager", return_value="systemd"),
        mock.patch(
            "traderbot.services.deploy._destination",
            return_value=tmp_path / "traderbot.service",
        ),
    ):
        destination = deploy_service(profile_token="test-token")
        rendered = destination.read_text()
        assert "[Service]" in rendered
        assert "ExecStart" in rendered
        assert "test-token" in rendered

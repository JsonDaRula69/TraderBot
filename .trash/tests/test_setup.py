"""Tests for `traderbot setup` interactive wizard."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tests.conftest import strip_ansi
from traderbot.cli import app

runner = CliRunner()


def _make_auth_mock(*, has_kalshi: bool = False, has_optional: dict[str, bool] | None = None) -> MagicMock:
    """Create a mock AuthManager that returns configured/not."""
    if has_optional is None:
        has_optional = {}

    mock_mgr = MagicMock()

    def get_credential(service: str, key: str):
        from pydantic import SecretStr

        from traderbot.auth import CredentialResult

        if service == "kalshi" and key == "api_key":
            if has_kalshi:
                return CredentialResult(service="kalshi", key="api_key", value=SecretStr("dummy-key"), source="keyring")
            return None
        if service in has_optional and has_optional.get(service, False):
            return CredentialResult(service=service, key="api_key", value=SecretStr("dummy-key"), source="keyring")
        return None

    mock_mgr.get_credential = get_credential
    mock_mgr.set_credential = MagicMock(return_value="env")
    return mock_mgr


def _make_profile_registry_mock(existing_profiles: list[str] | None = None) -> MagicMock:
    """Create a mock ProfileRegistry."""
    if existing_profiles is None:
        existing_profiles = []
    mock_reg = MagicMock()
    mock_reg.list_profiles.return_value = existing_profiles
    mock_reg.create_profile = MagicMock()
    mock_reg.profile_exists = MagicMock(return_value=bool(existing_profiles))
    return mock_reg


# Shared patch tuples for reuse
def _all_good_patches():
    return (
        patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))),
        patch("traderbot.auth.AuthManager", return_value=_make_auth_mock(has_kalshi=True)),
        patch("traderbot.profiles.registry.ProfileRegistry", return_value=_make_profile_registry_mock(["default"])),
        patch("traderbot.master_password.is_setup", return_value=True),
    )


def _nothing_configured_patches():
    return (
        patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))),
        patch("traderbot.auth.AuthManager", return_value=_make_auth_mock(has_kalshi=False)),
        patch("traderbot.profiles.registry.ProfileRegistry", return_value=_make_profile_registry_mock([])),
        patch("traderbot.master_password.is_setup", return_value=False),
    )


class TestSetupHelp:
    """Help output tests."""

    def test_help_succeeds(self):
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output.lower()
        assert "--dry-run" in strip_ansi(result.output)
        assert "--non-interactive" in strip_ansi(result.output)
        assert "--json" in strip_ansi(result.output)
        assert "--no-creds" in strip_ansi(result.output)

    def test_help_shows_steps(self):
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        cleaned = strip_ansi(result.output)
        assert "Python version" in cleaned or "python" in cleaned.lower()


class TestSetupStepPythonCheck:
    """Python version step tests."""

    def test_python_version_ok(self):
        """Python version check passes on supported Python."""
        with patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))):
            result = runner.invoke(app, ["setup", "--dry-run"])
            assert result.exit_code == 0
            assert "compatible" in strip_ansi(result.output)

    def test_python_version_error(self):
        """Python version check fails on unsupported Python."""
        with patch("traderbot.cli.setup._python_version_ok", return_value=(False, "3.11.0", (3, 11))):
            result = runner.invoke(app, ["setup", "--dry-run"])
            assert result.exit_code == 1
            assert "required" in strip_ansi(result.output).lower()

    def test_python_version_json_error(self):
        """Failed check outputs JSON with error."""
        with patch("traderbot.cli.setup._python_version_ok", return_value=(False, "3.11.0", (3, 11))):
            result = runner.invoke(app, ["setup", "--dry-run", "--json"])
            assert result.exit_code == 1
            data = json.loads(strip_ansi(result.output))
            assert "error" in data
            assert "3.11" in data["error"]


class TestSetupDryRun:
    """Dry-run tests — validate without writing."""

    def test_dry_run_succeeds_with_existing_kalshi(self):
        """Dry run passes when credentials and profiles exist."""
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--dry-run"])
            assert result.exit_code == 0
            cleaned = strip_ansi(result.output)
            assert "Would create data directory" in cleaned
            assert "Would initialize database" in cleaned
            assert "already configured" in cleaned.lower()

    def test_dry_run_json_output(self):
        """Dry run outputs structured JSON."""
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--dry-run", "--json"])
            assert result.exit_code == 0
            data = json.loads(strip_ansi(result.output))
            assert "results" in data
            steps = [r["step"] for r in data["results"]]
            assert "python_version" in steps
            assert "data_dir" in steps
            assert "db_init" in steps
            assert "kalshi_credentials" in steps
            assert "optional_services" in steps
            assert "master_password" in steps
            assert "profile_creation" in steps


class TestSetupNonInteractive:
    """Non-interactive mode — skips all prompts."""

    def test_non_interactive_skips_credentials(self):
        """Non-interactive shows warnings for missing creds."""
        patches = _nothing_configured_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive"])
            assert result.exit_code == 0
            cleaned = strip_ansi(result.output)
            assert "not configured" in cleaned.lower()

    def test_non_interactive_json(self):
        """Non-interactive JSON output reports all warnings."""
        patches = _nothing_configured_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive", "--json"])
            assert result.exit_code == 0
            data = json.loads(strip_ansi(result.output))
            warnings = [r for r in data["results"] if r["status"] == "warning"]
            assert len(warnings) >= 3  # kalshi, master_password, profile_creation


class TestSetupStepDataDir:
    """Data directory step tests."""

    def test_dry_run_reports_path(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--dry-run"])
            assert result.exit_code == 0
            assert ".traderbot" in strip_ansi(result.output)

    def test_creates_dir_on_real_run(self):
        td = tempfile.TemporaryDirectory()
        tmpdir = td
        try:
            with (
                td,
                patch("traderbot.paths.get_data_dir", return_value=Path(tmpdir.name) / ".traderbot"),
                patch("traderbot.db.DB_PATH", Path(tmpdir.name) / ".traderbot" / "traderbot.db"),
                patch("traderbot.auth.AuthManager", return_value=_make_auth_mock(has_kalshi=True)),
                patch("traderbot.profiles.registry.ProfileRegistry", return_value=_make_profile_registry_mock(["default"])),
                patch("traderbot.master_password.is_setup", return_value=True),
            ):
                result = runner.invoke(app, ["setup", "--non-interactive"])
                assert result.exit_code == 0
                data_dir = Path(tmpdir.name) / ".traderbot"
                assert data_dir.exists()
        finally:
            td.cleanup()


class TestSetupStepDbInit:
    """Database initialization tests."""

    def test_dry_run_reports_path(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--dry-run"])
            assert result.exit_code == 0
            assert "Would initialize database" in strip_ansi(result.output)

    def test_db_init_handles_error(self):
        with (
            patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))),
            patch("traderbot.auth.AuthManager", return_value=_make_auth_mock(has_kalshi=True)),
            patch("traderbot.profiles.registry.ProfileRegistry", return_value=_make_profile_registry_mock(["default"])),
            patch("traderbot.master_password.is_setup", return_value=True),
            patch("traderbot.db.get_connection", side_effect=RuntimeError("disk full")),
        ):
            result = runner.invoke(app, ["setup"])
            assert result.exit_code == 1  # error step count > 0
            assert "disk full" in strip_ansi(result.output)


class TestSetupStepKalshiAlreadyConfigured:
    """Kalshi credentials — already configured detection."""

    def test_skips_when_configured(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive"])
            assert result.exit_code == 0
            assert "already configured" in strip_ansi(result.output).lower()

    def test_warns_when_not_configured_non_interactive(self):
        patches = _nothing_configured_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive"])
            assert result.exit_code == 0
            assert "not configured" in strip_ansi(result.output).lower()

    def test_no_creds_flag_skips_kalshi(self):
        patches = _nothing_configured_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--no-creds", "--non-interactive"])
            assert result.exit_code == 0
            cleaned = strip_ansi(result.output)
            assert "--no-creds" in cleaned


class TestSetupCreatesProfile:
    """Profile creation step tests."""

    def test_skip_when_profiles_exist(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive"])
            assert result.exit_code == 0
            cleaned = strip_ansi(result.output)
            assert "already exist" in cleaned.lower() or "default" in cleaned.lower()

    def test_creates_default_profile(self):
        mock_registry = _make_profile_registry_mock([])
        with (
            patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))),
            patch("traderbot.auth.AuthManager", return_value=_make_auth_mock(has_kalshi=True)),
            patch("traderbot.master_password.is_setup", return_value=True),
            patch("traderbot.profiles.registry.ProfileRegistry", return_value=mock_registry),
            patch("typer.confirm", return_value=True),
            patch("sys.stdin.read", return_value="-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----"),
        ):
            result = runner.invoke(app, ["setup", "--no-creds"])
            assert result.exit_code == 0
            mock_registry.create_profile.assert_called_once()
            call_args = mock_registry.create_profile.call_args[0][0]
            assert call_args.name == "default"
            assert call_args.mode == "paper"

    def test_skip_when_user_declines(self):
        with (
            patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))),
            patch("traderbot.auth.AuthManager", return_value=_make_auth_mock(has_kalshi=True)),
            patch("traderbot.master_password.is_setup", return_value=True),
            patch("traderbot.profiles.registry.ProfileRegistry", return_value=_make_profile_registry_mock([])),
            patch("typer.confirm", return_value=False),
        ):
            result = runner.invoke(app, ["setup"])
            assert result.exit_code == 0
            assert "Skipped" in strip_ansi(result.output) or "skipped" in strip_ansi(result.output)


class TestSetupMasterPassword:
    """Master password step tests."""

    def test_skip_when_already_configured(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive"])
            assert result.exit_code == 0
            assert "already configured" in strip_ansi(result.output).lower()

    def test_warn_when_not_configured_non_interactive(self):
        patches = _nothing_configured_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--non-interactive"])
            assert result.exit_code == 0
            assert "not configured" in strip_ansi(result.output).lower()


class TestSetupSummary:
    """Summary output tests."""

    def test_dry_run_summary_json(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["setup", "--dry-run", "--json"])
            assert result.exit_code == 0
            data = json.loads(strip_ansi(result.output))
            assert "results" in data
            assert len(data["results"]) == 7  # 7 steps


class TestBootstrapFullDelegation:
    """Test that `traderbot bootstrap --full` delegates to setup wizard."""

    def test_bootstrap_full_runs_setup(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["bootstrap", "--full", "--dry-run"])
            assert result.exit_code == 0
            cleaned = strip_ansi(result.output)
            assert "Step 1" in cleaned or "Python" in cleaned

    def test_bootstrap_full_json(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            result = runner.invoke(app, ["bootstrap", "--full", "--dry-run", "--json"])
            assert result.exit_code == 0
            data = json.loads(strip_ansi(result.output))
            assert "results" in data

    def test_bootstrap_without_full_is_unchanged(self):
        """Legacy bootstrap should still work without --full."""
        with patch("traderbot.cli.setup._python_version_ok", return_value=(True, "3.12.5", (3, 12))):
            result = runner.invoke(app, ["bootstrap", "--dry-run"])
            assert result.exit_code == 0
            cleaned = strip_ansi(result.output)
            assert "Data directory" in cleaned or "Bootstrap" in cleaned


class TestSetupIdempotent:
    """Setup should be safe to run multiple times."""

    def test_second_run_also_passes(self):
        patches = _all_good_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            r1 = runner.invoke(app, ["setup", "--non-interactive"])
            r2 = runner.invoke(app, ["setup", "--non-interactive"])
            assert r1.exit_code == 0
            assert r2.exit_code == 0

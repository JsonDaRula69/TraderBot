"""Tests for systemd service template validation."""

import re
from pathlib import Path

import pytest


@pytest.fixture
def template_path() -> Path:
    """Path to the systemd service template."""
    return Path(__file__).parent.parent.parent / "install" / "services" / "traderbot-agent@.service"


@pytest.fixture
def template_content(template_path: Path) -> str:
    """Read the systemd service template content."""
    return template_path.read_text()


def test_template_file_exists(template_path: Path) -> None:
    """Template file exists and is readable."""
    assert template_path.exists(), f"Template file not found: {template_path}"
    assert template_path.is_file(), f"Template path is not a file: {template_path}"
    assert template_path.stat().st_size > 0, "Template file is empty"


def test_template_has_required_sections(template_content: str) -> None:
    """Template contains all required systemd sections."""
    required_sections = ["[Unit]", "[Service]", "[Install]"]
    for section in required_sections:
        assert section in template_content, f"Missing required section: {section}"


def test_template_unit_section(template_content: str) -> None:
    """[Unit] section has required directives."""
    # Extract [Unit] section
    unit_match = re.search(r"\[Unit\](.*?)(?=\[Service\])", template_content, re.DOTALL)
    assert unit_match, "[Unit] section not found or malformed"
    unit_section = unit_match.group(1)

    # Check required directives
    assert re.search(r"^Description=.*%i", unit_section, re.MULTILINE), "Description must use %i for agent ID"
    assert "After=network.target" in unit_section, "Must wait for network.target"
    assert "Wants=network-online.target" in unit_section, "Should want network-online.target"


def test_template_service_section(template_content: str) -> None:
    """[Service] section has required directives."""
    service_match = re.search(r"\[Service\](.*?)(?=\[Install\])", template_content, re.DOTALL)
    assert service_match, "[Service] section not found or malformed"
    service_section = service_match.group(1)

    assert re.search(r"^Type=oneshot", service_section, re.MULTILINE), "Service type must be oneshot (scheduling via OpenClaw Gateway)"
    assert re.search(r"^User=", service_section, re.MULTILINE), "User directive required"
    assert re.search(r"^WorkingDirectory=", service_section, re.MULTILINE), "WorkingDirectory required"
    assert re.search(r"^ExecStart=.*traderbot.*heartbeat", service_section, re.MULTILINE), "ExecStart must run traderbot heartbeat"
    assert "StandardOutput=journal" in service_section, "Must log to journal"
    assert "StandardError=journal" in service_section, "Must log errors to journal"


def test_template_install_section(template_content: str) -> None:
    """[Install] section has required directives."""
    # Extract [Install] section
    install_match = re.search(r"\[Install\](.*?)$", template_content, re.DOTALL)
    assert install_match, "[Install] section not found or malformed"
    install_section = install_match.group(1)

    # Check required directives
    assert "WantedBy=multi-user.target" in install_section, "Must be wanted by multi-user.target"


def test_template_uses_instance_variable(template_content: str) -> None:
    """Template uses %i for instance-specific values."""
    # Should use %i in multiple places
    instance_uses = template_content.count("%i")
    assert instance_uses >= 3, f"Template should use %i at least 3 times, found {instance_uses}"

    # Specific checks
    assert re.search(r"Description=.*%i", template_content), "Description should use %i"
    # User or WorkingDirectory should use %i (or both)
    assert "%i" in template_content, "Template must use %i for instance-specific configuration"


def test_template_has_profile_token_placeholder(template_content: str) -> None:
    """Template loads TRADERBOT_PROFILE_TOKEN via EnvironmentFile (secure approach).

    The token is NOT embedded in the service file (which is world-readable).
    Instead, EnvironmentFile=%h/.traderbot/.env loads it at runtime from
    a chmod-600 file, keeping the token secret.
    """
    assert "EnvironmentFile=" in template_content, "Must use EnvironmentFile to load env vars securely"
    assert "%h/.traderbot/.env" in template_content, "EnvironmentFile must point to ~/.traderbot/.env"


def test_template_has_proper_security_constraints(template_content: str) -> None:
    """[Service] section has security hardening directives."""
    service_match = re.search(r"\[Service\](.*?)(?=\[Install\])", template_content, re.DOTALL)
    assert service_match, "[Service] section not found"
    service_section = service_match.group(1)

    assert "NoNewPrivileges=true" in service_section, "Must set NoNewPrivileges"
    assert "PrivateTmp=true" in service_section, "Must set PrivateTmp"
    assert "ProtectSystem=strict" in service_section, "Must set ProtectSystem=strict"


def test_template_has_documentation_comments(template_content: str) -> None:
    """Template includes helpful comments."""
    # Should have comments explaining customization
    assert "#" in template_content, "Template should have comments"

    # Check for key documentation
    comment_keywords = ["USAGE", "VENV_PATH", "CONFIG_DIR", "%i"]
    found_keywords = sum(1 for keyword in comment_keywords if keyword in template_content)
    assert found_keywords >= 3, f"Template should document key concepts, found {found_keywords}/4"


def test_template_filename_is_correct(template_path: Path) -> None:
    """Template filename follows systemd conventions."""
    assert template_path.name == "traderbot-agent@.service", "Template must be named with @ symbol"
    assert template_path.suffix == ".service", "Template must have .service extension"


def test_template_has_syslog_identifier(template_content: str) -> None:
    """Template has SyslogIdentifier for easier log filtering."""
    # Extract [Service] section
    service_match = re.search(r"\[Service\](.*?)(?=\[Install\])", template_content, re.DOTALL)
    assert service_match, "[Service] section not found"
    service_section = service_match.group(1)

    # Check for SyslogIdentifier with %i
    assert re.search(r"SyslogIdentifier=.*%i", service_section), "Should have SyslogIdentifier with %i for per-agent logs"


def test_template_has_execstart_and_envfile(template_content: str) -> None:
    """Template has ExecStart and EnvironmentFile in [Service] section."""
    service_match = re.search(r"\[Service\](.*?)(?=\[Install\])", template_content, re.DOTALL)
    assert service_match, "[Service] section not found"
    service_section = service_match.group(1)

    has_execstart = "ExecStart=" in service_section
    has_envfile = "EnvironmentFile=" in service_section
    assert has_execstart, "Must have ExecStart directive"
    assert has_envfile, "Must have EnvironmentFile for secure credential loading"

# Made with Bob

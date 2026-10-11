"""Machine-bound Fernet key derivation for encrypted local secrets."""

from __future__ import annotations

import base64
import getpass
import hashlib
import logging
import socket
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def derive_key(hostname: str, username: str, machine_id: str) -> Fernet:
    """Derive the machine-bound Fernet key from stable host identity."""
    digest = hashlib.sha256(f"{hostname}:{username}:{machine_id}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def machine_identity() -> tuple[str, str, str]:
    """Return the current machine's hostname, username, and stable identifier."""
    machine_id = _read_machine_id()
    if machine_id == "":
        logger.warning(
            "Could not determine a machine ID; encryption key degrades to hostname+username"
        )
    return socket.gethostname(), getpass.getuser(), machine_id


def _read_machine_id() -> str:
    if sys.platform == "linux":
        try:
            return Path("/etc/machine-id").read_text(encoding="ascii").strip()
        except OSError:
            return ""
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        for line in result.stdout.splitlines():
            if "IOPlatformUUID" in line:
                parts = line.split('"')
                if len(parts) >= 4 and parts[3] != "":
                    return parts[3]
        return ""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "csproduct", "get", "UUID"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return next(
            (
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip() and line.strip() != "UUID"
            ),
            "",
        )
    logger.warning("Unsupported platform %r for machine ID lookup", sys.platform)
    return ""


__all__ = ["derive_key", "machine_identity"]

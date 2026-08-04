"""Encrypted local fallback secrets store (DD-037 §9).

:class:`LocalEncryptedStore` is the air-gapped / testing fallback behind the
:class:`SecretsStore` facade. It implements the structural :class:`LocalStore`
protocol from ``protocols.py``: ``get``/``set``/``delete``/``get_namespace``
with ``service``/``key``/``value``/``namespace`` keyword arguments.

Storage layout (under the store's base directory, default
``~/.traderbot/secrets``)::

    secrets.json           encrypted envelope (version + one Fernet token)
    secrets.json.sha256    SHA-256 hex digest of secrets.json (integrity)

Both files are written with mode 0600 via a temp file + ``os.replace``.

Security properties (DD-037 §9):

* **Machine-derived encryption** — the Fernet key is
  ``base64(sha256("{hostname}:{username}:{machine_id}"))``. The file is
  unreadable if copied to another machine but decrypts automatically on the
  original machine with no user-supplied password. The machine ID is
  ``/etc/machine-id`` on Linux and the IOPlatformUUID (``ioreg``) on macOS;
  if neither is available the key degrades to hostname+username with a
  warning.
* **Integrity monitoring** — every read verifies the SHA-256 of the raw file
  against ``secrets.json.sha256`` and **fails closed** (raises
  :class:`SecretIntegrityError`) on any mismatch, missing integrity file, or
  decryption failure. Corruption never silently yields data.
* **No automatic rotation** — rotation is manual only (DD-037 §9).

The whole payload is encrypted as a single Fernet token so service/key names
are not visible at rest. **Not thread-safe** — concurrent writes can lose
updates; Phase 1 callers serialize access externally (same caveat as
:class:`LocalTokenStore`).
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, ValidationError

from traderbot.paths import get_data_dir
from traderbot.secrets.store import SecretNotFoundError

logger = logging.getLogger(__name__)

_INTEGRITY_SUFFIX = ".sha256"


class SecretIntegrityError(RuntimeError):
    """Raised when the store fails integrity or decryption checks (fail closed)."""


class SecretsEnvelope(BaseModel):
    """On-disk envelope: a version marker plus one opaque Fernet token."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: int
    payload: str


class SecretsPayload(BaseModel):
    """Decrypted payload: ``{namespace: {service: {key: value}}}`` mapping."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    secrets: dict[str, dict[str, dict[str, str]]]


def derive_key(hostname: str, username: str, machine_id: str) -> Fernet:
    """Derive the machine-bound Fernet key from the host identity (DD-037 §9).

    Args:
        hostname: The machine hostname.
        username: The OS account running TraderBot.
        machine_id: The stable platform machine ID, or ``""`` if unavailable.

    Returns:
        A :class:`Fernet` instance whose key is the SHA-256 of
        ``hostname:username:machine_id``, base64-encoded (exactly 32 bytes of
        key material, the Fernet requirement).
    """
    digest = hashlib.sha256(f"{hostname}:{username}:{machine_id}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _machine_identity() -> tuple[str, str, str]:
    """Return the current machine's ``(hostname, username, machine_id)``."""
    machine_id = _read_machine_id()
    if machine_id == "":
        logger.warning(
            "Could not determine a machine ID; encryption key degrades to hostname+username"
        )
    return socket.gethostname(), getpass.getuser(), machine_id


def _read_machine_id() -> str:
    """Return the stable machine ID, or ``""`` if the platform lookup fails.

    Linux reads ``/etc/machine-id``. macOS queries the IOPlatformUUID via
    ``ioreg`` — the field is double-quoted, so the value is extracted by
    splitting on ``"`` (the DD-037 command's single-quote awk yields nothing
    on real hardware).
    """
    if sys.platform == "linux":
        machine_id_file = Path("/etc/machine-id")
        try:
            return machine_id_file.read_text(encoding="ascii").strip()
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
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if stripped and stripped != "UUID":
                    return stripped
        except (OSError, subprocess.SubprocessError):
            pass
        return ""
    logger.warning("Unsupported platform %r for machine ID lookup", sys.platform)
    return ""


class LocalEncryptedStore:
    """Machine-bound encrypted :class:`LocalStore` (see module docstring).

    Args:
        base_path: Directory holding ``secrets.json`` and its integrity file
            (default ``~/.traderbot/secrets``).
    """

    def __init__(self, base_path: Path | None = None) -> None:
        if base_path is None:
            base_path = get_data_dir() / "secrets"
        self.secrets_dir: Path = Path(base_path)
        self.secrets_file: Path = self.secrets_dir / "secrets.json"
        self.integrity_file: Path = self.secrets_dir / f"secrets.json{_INTEGRITY_SUFFIX}"
        self._fernet: Fernet = derive_key(*_machine_identity())

    # LocalStore protocol ----------------------------------------------------

    def get(self, *, service: str, key: str, namespace: str) -> str | None:
        """Return the secret value for ``service``/``key``, or ``None`` if missing."""
        return self._load_payload().get(namespace, {}).get(service, {}).get(key)

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None:
        """Store ``value`` for ``service``/``key``, overwriting any existing value."""
        data = self._load_payload()
        if namespace not in data:
            data[namespace] = {}
        if service not in data[namespace]:
            data[namespace][service] = {}
        data[namespace][service][key] = value
        self._save_payload(data)

    def delete(self, *, service: str, key: str, namespace: str) -> None:
        """Delete the secret for ``service``/``key``.

        Raises:
            SecretNotFoundError: if the key does not exist.
        """
        data = self._load_payload()
        try:
            del data[namespace][service][key]
        except KeyError as exc:
            raise SecretNotFoundError(service=service, key=key, namespace=namespace) from exc
        self._save_payload(data)

    def get_namespace(self, namespace: str) -> dict[str, str]:
        """Return all ``{service}_{key} -> value`` pairs under ``namespace``."""
        return {
            f"{service}_{secret_key}": value
            for service, keys in self._load_payload().get(namespace, {}).items()
            for secret_key, value in keys.items()
        }

    # Storage ------------------------------------------------------------------

    def _load_payload(self) -> dict[str, dict[str, dict[str, str]]]:
        """Load, verify, and decrypt the store; ``{}`` when no store exists yet.

        Raises:
            SecretIntegrityError: on any integrity or decryption failure
                (tampered file, missing integrity file, foreign machine key).
        """
        if not self.secrets_file.exists():
            if self.integrity_file.exists():
                raise SecretIntegrityError(
                    f"integrity file {self.integrity_file} exists without {self.secrets_file}"
                )
            return {}
        self._verify_integrity()
        try:
            envelope = SecretsEnvelope.model_validate_json(
                self.secrets_file.read_text(encoding="utf-8"), strict=True
            )
        except (OSError, ValidationError) as exc:
            raise SecretIntegrityError(f"secrets file {self.secrets_file} is corrupt") from exc
        try:
            plaintext = self._fernet.decrypt(envelope.payload.encode("ascii"))
        except InvalidToken as exc:
            raise SecretIntegrityError(
                "secrets file cannot be decrypted with the machine-derived key"
            ) from exc
        try:
            payload = SecretsPayload.model_validate_json(plaintext, strict=True)
        except ValidationError as exc:
            raise SecretIntegrityError("decrypted secrets payload is malformed") from exc
        return payload.secrets

    def _verify_integrity(self) -> None:
        """Compare the stored SHA-256 against the raw file bytes (fail closed)."""
        try:
            expected = self.integrity_file.read_text(encoding="ascii").strip()
            actual = hashlib.sha256(self.secrets_file.read_bytes()).hexdigest()
        except (OSError, UnicodeDecodeError) as exc:
            raise SecretIntegrityError(
                f"cannot read integrity metadata for {self.secrets_file}"
            ) from exc
        if expected != actual:
            raise SecretIntegrityError("secrets file integrity check failed (tampering detected)")

    def _save_payload(self, data: dict[str, dict[str, dict[str, str]]]) -> None:
        """Encrypt ``data`` and atomically write ``secrets.json`` plus its hash.

        The integrity file is written after the payload; a crash between the
        two writes leaves a stale hash that fails closed on the next read —
        conservative by design.
        """
        plaintext = json.dumps({"secrets": data}, indent=2).encode("utf-8")
        envelope = json.dumps(
            {"version": 1, "payload": self._fernet.encrypt(plaintext).decode("ascii")},
            indent=2,
        )
        envelope += "\n"
        # Write in binary mode to avoid Windows \r\n line-ending translation,
        # which would break the integrity hash (computed on the exact bytes).
        envelope_bytes = envelope.encode("utf-8")
        self._atomic_write_bytes(self.secrets_file, envelope_bytes)
        digest = hashlib.sha256(envelope_bytes).hexdigest()
        self._atomic_write_bytes(self.integrity_file, f"{digest}\n".encode())

    def _atomic_write_bytes(self, path: Path, contents: bytes) -> None:
        """Write ``contents`` to ``path`` atomically with mode 0600 (POSIX).

        Uses binary mode to avoid platform-specific line-ending translation.
        """
        self.secrets_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_file = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=self.secrets_dir,
            delete=False,
        )
        tmp = Path(temp_file.name)
        try:
            with temp_file as fh:
                _ = fh.write(contents)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def _atomic_write(self, path: Path, contents: str) -> None:
        """Write ``contents`` to ``path`` atomically with mode 0600 (POSIX).

        Delegates to :meth:`_atomic_write_bytes` with UTF-8 encoded contents.
        """
        self._atomic_write_bytes(path, contents.encode("utf-8"))

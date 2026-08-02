"""Token storage and resolution for profile-based auth (DD-025, DD-037).

Phase 1 replaces Phase 0's hardcoded token mapping with a pluggable
``TokenStore``. The default implementation, :class:`LocalTokenStore`, persists
tokens as a JSON file under the TraderBot data directory
(``~/.traderbot/tokens.json``). A later phase (1.5) swaps in an Infisical-backed
store behind the same interface.

Module-level helpers (:func:`get_store`, :func:`set_store`,
:func:`resolve_token`) let callers resolve tokens against the active store and
let tests inject an in-memory or temp-file store without touching the real
``~/.traderbot`` directory.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class TokenStore(ABC):
    """Interface for mapping profile tokens to (profile_name, agent_id).

    Implementations are **not thread-safe**: concurrent writes can corrupt the
    backing store. Callers must serialize access (Phase 1 has no production
    caller beyond the resolver, so this is acceptable for now).
    """

    @abstractmethod
    def store_token(self, profile_name: str, agent_id: str, token: str) -> None:
        """Associate ``token`` with ``profile_name`` and ``agent_id``.

        Storing a token that already exists is idempotent: it overwrites the
        previous association.
        """

    @abstractmethod
    def resolve_token(self, token: str) -> tuple[str, str] | None:
        """Return ``(profile_name, agent_id)`` for ``token``, or ``None`` if unknown."""

    @abstractmethod
    def rotate_token(self, profile_name: str, agent_id: str) -> str:
        """Replace the token for ``profile_name``/``agent_id`` and return the new one.

        Raises:
            KeyError: if no token is associated with the given profile/agent.
        """

    @abstractmethod
    def list_tokens(self) -> list[dict]:
        """Return all tokens as ``[{"token", "profile", "agent_id"}, ...]``."""


class LocalTokenStore(TokenStore):
    """JSON-file-backed :class:`TokenStore`.

    Tokens are stored at ``<base_path>/tokens.json`` with schema::

        {"tokens": {"<token>": {"profile": "<name>", "agent_id": "<id>"}}}

    The backing directory is created (mode 0755) if missing; the token file is
    written with mode 0600 on POSIX and written atomically via ``os.replace``.

    **Not thread-safe** — concurrent access may lose updates. Phase 1 callers
    serialize access externally.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the store rooted at ``base_path`` (default ``~/.traderbot``)."""
        if base_path is None:
            base_path = Path.home() / ".traderbot"
        self.base_path = Path(base_path)
        self.token_file = self.base_path / "tokens.json"

    def _load(self) -> dict:
        """Read the token file into a dict, tolerant of a missing or corrupt file.

        Returns:
            The parsed store payload, or ``{"tokens": {}}`` when the file is
            missing or corrupt. Corrupt files are logged as warnings so callers
            can retry without crashing.
        """
        try:
            with self.token_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {"tokens": {}}
        except (json.JSONDecodeError, OSError):
            logger.warning("Token store %s is unreadable; treating as empty", self.token_file)
            return {"tokens": {}}
        if not isinstance(data, dict):
            logger.warning(
                "Token store %s has unexpected shape; treating as empty", self.token_file
            )
            return {"tokens": {}}
        data.setdefault("tokens", {})
        return data

    def _save(self, data: dict) -> None:
        """Write ``data`` atomically to the token file.

        Writes to a temp file in the same directory, then ``os.replace``s it
        into place (cross-platform atomic replace). On POSIX the file is chmod
        0600. Write failures propagate as :class:`OSError` — they are never
        swallowed, since silent persistence failure is a security risk.
        """
        self.base_path.mkdir(parents=True, exist_ok=True, mode=0o755)

        tmp = self.token_file.with_name(f"{self.token_file.name}.{os.getpid()}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            if sys.platform != "win32":
                os.chmod(tmp, 0o600)
            os.replace(tmp, self.token_file)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def store_token(self, profile_name: str, agent_id: str, token: str) -> None:
        data = self._load()
        data["tokens"][token] = {"profile": profile_name, "agent_id": agent_id}
        self._save(data)

    def resolve_token(self, token: str) -> tuple[str, str] | None:
        entry = self._load()["tokens"].get(token)
        if entry is None:
            return None
        return entry["profile"], entry["agent_id"]

    def rotate_token(self, profile_name: str, agent_id: str) -> str:
        data = self._load()
        tokens = data["tokens"]

        old_token = next(
            (
                tok
                for tok, entry in tokens.items()
                if entry.get("profile") == profile_name and entry.get("agent_id") == agent_id
            ),
            None,
        )
        if old_token is None:
            raise KeyError(f"No token for profile={profile_name!r} agent_id={agent_id!r}")

        new_token = generate_token()
        del tokens[old_token]
        tokens[new_token] = {"profile": profile_name, "agent_id": agent_id}
        self._save(data)
        return new_token

    def list_tokens(self) -> list[dict]:
        return [
            {"token": tok, "profile": entry["profile"], "agent_id": entry["agent_id"]}
            for tok, entry in self._load()["tokens"].items()
        ]


def generate_token() -> str:
    """Return a fresh 256-bit URL-safe token."""
    return secrets.token_urlsafe(32)


_active_store: TokenStore | None = None


def get_store() -> TokenStore:
    """Return the active :class:`TokenStore`, creating a default if unset.

    The default is a :class:`LocalTokenStore` rooted at ``~/.traderbot``. The
    default is cached so repeated calls resolve against the same store.
    """
    global _active_store
    if _active_store is None:
        _active_store = LocalTokenStore()
    return _active_store


def set_store(store: TokenStore | None) -> None:
    """Set the active :class:`TokenStore` (``None`` resets to the default).

    Primarily for test injection.
    """
    global _active_store
    _active_store = store


def resolve_token(token: str) -> tuple[str, str] | None:
    """Resolve ``token`` against the active store to ``(profile_name, agent_id)``."""
    return get_store().resolve_token(token)

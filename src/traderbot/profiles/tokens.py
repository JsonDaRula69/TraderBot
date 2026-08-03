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
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, TypedDict, override

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)


class TokenListEntry(TypedDict):
    token: str
    profile: str
    agent_id: str


class PersistedTokenEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    profile: str
    agent_id: str


class PersistedTokenPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)

    tokens: dict[str, PersistedTokenEntry]


@dataclass(frozen=True, slots=True)
class TokenNotFoundError(KeyError):
    profile_name: str
    agent_id: str

    @override
    def __str__(self) -> str:
        return f"No token for profile={self.profile_name!r} agent_id={self.agent_id!r}"


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
    def list_tokens(self) -> list[TokenListEntry]:
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
        self.base_path: Path = Path(base_path)
        self.token_file: Path = self.base_path / "tokens.json"

    def _load(self) -> PersistedTokenPayload:
        """Read and validate the token file, tolerating missing or corrupt data.

        Returns:
            The parsed store payload, or an empty payload when the file is
            missing or corrupt. Corrupt files are logged as warnings so callers
            can retry without crashing.
        """
        try:
            contents = self.token_file.read_text(encoding="utf-8")
            return PersistedTokenPayload.model_validate_json(contents, strict=True)
        except FileNotFoundError:
            return PersistedTokenPayload(tokens={})
        except (OSError, UnicodeDecodeError, ValidationError):
            logger.warning("Token store %s is unreadable; treating as empty", self.token_file)
            return PersistedTokenPayload(tokens={})

    def _save(self, data: PersistedTokenPayload) -> None:
        """Write ``data`` atomically to the token file.

        Securely creates a mode-0600 temp file in the same directory, then
        ``os.replace``s it into place. Write failures propagate as
        :class:`OSError` and the temp file is always removed.
        """
        self.base_path.mkdir(parents=True, exist_ok=True, mode=0o755)

        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{self.token_file.name}.",
            suffix=".tmp",
            dir=self.base_path,
            delete=False,
        )
        tmp = Path(temp_file.name)
        try:
            with temp_file as fh:
                json.dump(data.model_dump(mode="json"), fh, indent=2)
                _ = fh.write("\n")
            os.replace(tmp, self.token_file)
        finally:
            tmp.unlink(missing_ok=True)

    @override
    def store_token(self, profile_name: str, agent_id: str, token: str) -> None:
        data = self._load()
        tokens = dict(data.tokens)
        tokens[token] = PersistedTokenEntry(profile=profile_name, agent_id=agent_id)
        self._save(PersistedTokenPayload(tokens=tokens))

    @override
    def resolve_token(self, token: str) -> tuple[str, str] | None:
        entry = self._load().tokens.get(token)
        if entry is None:
            return None
        return entry.profile, entry.agent_id

    @override
    def rotate_token(self, profile_name: str, agent_id: str) -> str:
        data = self._load()
        matching_tokens = [
            token
            for token, entry in data.tokens.items()
            if entry.profile == profile_name and entry.agent_id == agent_id
        ]
        if not matching_tokens:
            raise TokenNotFoundError(profile_name=profile_name, agent_id=agent_id)

        tokens = dict(data.tokens)
        for old_token in matching_tokens:
            del tokens[old_token]
        new_token = generate_token()
        tokens[new_token] = PersistedTokenEntry(profile=profile_name, agent_id=agent_id)
        self._save(PersistedTokenPayload(tokens=tokens))
        return new_token

    @override
    def list_tokens(self) -> list[TokenListEntry]:
        return [
            {"token": token, "profile": entry.profile, "agent_id": entry.agent_id}
            for token, entry in self._load().tokens.items()
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

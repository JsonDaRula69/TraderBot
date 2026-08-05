"""SecretsResolver — builds SecretsStore from Infisical credentials (DD-037).

Phase 1.5 entry point: on first real-auth token resolution, the MCP resolver
lazily installs a :class:`SecretsStore`-backed :class:`TokenStoreAdapter`.
This module owns that construction:

* When ``~/.traderbot/infisical-credentials.json`` exists and Infisical is
  reachable, the store is Infisical-backed (primary).
* Otherwise the store falls back to :class:`LocalEncryptedStore` (air-gapped
  / testing) and the failure is logged at warning level.

The adapter is installed through the existing ``tokens.set_store()`` seam, so
``resolve_token_adapter`` continues to resolve via ``tokens.resolve_token``.
The module keeps a process-wide singleton resolver (``get_resolver`` /
``set_resolver``); tests reset it with ``set_resolver(None)``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from traderbot.profiles import tokens
from traderbot.secrets.adapter import TokenStoreAdapter
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.protocols import InfisicalClient
from traderbot.secrets.store import SecretsStore

logger = logging.getLogger(__name__)

_resolver: SecretsResolver | None = None


def build_secrets_store() -> SecretsStore:
    """Build a :class:`SecretsStore` from the Infisical credentials file.

    When ``~/.traderbot/infisical-credentials.json`` exists and Infisical is
    reachable, the store is Infisical-backed (primary); otherwise it falls back
    to :class:`LocalEncryptedStore`. Shared by :class:`SecretsResolver` and the
    daemon's component graph so both use the same construction.
    """
    creds_path = Path.home() / ".traderbot" / "infisical-credentials.json"
    try:
        creds = json.loads(creds_path.read_text())
        from infisical_sdk import InfisicalSDKClient

        # The SDK ships no type stubs; cast to the structural client protocol
        # (established pattern: Any first, then cast).
        client: Any = InfisicalSDKClient(host=creds["host"])
        client.auth.universal_auth.login(
            creds["machineIdentity"]["clientId"],
            creds["machineIdentity"]["clientSecret"],
        )
        store = SecretsStore(
            infisical_client=cast(InfisicalClient, client),
            local_store=LocalEncryptedStore(),
        )
        logger.info("SecretsResolver: Infisical connected")
        return store
    except Exception as exc:
        logger.warning("SecretsResolver: Infisical unreachable (%s), using local fallback", exc)
        return SecretsStore(infisical_client=None, local_store=LocalEncryptedStore())


class SecretsResolver:
    """Reads Infisical credentials, builds :class:`SecretsStore`, installs the adapter."""

    def __init__(self) -> None:
        store = build_secrets_store()
        self._store: SecretsStore = store
        # Install the adapter via the existing set_store() seam
        tokens.set_store(TokenStoreAdapter(store))


def get_resolver() -> SecretsResolver:
    """Return the process-wide :class:`SecretsResolver`, creating it on first use."""
    global _resolver
    if _resolver is None:
        _resolver = SecretsResolver()
    return _resolver


def set_resolver(resolver: SecretsResolver | None) -> None:
    """Set the process-wide resolver (``None`` resets it; used by tests)."""
    global _resolver
    _resolver = resolver

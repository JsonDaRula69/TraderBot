"""Migrate local profile tokens into Infisical (DD-037, one-way, Phase 1.5).

Reads the Phase 1 :class:`LocalTokenStore` file (``~/.traderbot/tokens.json``)
and stores each profile token as an Infisical secret via
:class:`SecretsStore`. The migration is one-way local → Infisical: the source
file is left untouched so operators can roll back.

Only profile tokens are migrated — API keys are out of scope for Phase 1.5.
Categories and permissions default to empty (populated on first profile
lookup), matching the 5-field profile-token document (DD-037 §4).

Run as a module: ``python -m traderbot.secrets.migrate``
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, cast

import requests
from infisical_sdk import InfisicalSDKClient

from traderbot.paths import get_data_dir
from traderbot.profiles.tokens import PersistedTokenPayload
from traderbot.secrets import SecretsStore
from traderbot.secrets.protocols import InfisicalClient

logger = logging.getLogger(__name__)

_TOKENS_PATH = get_data_dir() / "tokens.json"


def build_infisical_store() -> SecretsStore:
    """Build a SecretsStore backed by a live Infisical client from env config.

    Raises:
        RuntimeError: if ``INFISICAL_TOKEN`` or ``INFISICAL_DOMAIN`` is unset.
    """
    token = os.environ.get("INFISICAL_TOKEN")
    host = os.environ.get("INFISICAL_DOMAIN")
    if not token or not host:
        raise RuntimeError("INFISICAL_TOKEN and INFISICAL_DOMAIN must both be set")
    # cache_ttl=None disables the SDK's secrets cache (documented behavior),
    # matching the resolver script so rotated tokens are never masked.
    kwargs: dict[str, Any] = {"host": host, "token": token, "cache_ttl": None}
    client: Any = InfisicalSDKClient(**kwargs)
    return SecretsStore(infisical_client=cast(InfisicalClient, client))


def _load_local_tokens(path: Path) -> PersistedTokenPayload:
    """Read and validate the LocalTokenStore file at ``path``.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Local token store not found: {path} — nothing to migrate")
    contents = path.read_text(encoding="utf-8")
    return PersistedTokenPayload.model_validate_json(contents, strict=True)


def migrate_local_to_infisical(
    store: SecretsStore | None = None,
    tokens_path: Path | None = None,
) -> int:
    """Migrate profile tokens from ``tokens_path`` into ``store``.

    Args:
        store: Target store. When ``None``, a live Infisical-backed store is
            built from environment config.
        tokens_path: Source token file. Defaults to ``~/.traderbot/tokens.json``.

    Returns:
        The number of tokens migrated. Returns ``0`` when the source has no
        tokens (or the file is empty).

    Raises:
        FileNotFoundError: if the source token file is missing.
        ConnectionError: if Infisical is unreachable mid-migration.
    """
    if store is None:
        store = build_infisical_store()
    path = tokens_path or _TOKENS_PATH

    payload = _load_local_tokens(path)
    if not payload.tokens:
        logger.info("No profile tokens to migrate in %s", path)
        return 0

    count = 0
    for token_value, entry in payload.tokens.items():
        try:
            store.store_profile_token(
                agent_id=entry.agent_id,
                token=token_value,
                profile=entry.profile,
                categories=[],
                permissions=[],
            )
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Infisical unreachable while migrating agent_id={entry.agent_id!r}"
            ) from exc
        count += 1
        logger.info("Migrated token for agent_id=%s profile=%s", entry.agent_id, entry.profile)

    logger.info("Migrated %d token(s) to Infisical (original file kept)", count)
    return count


def main() -> None:
    """CLI entrypoint: migrate local profile tokens into Infisical."""
    try:
        count = migrate_local_to_infisical()
    except RuntimeError as exc:
        print(f"migrate: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except FileNotFoundError as exc:
        print(f"migrate: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ConnectionError as exc:
        print(f"migrate: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Migrated {count} profile token(s) to Infisical.")


if __name__ == "__main__":
    main()

"""TokenStoreAdapter — bridges SecretsStore to the TokenStore ABC (DD-025, DD-037).

The TokenStore interface used by MCP token resolution (``store_token``,
``resolve_token``, ``rotate_token``, ``list_tokens``) is implemented by
:class:`LocalTokenStore` in Phase 1. Phase 1.5 swaps the backing store for
:class:`SecretsStore` (Infisical primary, local encrypted fallback) behind the
same interface via this adapter, so ``resolve_token_adapter`` keeps working
unchanged while secrets move to the unified store.
"""

from __future__ import annotations

import secrets
from typing import override

from traderbot.profiles.registry import ProfileRegistry
from traderbot.profiles.tokens import TokenListEntry, TokenStore
from traderbot.secrets.store import SecretsStore


class TokenStoreAdapter(TokenStore):
    """Wraps :class:`SecretsStore` to implement the :class:`TokenStore` ABC interface.

    ``store_token`` enriches the stored entry with the profile's enabled
    categories and permissions (the 5-field DD-037 document), read from
    :class:`ProfileRegistry`. Rotation uses the same 256-bit generator as the
    local store so token strength is consistent across backends.
    """

    def __init__(self, secrets_store: SecretsStore) -> None:
        self._store: SecretsStore = secrets_store

    @override
    def store_token(self, profile_name: str, agent_id: str, token: str) -> None:
        profile = ProfileRegistry().get_profile(profile_name)
        if profile is None:
            categories: list[str] = []
            permissions: list[str] = []
        else:
            categories = [c.value for c in profile.enabled_categories]
            permissions = list(profile.permissions)
        self._store.store_profile_token(agent_id, token, profile_name, categories, permissions)

    @override
    def resolve_token(self, token: str) -> tuple[str, str] | None:
        return self._store.resolve_profile_token(token)

    @override
    def rotate_token(self, profile_name: str, agent_id: str) -> str:
        new_token = secrets.token_urlsafe(32)
        self._store.rotate_profile_token(agent_id, new_token)
        return new_token

    @override
    def list_tokens(self) -> list[TokenListEntry]:
        entries = self._store.list_profile_tokens()
        return [
            TokenListEntry(token=e["token"], profile=e["profile"], agent_id=e["agent_id"])
            for e in entries
        ]

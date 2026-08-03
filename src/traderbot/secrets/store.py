"""Unified secrets store — Infisical primary, local encrypted fallback (DD-037).

``SecretsStore`` is the concrete facade every TraderBot component uses for
secret access (API keys and profile tokens). It owns two backends behind one
interface:

* **Infisical** (primary, default) — API keys live in the ``TraderBot``
  project and profile tokens in the ``TraderBot Agent Tokens`` project.
  Namespaces map to ``(project, environment)`` targets (``_NAMESPACE_MAP``).
* **Local encrypted store** (fallback) — a namespaced ``secrets.json`` backed
  by :class:`LocalEncryptedStore` (Todo 4) for air-gapped and testing
  deployments.

The active backend is chosen at construction: an Infisical client, when
supplied, takes precedence; otherwise all operations route to the local
store. Both backends are typed structurally via Protocols (the Infisical SDK
ships no type stubs, and :class:`LocalEncryptedStore` does not exist yet), so
any object with the documented surface is accepted without runtime imports.
``get`` returns ``None`` for missing keys (mirroring
``TokenStore.resolve_token``); ``delete`` raises :class:`SecretNotFoundError`
when the key does not exist.

Keys are stored as flat ``{service}_{key}`` names in the Infisical vault (e.g.
service ``kalshi`` + key ``api_key`` → ``kalshi_api_key``, matching the DD-037
vault structure).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import override

from infisical_sdk.infisical_requests import APIError

from traderbot.secrets.protocols import InfisicalClient, LocalStore

# namespace -> (Infisical project, environment slug). The production
# environment slug is "prod" (matches the deployed Infisical instance).
_NAMESPACE_MAP: dict[str, tuple[str, str]] = {
    "global": ("TraderBot", "prod"),
    "tokens": ("TraderBot Agent Tokens", "prod"),
}


@dataclass(frozen=True, slots=True)
class SecretNotFoundError(KeyError):
    """Raised by :meth:`SecretsStore.delete` when the secret does not exist."""

    service: str
    key: str
    namespace: str

    @override
    def __str__(self) -> str:
        return (
            f"No secret for service={self.service!r} key={self.key!r} "
            f"in namespace={self.namespace!r}"
        )


class SecretsStore:
    """Unified secret access facade (see module docstring for the backend model).

    Args:
        infisical_client: Authenticated Infisical client (any object exposing
            a ``secrets`` resource with ``get/create/update/delete/list`` by
            name), or ``None`` to use the local store exclusively. When
            provided it takes precedence.
        local_store: Local backend store (structural match of
            :class:`LocalEncryptedStore`), or ``None``. The local backend
            delegates to its ``get``/``set``/``delete``/``get_namespace``
            methods, each accepting ``service``, ``key``, ``value``, and
            ``namespace`` keyword arguments.
    """

    def __init__(
        self,
        infisical_client: InfisicalClient | None = None,
        local_store: LocalStore | None = None,
    ) -> None:
        self._infisical_client: InfisicalClient | None = infisical_client
        self._local_store: LocalStore | None = local_store

    # Public interface -------------------------------------------------------

    def get(self, service: str, key: str, namespace: str = "global") -> str | None:
        """Return the secret value for ``service``/``key``, or ``None`` if missing."""
        if self._infisical_client is not None:
            project, env = self._infisical_target(namespace)
            return self._infisical_get(project, env, f"{service}_{key}")
        return self._local_get(service, key, namespace)

    def set(self, service: str, key: str, value: str, namespace: str = "global") -> None:
        """Store ``value`` for ``service``/``key``, overwriting any existing value."""
        if self._infisical_client is not None:
            project, env = self._infisical_target(namespace)
            self._infisical_set(project, env, f"{service}_{key}", value)
            return
        self._local_set(service, key, value, namespace)

    def delete(self, service: str, key: str, namespace: str = "global") -> None:
        """Delete the secret for ``service``/``key``.

        Raises:
            SecretNotFoundError: if the key does not exist.
        """
        if self.get(service, key, namespace) is None:
            raise SecretNotFoundError(service=service, key=key, namespace=namespace)
        if self._infisical_client is not None:
            project, env = self._infisical_target(namespace)
            self._infisical_delete(project, env, f"{service}_{key}")
            return
        self._local_delete(service, key, namespace)

    def get_namespace(self, namespace: str) -> dict[str, str]:
        """Return all ``key -> value`` pairs stored under ``namespace``."""
        if self._infisical_client is not None:
            project, env = self._infisical_target(namespace)
            return self._infisical_list(project, env)
        return self._local_list(namespace)

    # Infisical backend ------------------------------------------------------

    def _infisical_target(self, namespace: str) -> tuple[str, str]:
        """Map ``namespace`` to its ``(project, environment)`` Infisical target."""
        try:
            return _NAMESPACE_MAP[namespace]
        except KeyError as exc:
            raise KeyError(f"Unknown secrets namespace: {namespace!r}") from exc

    def _infisical_get(self, project: str, env: str, key: str) -> str | None:
        """Return the Infisical secret value for ``key``, or ``None`` if missing."""
        client = self._infisical_client
        if client is None:
            raise RuntimeError("No Infisical client configured")
        try:
            result = client.secrets.get_secret_by_name(
                secret_name=key,
                environment_slug=env,
                secret_path="/",
                project_slug=project,
                view_secret_value=True,
            )
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise
        return result.secretValue

    def _infisical_set(self, project: str, env: str, key: str, value: str) -> None:
        """Create or update the Infisical secret ``key`` to ``value`` (idempotent)."""
        client = self._infisical_client
        if client is None:
            raise RuntimeError("No Infisical client configured")
        secrets = client.secrets
        if self._infisical_get(project, env, key) is not None:
            _ = secrets.update_secret_by_name(
                current_secret_name=key,
                secret_path="/",
                environment_slug=env,
                project_slug=project,
                secret_value=value,
            )
        else:
            _ = secrets.create_secret_by_name(
                secret_name=key,
                secret_path="/",
                environment_slug=env,
                project_slug=project,
                secret_value=value,
            )

    def _infisical_delete(self, project: str, env: str, key: str) -> None:
        """Delete the Infisical secret ``key``."""
        client = self._infisical_client
        if client is None:
            raise RuntimeError("No Infisical client configured")
        _ = client.secrets.delete_secret_by_name(
            secret_name=key,
            secret_path="/",
            environment_slug=env,
            project_slug=project,
        )

    def _infisical_list(self, project: str, env: str) -> dict[str, str]:
        """Return all ``key -> value`` pairs in the Infisical ``project``/``env``."""
        client = self._infisical_client
        if client is None:
            raise RuntimeError("No Infisical client configured")
        response = client.secrets.list_secrets(
            environment_slug=env,
            secret_path="/",
            project_slug=project,
            view_secret_value=True,
        )
        return {secret.secretKey: secret.secretValue for secret in response.secrets}

    # Local backend ----------------------------------------------------------

    def _local_get(self, service: str, key: str, namespace: str) -> str | None:
        store = self._require_local_store()
        return store.get(service=service, key=key, namespace=namespace)

    def _local_set(self, service: str, key: str, value: str, namespace: str) -> None:
        store = self._require_local_store()
        store.set(service=service, key=key, value=value, namespace=namespace)

    def _local_delete(self, service: str, key: str, namespace: str) -> None:
        store = self._require_local_store()
        store.delete(service=service, key=key, namespace=namespace)

    def _local_list(self, namespace: str) -> dict[str, str]:
        store = self._require_local_store()
        return store.get_namespace(namespace)

    def _require_local_store(self) -> LocalStore:
        if self._local_store is None:
            raise RuntimeError("No local secrets store configured")
        return self._local_store

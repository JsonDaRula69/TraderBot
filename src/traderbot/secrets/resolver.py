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

import inspect
import logging
import os
from collections.abc import Mapping
from typing import ClassVar, Literal, final

from infisical_sdk import InfisicalSDKClient
from infisical_sdk.infisical_requests import InfisicalError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from requests import RequestException

from traderbot.deploy.validation import validate_infisical_origin
from traderbot.paths import get_data_dir
from traderbot.profiles import tokens
from traderbot.secrets.adapter import TokenStoreAdapter
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.protocols import SecretListResult, SecretResult, SecretsResource
from traderbot.secrets.store import SecretsStore

logger = logging.getLogger(__name__)

_resolver: SecretsResolver | None = None
type SecretsBackendName = Literal["infisical", "local-encrypted"]
_PROXY_NAMES = frozenset({"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"})
_ACCESS_TARGETS = (
    ("traderbot", "prod", "/"),
    ("traderbot-agent-tokens", "prod", "/"),
)


# The shared document includes routing metadata owned by openclaw-infisical-resolver;
# both readers below ignore unrelated fields while requiring the login credentials.
class _MachineIdentity(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    client_id: str = Field(validation_alias="clientId")
    client_secret: SecretStr = Field(validation_alias="clientSecret")


class _InfisicalCredentials(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    host: str
    machine_identity: _MachineIdentity = Field(validation_alias="machineIdentity")


@final
class _SdkSecretsAdapter:
    def __init__(self, client: InfisicalSDKClient) -> None:
        self._client: InfisicalSDKClient = client

    def get_secret_by_name(
        self,
        *,
        secret_name: str,
        environment_slug: str,
        secret_path: str,
        project_slug: str,
        view_secret_value: bool = True,
    ) -> SecretResult:
        return self._client.secrets.get_secret_by_name(
            secret_name=secret_name,
            environment_slug=environment_slug,
            secret_path=secret_path,
            project_slug=project_slug,
            view_secret_value=view_secret_value,
        )

    def create_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str,
        secret_value: str,
    ) -> SecretResult:
        return self._client.secrets.create_secret_by_name(
            secret_name=secret_name,
            secret_path=secret_path,
            environment_slug=environment_slug,
            project_slug=project_slug,
            secret_value=secret_value,
        )

    def update_secret_by_name(
        self,
        *,
        current_secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str,
        secret_value: str,
    ) -> SecretResult:
        return self._client.secrets.update_secret_by_name(
            current_secret_name=current_secret_name,
            secret_path=secret_path,
            environment_slug=environment_slug,
            project_slug=project_slug,
            secret_value=secret_value,
        )

    def delete_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str,
    ) -> SecretResult:
        return self._client.secrets.delete_secret_by_name(
            secret_name=secret_name,
            secret_path=secret_path,
            environment_slug=environment_slug,
            project_slug=project_slug,
        )

    def list_secrets(
        self,
        *,
        environment_slug: str,
        secret_path: str,
        project_slug: str,
        view_secret_value: bool = True,
    ) -> SecretListResult:
        return self._client.secrets.list_secrets(
            environment_slug=environment_slug,
            secret_path=secret_path,
            project_slug=project_slug,
            view_secret_value=view_secret_value,
        )


@final
class _SdkClientAdapter:
    def __init__(self, client: InfisicalSDKClient) -> None:
        self._client: InfisicalSDKClient = client
        self._secrets: SecretsResource = _SdkSecretsAdapter(client)

    @property
    def secrets(self) -> SecretsResource:
        return self._secrets

    def close(self) -> None:
        self._client.close()


@final
class _ManagedSecretsStore(SecretsStore):
    def __init__(self, client: _SdkClientAdapter, local_store: LocalEncryptedStore) -> None:
        super().__init__(infisical_client=client, local_store=local_store)
        self._client: _SdkClientAdapter | None = client

    def close(self) -> None:
        client = self._client
        if client is not None:
            client.close()
            self._client = None


def close_secrets_store(store: SecretsStore) -> None:
    """Close an SDK-backed resolver store; encrypted local stores are resource-free."""
    if isinstance(store, _ManagedSecretsStore):
        store.close()


def _proxy_environment_is_unsafe(environment: Mapping[str, str]) -> bool:
    return any(name.upper() in _PROXY_NAMES and value != "" for name, value in environment.items())


def build_secrets_store_selection(
    host_override: str | None = None,
) -> tuple[SecretsStore, SecretsBackendName]:
    """Build a :class:`SecretsStore` from the Infisical credentials file.

    When ``~/.traderbot/infisical-credentials.json`` exists and Infisical is
    reachable, the store is Infisical-backed (primary); otherwise it falls back
    to :class:`LocalEncryptedStore`. Shared by :class:`SecretsResolver` and the
    daemon's component graph so both use the same construction.
    """
    safe_override = None if host_override is None else validate_infisical_origin(host_override)
    if _proxy_environment_is_unsafe(os.environ):
        logger.warning("SecretsResolver: proxy environment forbids Infisical SDK use")
        return SecretsStore(local_store=LocalEncryptedStore()), "local-encrypted"
    creds_path = get_data_dir() / "infisical-credentials.json"
    client: InfisicalSDKClient | None = None
    selection_failed = False
    try:
        creds = _InfisicalCredentials.model_validate_json(creds_path.read_text())
        host = validate_infisical_origin(creds.host) if safe_override is None else safe_override
        signature = inspect.signature(InfisicalSDKClient)
        arguments = signature.bind(host=host, cache_ttl=None)
        client = InfisicalSDKClient(*arguments.args, **arguments.kwargs)
        _ = client.auth.universal_auth.login(
            creds.machine_identity.client_id,
            creds.machine_identity.client_secret.get_secret_value(),
        )
        secrets_resource = _SdkSecretsAdapter(client)
        for project, environment, path in _ACCESS_TARGETS:
            _ = secrets_resource.list_secrets(
                environment_slug=environment,
                secret_path=path,
                project_slug=project,
                view_secret_value=False,
            )
        store = _ManagedSecretsStore(_SdkClientAdapter(client), LocalEncryptedStore())
        logger.info("SecretsResolver: Infisical connected")
        return store, "infisical"
    except (InfisicalError, OSError, RequestException, TypeError, ValidationError, ValueError):
        selection_failed = True
    close_failed = False
    if client is not None:
        try:
            client.close()
        except (OSError, RuntimeError, TypeError, ValueError):
            close_failed = True
        client = None
    reason = "sdk-close-failed" if close_failed else "access-or-login-unusable"
    if selection_failed:
        logger.warning(
            "SecretsResolver: Infisical unusable, using encrypted local fallback; reason=%s",
            reason,
        )
    local = SecretsStore(infisical_client=None, local_store=LocalEncryptedStore())
    return local, "local-encrypted"


def build_secrets_store(host_override: str | None = None) -> SecretsStore:
    """Build the runtime facade, preferring an existing usable Infisical setup."""
    store, _ = build_secrets_store_selection(host_override)
    return store


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

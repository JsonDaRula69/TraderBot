"""Secure Kalshi secret acquisition for deploy step 4."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, final, override

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from infisical_sdk.infisical_requests import InfisicalError
from pydantic import BaseModel, ConfigDict, SecretStr
from requests import RequestException

from traderbot.deploy.capabilities import infisical_is_running
from traderbot.deploy.validation import SecretReconciliationApprovals, validate_infisical_origin
from traderbot.kalshi.client import Environment
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.resolver import build_secrets_store_selection, close_secrets_store
from traderbot.secrets.store import SecretsStore

type SecretsBackend = Literal["infisical", "local-encrypted"]
type SecretProvisionStatus = Literal["created", "existing", "reconciled", "replaced"]

_KALSHI_SECRET_SERVICES: dict[Environment, str] = {
    "production": "kalshi",
    "demo": "kalshi_demo",
}


def kalshi_secret_service(environment: Environment) -> str:
    """Return the flat secret service name for a Kalshi environment."""
    return _KALSHI_SECRET_SERVICES[environment]


def kalshi_secret_names(environment: Environment) -> tuple[str, str]:
    """Return the canonical flat secret names for a Kalshi environment."""
    service = kalshi_secret_service(environment)
    return (f"{service}_api_key", f"{service}_private_key_pem")


class DeploySecrets(Protocol):
    def get(self, service: str, key: str, namespace: str = "global") -> str | None: ...

    def set(
        self,
        service: str,
        key: str,
        value: str,
        namespace: str = "global",
    ) -> None: ...


class KalshiSecretPair(BaseModel):
    """A redacted, immutable Kalshi credential pair."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    private_key_pem: SecretStr

    @classmethod
    def from_plain(cls, api_key: str, private_key_pem: str) -> KalshiSecretPair:
        """Parse plaintext only at the hidden or environment boundary."""
        return cls(api_key=SecretStr(api_key), private_key_pem=SecretStr(private_key_pem))


@dataclass(frozen=True, slots=True)
class SecretProvisionReport:
    status: SecretProvisionStatus
    backend: SecretsBackend
    secret_names: tuple[str, str] = ("kalshi_api_key", "kalshi_private_key_pem")


@dataclass(frozen=True, slots=True)
class SecretsSelection:
    store: SecretsStore
    backend: SecretsBackend
    fallback_store: SecretsStore

    def close(self) -> None:
        """Release the selected SDK client; local fallback owns no live resource."""
        close_secrets_store(self.store)


@dataclass(slots=True)
class MissingSecretEnvironmentError(RuntimeError):
    names: tuple[str, ...]

    @override
    def __str__(self) -> str:
        return f"missing secret environment variables: {', '.join(self.names)}"


@dataclass(slots=True)
class SecretPairValidationError(RuntimeError):
    reason: str

    @override
    def __str__(self) -> str:
        return f"Kalshi secret pair is invalid: {self.reason}"


@dataclass(slots=True)
class SecretReconciliationError(RuntimeError):
    written_secret_names: tuple[str, ...]
    pending_secret_names: tuple[str, ...]

    @override
    def __str__(self) -> str:
        written = ", ".join(self.written_secret_names)
        pending = ", ".join(self.pending_secret_names)
        return f"secret reconciliation required; written={written}; pending={pending}"


@dataclass(slots=True)
class SecretPairApprovalError(RuntimeError):
    reason: str

    @override
    def __str__(self) -> str:
        return f"explicit Kalshi secret approval required: {self.reason}"


class SecretPersistenceVerificationError(RuntimeError):
    """Raised when a backend acknowledges a set without persisting it."""


@final
class EnvironmentSecretInput:
    def __init__(
        self,
        api_key_name: str,
        private_key_name: str,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._api_key_name: str = api_key_name
        self._private_key_name: str = private_key_name
        self._environment: Mapping[str, str] = os.environ if environment is None else environment

    def read(self) -> KalshiSecretPair:
        missing = tuple(
            name
            for name in (self._api_key_name, self._private_key_name)
            if name not in self._environment
        )
        if missing:
            raise MissingSecretEnvironmentError(missing)
        return KalshiSecretPair.from_plain(
            self._environment[self._api_key_name],
            self._environment[self._private_key_name],
        )


@final
class HiddenSecretInput:
    def __init__(self, ask_hidden: Callable[[str], str]) -> None:
        self._ask_hidden: Callable[[str], str] = ask_hidden

    def read(self) -> KalshiSecretPair:
        return KalshiSecretPair.from_plain(
            self._ask_hidden("Kalshi API key"),
            self._ask_hidden("Kalshi RSA private key PEM"),
        )


@dataclass(slots=True)
class SecretInputRequiredError(RuntimeError):
    @override
    def __str__(self) -> str:
        return "Kalshi secret environment references are required when no valid pair is stored"


def validate_kalshi_secret_pair(pair: KalshiSecretPair) -> KalshiSecretPair:
    if pair.api_key.get_secret_value().strip() == "":
        raise SecretPairValidationError("API key is empty")
    try:
        key = serialization.load_pem_private_key(
            pair.private_key_pem.get_secret_value().encode("utf-8"),
            None,
        )
    except (TypeError, ValueError) as exc:
        raise SecretPairValidationError("private key is not a parseable PEM") from exc
    if not isinstance(key, RSAPrivateKey):
        raise SecretPairValidationError("private key is not RSA")
    return pair


def provision_kalshi_secrets(
    store: DeploySecrets,
    read_replacement: Callable[[], KalshiSecretPair],
    *,
    backend: SecretsBackend,
    approvals: SecretReconciliationApprovals | None = None,
    environment: Environment = "production",
) -> SecretProvisionReport:
    authority = approvals or SecretReconciliationApprovals()
    service = kalshi_secret_service(environment)
    secret_names = kalshi_secret_names(environment)
    existing_api_key = store.get(service, "api_key")
    existing_private_key = store.get(service, "private_key_pem")
    if existing_api_key is not None and existing_private_key is not None:
        try:
            _ = validate_kalshi_secret_pair(
                KalshiSecretPair.from_plain(existing_api_key, existing_private_key)
            )
        except SecretPairValidationError:
            if not authority.replace_existing:
                raise SecretPairApprovalError("stored pair is malformed") from None
            status: SecretProvisionStatus = "replaced"
        else:
            return SecretProvisionReport(status="existing", backend=backend)
    elif existing_api_key is not None or existing_private_key is not None:
        if not authority.reconcile_incomplete:
            raise SecretPairApprovalError("stored pair is incomplete")
        status = "reconciled"
    else:
        status = "created"

    replacement = validate_kalshi_secret_pair(read_replacement())
    desired = {
        "api_key": replacement.api_key.get_secret_value(),
        "private_key_pem": replacement.private_key_pem.get_secret_value(),
    }
    existing = {"api_key": existing_api_key, "private_key_pem": existing_private_key}
    mismatched = tuple(
        key for key, value in existing.items() if value is not None and value != desired[key]
    )
    if mismatched and not authority.replace_existing:
        raise SecretPairApprovalError("stored field differs from supplied replacement")
    if mismatched:
        status = "replaced"

    for key in ("api_key", "private_key_pem"):
        if existing[key] == desired[key]:
            continue
        failed_state: tuple[tuple[str, ...], tuple[str, ...]] | None = None
        try:
            store.set(service, key, desired[key])
            if store.get(service, key) != desired[key]:
                raise SecretPersistenceVerificationError
        except (InfisicalError, OSError, RequestException, RuntimeError):
            failed_state = _reconciliation_state(
                store,
                desired,
                service=service,
                secret_names=secret_names,
            )
        if failed_state is not None:
            written, pending = failed_state
            raise SecretReconciliationError(written, pending) from None
        existing[key] = desired[key]
    return SecretProvisionReport(status=status, backend=backend, secret_names=secret_names)


def _reconciliation_state(
    store: DeploySecrets,
    desired: dict[str, str],
    *,
    service: str,
    secret_names: tuple[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    written: list[str] = []
    pending: list[str] = []
    for key, canonical in zip(("api_key", "private_key_pem"), secret_names):
        try:
            durable = store.get(service, key) == desired[key]
        except (InfisicalError, OSError, RequestException, RuntimeError):
            durable = False
        (written if durable else pending).append(canonical)
    return tuple(written), tuple(pending)


def select_deploy_secrets(
    infisical_url: str,
    *,
    local_path: Path | None = None,
    status_probe: Callable[[str], bool] = infisical_is_running,
) -> SecretsSelection:
    safe_url = validate_infisical_origin(infisical_url)
    if status_probe(safe_url):
        store, backend = build_secrets_store_selection(host_override=safe_url)
        if backend == "infisical":
            return SecretsSelection(
                store=store,
                backend="infisical",
                fallback_store=SecretsStore(local_store=LocalEncryptedStore(base_path=local_path)),
            )
    local_store = LocalEncryptedStore(base_path=local_path)
    fallback = SecretsStore(local_store=local_store)
    return SecretsSelection(
        store=fallback,
        backend="local-encrypted",
        fallback_store=fallback,
    )


__all__ = [
    "DeploySecrets",
    "EnvironmentSecretInput",
    "HiddenSecretInput",
    "KalshiSecretPair",
    "MissingSecretEnvironmentError",
    "SecretPairValidationError",
    "SecretPairApprovalError",
    "SecretInputRequiredError",
    "SecretProvisionReport",
    "SecretReconciliationError",
    "SecretsSelection",
    "SecretsBackend",
    "kalshi_secret_names",
    "kalshi_secret_service",
    "provision_kalshi_secrets",
    "select_deploy_secrets",
    "validate_kalshi_secret_pair",
]

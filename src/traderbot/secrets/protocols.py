"""Structural protocols for the secrets backends (DD-037).

The Infisical SDK ships no type stubs and :class:`LocalEncryptedStore` does
not exist yet, so :class:`SecretsStore` is typed against minimal structural
surfaces instead of concrete classes. Any object exposing the documented
methods is accepted, which keeps tests mockable and the facade decoupled
from third-party types.

Attribute protocols are declared as read-only ``@property`` so covariance
holds: a mutable attribute is invariant and requires a bidirectional check
that concrete implementations do not satisfy.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class SecretResult(Protocol):
    """A single Infisical secret (structural subset of ``BaseSecret``)."""

    secretKey: str
    secretValue: str


class SecretListResult(Protocol):
    """Infisical ``list_secrets`` response (structural subset of ``ListSecretsResponse``)."""

    @property
    def secrets(self) -> Sequence[SecretResult]: ...


class SecretsResource(Protocol):
    """The ``client.secrets`` surface used by the facade (structural)."""

    def get_secret_by_name(
        self,
        *,
        secret_name: str,
        environment_slug: str,
        secret_path: str,
        project_slug: str | None = None,
        view_secret_value: bool = True,
    ) -> SecretResult: ...

    def create_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        secret_value: str | None = None,
    ) -> SecretResult: ...

    def update_secret_by_name(
        self,
        *,
        current_secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
        secret_value: str | None = None,
    ) -> SecretResult: ...

    def delete_secret_by_name(
        self,
        *,
        secret_name: str,
        secret_path: str,
        environment_slug: str,
        project_slug: str | None = None,
    ) -> SecretResult: ...

    def list_secrets(
        self,
        *,
        environment_slug: str,
        secret_path: str,
        project_slug: str | None = None,
        view_secret_value: bool = True,
    ) -> SecretListResult: ...


class InfisicalClient(Protocol):
    """Minimal :class:`InfisicalSDKClient` surface used by the facade (structural)."""

    @property
    def secrets(self) -> SecretsResource: ...


class LocalStore(Protocol):
    """Local backend surface (structural — :class:`LocalEncryptedStore` from Todo 4)."""

    def get(self, *, service: str, key: str, namespace: str) -> str | None: ...

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None: ...

    def delete(self, *, service: str, key: str, namespace: str) -> None: ...

    def get_namespace(self, namespace: str) -> dict[str, str]: ...

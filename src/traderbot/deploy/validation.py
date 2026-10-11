"""Shared trust-boundary parsing for deploy steps 4-5."""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class DeployBoundaryError(ValueError):
    """Raised when an unsafe value bypasses the top-level config boundary."""


class SecretReconciliationApprovals(BaseModel):
    """Explicit authority for repairing pre-existing Kalshi secret state."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    reconcile_incomplete: bool = False
    replace_existing: bool = False


def validate_infisical_origin(origin: str) -> str:
    """Parse a loopback-only plain-HTTP Infisical origin."""
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query != ""
        or parsed.fragment != ""
    ):
        raise DeployBoundaryError("Infisical origin must be loopback-only HTTP")
    return origin.rstrip("/")


def validate_secret_references(
    api_key_name: str | None,
    private_key_name: str | None,
) -> tuple[str | None, str | None]:
    """Parse a complete optional environment-reference pair."""
    if api_key_name is None and private_key_name is None:
        return None, None
    if api_key_name is None or private_key_name is None:
        raise DeployBoundaryError("Kalshi environment references must be a complete pair")
    if any(_ENVIRONMENT_NAME.fullmatch(name) is None for name in (api_key_name, private_key_name)):
        raise DeployBoundaryError("Kalshi references must be environment variable names")
    return api_key_name, private_key_name


__all__ = [
    "DeployBoundaryError",
    "SecretReconciliationApprovals",
    "validate_infisical_origin",
    "validate_secret_references",
]

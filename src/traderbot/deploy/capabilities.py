"""Read-only deployment capability detection."""

from __future__ import annotations

import os
import platform
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

import httpx

from traderbot.deploy.validation import validate_infisical_origin
from traderbot.services.deploy import detect_service_manager

type ServiceManager = Literal["systemd", "launchd", "windows", "none"]

_INFISICAL_ORIGIN: Final = "http://localhost:8080"
_INFISICAL_TIMEOUT_SECONDS: Final = 1.0
_SERVICE_MANAGERS: Final[Mapping[str, ServiceManager]] = MappingProxyType(
    {
        "systemd": "systemd",
        "launchd": "launchd",
        "windows": "windows",
        "none": "none",
    }
)


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Deployment-relevant observations for the current host."""

    openclaw_installed: bool
    openclaw_path: str | None
    docker_available: bool
    service_manager: ServiceManager
    display_available: bool
    infisical_running: bool
    python_version: str


def detect_capabilities() -> Capabilities:
    """Observe local host capabilities without installing or executing tools."""
    openclaw_path = shutil.which("openclaw")
    service_manager = _SERVICE_MANAGERS.get(detect_service_manager(), "none")

    infisical_running = infisical_is_running(_INFISICAL_ORIGIN)

    return Capabilities(
        openclaw_installed=openclaw_path is not None,
        openclaw_path=openclaw_path,
        docker_available=shutil.which("docker") is not None,
        service_manager=service_manager,
        display_available=bool(os.environ.get("DISPLAY")),
        infisical_running=infisical_running,
        python_version=platform.python_version(),
    )


def infisical_is_running(origin: str) -> bool:
    """Probe the canonical Infisical status endpoint without environment proxies."""
    safe_origin = validate_infisical_origin(origin)
    status_url = f"{safe_origin}/api/status"
    try:
        response = httpx.get(
            status_url,
            timeout=_INFISICAL_TIMEOUT_SECONDS,
            trust_env=False,
        )
    except httpx.RequestError:
        return False
    return response.status_code == 200

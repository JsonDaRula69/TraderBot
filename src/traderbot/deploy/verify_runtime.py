"""Probe service and daemon health for deployment verification."""

from __future__ import annotations

from typing import ClassVar, Final, Literal

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from traderbot.deploy.openclaw_process import run_bounded
from traderbot.deploy.verify_models import ProbeResult, VerificationRequest
from traderbot.services.deploy import detect_service_manager, service_destination
from traderbot.services.paths import resolve_bin_paths

type Manager = Literal["systemd", "launchd", "windows", "none"]
_ACTIVE: Final = frozenset({"active", "running"})


class HealthComponents(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)
    mcp_server: Literal["running"]
    auth: Literal["resolved"]
    data_pipeline: Literal["running", "stopped"]
    websocket: Literal["connected", "disconnected", "fail_open", "not_started"]
    database: Literal["initialized"]
    chromadb: Literal["initialized"]
    chromadb_lock: Literal["held"]


class HealthResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)
    status: Literal["ok"]
    components: HealthComponents


def _manager(value: str) -> Manager:
    if value == "systemd":
        return "systemd"
    if value == "launchd":
        return "launchd"
    if value == "windows":
        return "windows"
    return "none"


def service_status() -> ProbeResult:
    manager = _manager(detect_service_manager())
    if manager == "none":
        return ProbeResult.degraded("manager_unsupported", "Service manager unsupported")
    if manager == "systemd":
        argv = ["systemctl", "is-active", "traderbot.service"]
    elif manager == "launchd":
        argv = ["launchctl", "print", "system/com.traderbot.daemon"]
    else:
        argv = ["sc.exe", "query", "traderbot"]
    expected = service_destination(manager, resolve_bin_paths())
    if not expected.is_file():
        return ProbeResult.failed("service_not_installed", "Daemon service is not installed")
    process = run_bounded(argv, timeout=3.0)
    if process is None:
        return ProbeResult.failed("service_status_error", "Service status command failed")
    if process.returncode != 0:
        return ProbeResult.failed("service_inactive", "Daemon service is inactive")
    output = process.stdout.lower()
    if manager == "windows" and not any(value in output for value in _ACTIVE):
        return ProbeResult.failed("service_inactive", "Daemon service is inactive")
    return ProbeResult.passed("service_active")


def evaluate_health(components: HealthComponents) -> ProbeResult:
    if components.data_pipeline != "running":
        return ProbeResult.failed("daemon_pipeline_inactive", "Daemon pipeline is inactive")
    if components.websocket == "connected":
        return ProbeResult.passed("daemon_health_exact")
    return ProbeResult.failed("daemon_websocket_inactive", "Daemon WebSocket is inactive")


async def daemon_runtime(request: VerificationRequest, token: SecretStr) -> ProbeResult:
    try:
        with anyio.fail_after(request.timeout_seconds):
            async with streamable_http_client(request.daemon_mcp_url) as transport:
                async with ClientSession(*transport) as session:
                    _ = await session.initialize()
                    result = await session.call_tool(
                        "health",
                        {"token": token.get_secret_value()},
                        read_timeout_seconds=request.timeout_seconds,
                    )
    except (OSError, TimeoutError, ValueError):
        return ProbeResult.failed("daemon_unreachable", "Daemon MCP health is unavailable")
    if result.is_error or not result.content:
        return ProbeResult.failed("daemon_health_error", "Daemon rejected the health probe")
    first = result.content[0]
    text = getattr(first, "text", None)
    if not isinstance(text, str):
        return ProbeResult.failed("daemon_health_malformed", "Daemon health is malformed")
    try:
        response = HealthResponse.model_validate_json(text)
    except ValidationError:
        return ProbeResult.failed("daemon_health_degraded", "Daemon components are degraded")
    return evaluate_health(response.components)


__all__ = ["daemon_runtime", "evaluate_health", "service_status"]

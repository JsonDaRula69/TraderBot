"""Focused tests for deploy capability detection."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import FrozenInstanceError
from unittest import mock

import httpx
import pytest

import traderbot.deploy.capabilities as capabilities
from traderbot.deploy.capabilities import Capabilities, detect_capabilities, infisical_is_running
from traderbot.deploy.validation import DeployBoundaryError
from traderbot.services.deploy import detect_service_manager


@pytest.fixture(autouse=True)
def isolate_external_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: deterministic defaults for every external observation
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(shutil, "which", mock.Mock(return_value=None))
    monkeypatch.setattr(capabilities, "detect_service_manager", mock.Mock(return_value="none"))
    monkeypatch.setattr(platform, "python_version", mock.Mock(return_value="3.12.13"))
    monkeypatch.setattr(
        httpx,
        "get",
        mock.Mock(return_value=httpx.Response(503)),
    )


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Linux", "systemd"),
        ("Darwin", "launchd"),
        ("Windows", "windows"),
        ("FreeBSD", "none"),
    ],
)
def test_existing_service_manager_values(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    expected: str,
) -> None:
    # Given: each platform value supported by the existing service detector
    monkeypatch.setattr(platform, "system", lambda: system)

    # When: the established detector observes that platform
    result = detect_service_manager()

    # Then: its public string contract remains characterized before integration
    assert result == expected


def test_detect_launchd(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a graphical macOS host with both optional binaries and healthy Infisical
    paths = {"openclaw": "/opt/homebrew/bin/openclaw", "docker": "/usr/local/bin/docker"}
    monkeypatch.setattr(shutil, "which", mock.Mock(side_effect=paths.get))
    monkeypatch.setattr(capabilities, "detect_service_manager", mock.Mock(return_value="launchd"))
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(httpx, "get", mock.Mock(return_value=httpx.Response(200)))

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: every documented field reflects the mocked macOS environment
    assert result == Capabilities(
        openclaw_installed=True,
        openclaw_path="/opt/homebrew/bin/openclaw",
        docker_available=True,
        service_manager="launchd",
        display_available=True,
        infisical_running=True,
        python_version="3.12.13",
    )


def test_no_service_manager() -> None:
    # Given: the shared service detector reports no supported manager
    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: the literal is preserved for downstream prompt routing
    assert result.service_manager == "none"


def test_windows_service_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the shared detector reports Windows Task Scheduler semantics
    monkeypatch.setattr(capabilities, "detect_service_manager", mock.Mock(return_value="windows"))

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: the exact supported literal is retained
    assert result.service_manager == "windows"


def test_unknown_service_manager_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: an unexpected future value escapes the legacy string return type
    monkeypatch.setattr(capabilities, "detect_service_manager", mock.Mock(return_value="unknown"))

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: the typed deploy boundary narrows it to the safe no-manager state
    assert result.service_manager == "none"


def test_openclaw_and_docker_paths_use_which(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: executable discovery returns one path and one miss
    which = mock.Mock(side_effect=["/usr/bin/openclaw", None])
    monkeypatch.setattr(shutil, "which", which)

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: paths are observed only through shutil.which
    assert result.openclaw_installed is True
    assert result.openclaw_path == "/usr/bin/openclaw"
    assert result.docker_available is False
    assert which.call_args_list == [mock.call("openclaw"), mock.call("docker")]


def test_display_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: DISPLAY contains a non-empty server identifier
    monkeypatch.setenv("DISPLAY", ":99")

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: GUI capability is available
    assert result.display_available is True


def test_display_absent_or_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: DISPLAY follows os.environ.get semantics with an empty value
    monkeypatch.setenv("DISPLAY", "")

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: GUI capability is unavailable
    assert result.display_available is False


def test_infisical_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the local Infisical endpoint returns HTTP 200
    monkeypatch.setattr(httpx, "get", mock.Mock(return_value=httpx.Response(200)))

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: Infisical is reported running
    assert result.infisical_running is True


def test_infisical_probe_uses_status_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a mocked healthy local Infisical server
    get = mock.Mock(return_value=httpx.Response(200))
    monkeypatch.setattr(httpx, "get", get)

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: the first-party health endpoint is probed with the existing bound
    assert result.infisical_running is True
    get.assert_called_once_with(
        "http://localhost:8080/api/status",
        timeout=1.0,
        trust_env=False,
    )


def test_infisical_probe_accepts_configured_local_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: deployment selected a distinct loopback Infisical origin.
    get = mock.Mock(return_value=httpx.Response(200))
    monkeypatch.setattr(httpx, "get", get)

    # When: the shared capability seam probes that origin.
    healthy = infisical_is_running("http://127.0.0.1:9080")

    # Then: it uses the canonical status path with the same proxy-safe timeout contract.
    assert healthy is True
    get.assert_called_once_with(
        "http://127.0.0.1:9080/api/status",
        timeout=1.0,
        trust_env=False,
    )


def test_infisical_probe_rejects_remote_origin_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a direct lower-level caller supplies a remote origin.
    get = mock.Mock()
    monkeypatch.setattr(httpx, "get", get)

    # When/Then: parsing fails before any network observation.
    with pytest.raises(DeployBoundaryError):
        _ = infisical_is_running("http://remote.example:8080")
    get.assert_not_called()


def test_infisical_probe_ignores_hostile_proxy_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: every supported proxy variable attempts to reroute local HTTP
    proxy_url = "http://proxy.invalid:3128"
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(variable, proxy_url)
    get = mock.Mock(return_value=httpx.Response(200))
    monkeypatch.setattr(httpx, "get", get)

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: the request disables environment routing without mutating the environment
    assert result.infisical_running is True
    get.assert_called_once_with(
        "http://localhost:8080/api/status",
        timeout=1.0,
        trust_env=False,
    )
    proxy_variables = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    assert all(os.environ[variable] == proxy_url for variable in proxy_variables)


def test_infisical_unhealthy_status_ignores_misleading_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the local endpoint claims health in its body but returns a failure status
    response = httpx.Response(503, text="healthy")
    monkeypatch.setattr(httpx, "get", mock.Mock(return_value=response))

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: HTTP status wins and detection fails closed
    assert result.infisical_running is False


def test_infisical_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: no process accepts the local Infisical connection
    request = httpx.Request("GET", "http://localhost:8080")
    get = mock.Mock(side_effect=httpx.ConnectError("refused", request=request))
    monkeypatch.setattr(httpx, "get", get)

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: connection failure is represented as unavailable
    assert result.infisical_running is False


def test_infisical_http_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the local endpoint exceeds the client's time budget
    request = httpx.Request("GET", "http://localhost:8080")
    get = mock.Mock(side_effect=httpx.ReadTimeout("timed out", request=request))
    monkeypatch.setattr(httpx, "get", get)

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: timeout failure is closed and the call has a short explicit bound
    assert result.infisical_running is False
    get.assert_called_once_with(
        "http://localhost:8080/api/status",
        timeout=1.0,
        trust_env=False,
    )


def test_python_version_uses_runtime_value(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the runtime reports a distinct supported Python version
    monkeypatch.setattr(platform, "python_version", mock.Mock(return_value="3.13.2"))

    # When: deployment capabilities are detected
    result = detect_capabilities()

    # Then: the exact runtime version is exposed
    assert result.python_version == "3.13.2"


def test_capabilities_are_immutable() -> None:
    # Given: a detected capability snapshot
    result = detect_capabilities()

    # When/Then: callers cannot mutate observations after routing decisions
    with pytest.raises(FrozenInstanceError):
        setattr(result, "service_manager", "systemd")

"""Infisical usability and lifecycle regressions for Todo-6 deploy."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import TypedDict

import pytest
from infisical_sdk.infisical_requests import APIError
from pydantic import SecretStr

import traderbot.secrets.resolver as resolver
from traderbot.deploy.secret_step import select_deploy_secrets
from traderbot.deploy.validation import DeployBoundaryError
from traderbot.secrets.resolver import SecretsBackendName
from traderbot.secrets.store import SecretsStore

_PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


class _Auth:
    class Universal:
        def login(self, client_id: str, client_secret: str) -> None:
            assert client_id
            assert client_secret

    universal_auth = Universal()


class _SecretList:
    secrets: tuple[()] = ()


class _ListCall(TypedDict):
    environment_slug: str
    secret_path: str
    project_slug: str
    view_secret_value: bool


class _ConstructorCall(TypedDict):
    host: str
    cache_ttl: int | None


class _Secrets:
    def __init__(self, *, denied: bool) -> None:
        self.denied = denied
        self.list_calls: list[_ListCall] = []

    def list_secrets(
        self,
        *,
        environment_slug: str,
        secret_path: str,
        project_slug: str,
        view_secret_value: bool,
    ) -> _SecretList:
        self.list_calls.append(
            {
                "environment_slug": environment_slug,
                "secret_path": secret_path,
                "project_slug": project_slug,
                "view_secret_value": view_secret_value,
            }
        )
        if self.denied:
            raise APIError("denied", 403, {})
        return _SecretList()


class _ClientCloseTypeError(TypeError):
    pass


class _Client:
    def __init__(self, *, denied: bool, close_error: SecretStr | None = None) -> None:
        self.auth = _Auth()
        self.secrets = _Secrets(denied=denied)
        self.closed = False
        self.close_calls = 0
        self._close_error: SecretStr | None = close_error

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True
        if self._close_error is not None:
            raise _ClientCloseTypeError(self._close_error.get_secret_value())


def _credentials(data_root: Path) -> None:
    data_root.mkdir()
    document = {
        "host": "http://localhost:8080",
        "machineIdentity": {
            "clientId": secrets.token_urlsafe(),
            "clientSecret": secrets.token_urlsafe(),
        },
    }
    _ = (data_root / "infisical-credentials.json").write_text(
        json.dumps(document),
        encoding="utf-8",
    )


def _clear_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PROXY_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("proxy_name", _PROXY_NAMES)
def test_proxy_environment_refuses_sdk_without_mutating_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    proxy_name: str,
) -> None:
    # Given: valid credentials and any nonempty proxy variant.
    data_root = tmp_path / "data"
    _credentials(data_root)
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_root))
    _clear_proxies(monkeypatch)
    proxy = "http://proxy.invalid:3128"
    monkeypatch.setenv(proxy_name, proxy)
    constructed = False

    def construct(*, host: str, cache_ttl: int | None) -> _Client:
        nonlocal constructed
        del host, cache_ttl
        constructed = True
        return _Client(denied=False)

    monkeypatch.setattr(resolver, "InfisicalSDKClient", construct)

    # When: backend selection evaluates SDK safety.
    _, backend = resolver.build_secrets_store_selection()

    # Then: encrypted local fallback is honest and environment state is untouched.
    assert backend == "local-encrypted"
    assert constructed is False
    assert os.environ[proxy_name] == proxy


def test_resolver_rejects_remote_override_before_backend_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a direct lower-level caller supplies a remote override.
    def fail_construct(*, host: str, cache_ttl: int | None) -> _Client:
        del host, cache_ttl
        pytest.fail("SDK must not be constructed")

    monkeypatch.setattr(resolver, "InfisicalSDKClient", fail_construct)

    # When/Then: the resolver rejects it before SDK or local state construction.
    with pytest.raises(DeployBoundaryError):
        _ = resolver.build_secrets_store_selection("http://remote.example:8080")


def test_login_success_with_project_denial_closes_and_falls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: login succeeds but non-value project access is denied.
    data_root = tmp_path / "data"
    _credentials(data_root)
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_root))
    _clear_proxies(monkeypatch)
    client = _Client(denied=True)

    def construct(*, host: str, cache_ttl: int | None) -> _Client:
        del host, cache_ttl
        return client

    monkeypatch.setattr(resolver, "InfisicalSDKClient", construct)

    # When: deploy sees a healthy status endpoint.
    selection = select_deploy_secrets(
        "http://localhost:8080",
        status_probe=lambda _url: True,
        local_path=data_root / "secrets",
    )

    # Then: denial is closed, abandoned, and reported as encrypted local fallback.
    assert selection.backend == "local-encrypted"
    assert client.closed is True
    assert len(client.secrets.list_calls) == 1


def test_denied_client_close_fault_cannot_block_or_taint_local_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given: denied project access and a close fault carrying protected input.
    data_root = tmp_path / "data"
    _credentials(data_root)
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_root))
    _clear_proxies(monkeypatch)
    protected = SecretStr(secrets.token_urlsafe())
    client = _Client(denied=True, close_error=protected)

    def construct(*, host: str, cache_ttl: int | None) -> _Client:
        del host, cache_ttl
        return client

    monkeypatch.setattr(resolver, "InfisicalSDKClient", construct)
    selection: tuple[SecretsStore, SecretsBackendName] | None = None
    escaped: TypeError | None = None

    # When: selection contains both the access denial and close fault.
    try:
        selection = resolver.build_secrets_store_selection()
    except TypeError as exc:
        escaped = exc

    # Then: fallback is selected, does not own the client, and exposes no protected input.
    protected_text = protected.get_secret_value()
    rendered = (repr(selection), repr(escaped), caplog.text)
    leak_count = sum(protected_text in surface for surface in rendered)
    assert leak_count == 0
    assert escaped is None
    assert selection is not None
    store, backend = selection
    assert backend == "local-encrypted"
    assert client.close_calls == 1
    resolver.close_secrets_store(store)
    assert client.close_calls == 1


def test_access_success_checks_required_targets_without_values_and_disables_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: credentials and a fake client with all required project access.
    data_root = tmp_path / "data"
    _credentials(data_root)
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_root))
    _clear_proxies(monkeypatch)
    client = _Client(denied=False)
    constructor_calls: list[_ConstructorCall] = []

    def construct(*, host: str, cache_ttl: int | None) -> _Client:
        constructor_calls.append({"host": host, "cache_ttl": cache_ttl})
        return client

    monkeypatch.setattr(resolver, "InfisicalSDKClient", construct)

    # When: resolver declares Infisical usable.
    store, backend = resolver.build_secrets_store_selection()

    # Then: cache is disabled and both namespaces are checked without values.
    assert backend == "infisical"
    assert constructor_calls == [{"host": "http://localhost:8080", "cache_ttl": None}]
    assert client.secrets.list_calls == [
        {
            "environment_slug": "prod",
            "secret_path": "/",
            "project_slug": "traderbot",
            "view_secret_value": False,
        },
        {
            "environment_slug": "prod",
            "secret_path": "/",
            "project_slug": "traderbot-agent-tokens",
            "view_secret_value": False,
        },
    ]
    resolver.close_secrets_store(store)
    assert client.closed is True

"""Tests for the OpenClaw -> Infisical exec-provider resolver script.

The script at ``scripts/openclaw-infisical-resolver`` is loaded in-process
(extensionless, executed via ``SourceFileLoader``) and driven through its real
stdin/stdout surface. The Infisical SDK client is replaced with a fake so no
network or real Infisical is required; the fake records every SDK call so the
routing contract (``_token`` -> Agent Tokens project, otherwise -> TraderBot
project) and the ``cache_ttl=None`` construction are asserted on observable
arguments, not on mocked return values.

Run with: pytest tests/test_infisical_resolver_script.py -v
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "openclaw-infisical-resolver"

_loader = SourceFileLoader("openclaw_infisical_resolver", str(SCRIPT_PATH))
assert _loader is not None
_spec = importlib.util.spec_from_loader("openclaw_infisical_resolver", _loader)
assert _spec is not None
resolver = importlib.util.module_from_spec(_spec)
_loader.exec_module(resolver)


class _SecretNotFound(Exception):
    """Raised by the fake when a secret id has no configured value."""


class FakeSecretResult:
    """Minimal ``get_secret_by_name`` result (structural match)."""

    def __init__(self, value: str | None) -> None:
        self.secretValue = value


class FakeSecrets:
    """Recorded-call fake for ``client.secrets`` (the SDK resource)."""

    def __init__(self, secrets: dict[str, str | None]) -> None:
        self._secrets = secrets
        self.calls: list[dict[str, Any]] = []

    def get_secret_by_name(self, **kwargs: Any) -> FakeSecretResult:
        self.calls.append(kwargs)
        secret_id = kwargs["secret_name"]
        if secret_id not in self._secrets:
            raise _SecretNotFound(secret_id)
        return FakeSecretResult(self._secrets[secret_id])


class FakeClient:
    """Fake SDK client exposing ``.secrets`` (matches the real SDK shape)."""

    def __init__(self, secrets: dict[str, str | None]) -> None:
        self.secrets = FakeSecrets(secrets)


class FakeClientFactory:
    """Stand-in for :class:`InfisicalSDKClient`; records constructor args."""

    def __init__(self, secrets: dict[str, str | None]) -> None:
        self._secrets = secrets
        self.construct_args: list[dict[str, Any]] = []
        self.clients: list[FakeClient] = []

    def __call__(self, **kwargs: Any) -> FakeClient:
        self.construct_args.append(kwargs)
        client = FakeClient(self._secrets)
        self.clients.append(client)
        return client


class _UnreachableSecrets:
    """Fake whose SDK calls fail with a transport-level error."""

    def get_secret_by_name(self, **kwargs: Any) -> FakeSecretResult:
        raise ConnectionError("Infisical unreachable")


class _UnreachableClient:
    """Fake SDK client whose secrets resource always fails."""

    def __init__(self) -> None:
        self.secrets = _UnreachableSecrets()


class _UnreachableFactory:
    """Client factory that always yields transport-failing SDK calls."""

    def __call__(self, **kwargs: Any) -> _UnreachableClient:
        return _UnreachableClient()


CREDENTIALS = {
    "host": "https://infisical.example.com",
    "projectId": "traderbot-project-id",
    "agentTokensProjectId": "agent-tokens-project-id",
}

REQUEST = {"protocolVersion": 1, "provider": "infisical", "ids": ["weather_token"]}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request_json: str,
    *,
    credentials: dict[str, str] | None = CREDENTIALS,
    env: dict[str, str] | None = None,
    factory: Any | None = None,
) -> tuple[str, int | None]:
    """Drive ``resolver.main()`` with a fake stdin/stdout.

    Returns ``(stdout_text, exit_code)``; exit code is ``None`` on a clean
    return and an int when the script exits via ``sys.exit``.
    """
    creds_path = tmp_path / "infisical-credentials.json"
    if credentials is not None:
        creds_path.write_text(json.dumps(credentials), encoding="utf-8")
    monkeypatch.setattr(resolver, "CREDENTIALS_PATH", creds_path)
    for var in ("INFISICAL_TOKEN", "INFISICAL_DOMAIN"):
        monkeypatch.delenv(var, raising=False)
    if env:
        for var, value in env.items():
            monkeypatch.setenv(var, value)
    if factory is not None:
        monkeypatch.setattr(resolver, "InfisicalSDKClient", factory)
    monkeypatch.setattr(sys, "stdin", io.StringIO(request_json))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    try:
        resolver.main()
    except SystemExit as exc:
        # The script only ever exits with an int status (sys.exit(1)); a
        # str/none code would be a contract violation worth surfacing.
        assert isinstance(exc.code, int)
        return stdout.getvalue(), exc.code
    return stdout.getvalue(), None


def _parse(response: str) -> dict[str, Any]:
    return json.loads(response)


class TestValidResolution:
    def test_valid_stdin_returns_values(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "values": {"weather_token": "tok-123"},
        }

    def test_multiple_ids_all_resolved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory(
            {"weather_token": "tok-123", "kalshi_api_key": "key-abc"}
        )
        request = {"protocolVersion": 1, "provider": "infisical",
                   "ids": ["weather_token", "kalshi_api_key"]}
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(request),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "values": {"weather_token": "tok-123", "kalshi_api_key": "key-abc"},
        }


class TestFailClosed:
    def test_missing_token_returns_per_id_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "errors": {"weather_token": "Not found"},
        }

    def test_missing_domain_returns_per_id_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t"},
            factory=factory,
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "errors": {"weather_token": "Not found"},
        }

    def test_missing_credentials_file_returns_per_id_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            credentials=None,
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "errors": {"weather_token": "Not found"},
        }

    def test_unreachable_infisical_returns_per_id_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=_UnreachableFactory(),
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "errors": {"weather_token": "Not found"},
        }

    def test_non_string_secret_value_is_per_id_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": None})
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "errors": {"weather_token": "Not found"},
        }


class TestMalformedStdin:
    def test_non_json_stdin_exits_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out, code = _run(
            monkeypatch,
            tmp_path,
            "this is not json",
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
        )
        assert code == 1
        assert out == ""

    def test_missing_ids_field_exits_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps({"protocolVersion": 1, "provider": "infisical"}),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
        )
        assert code == 1
        assert out == ""

    def test_unknown_extra_field_exits_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps({"protocolVersion": 1, "provider": "infisical",
                        "ids": [], "bogus": True}),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
        )
        assert code == 1
        assert out == ""


class TestRouting:
    def test_token_suffix_routes_to_agent_tokens_project(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory(
            {"weather_token": "tok-123", "kalshi_api_key": "key-abc"}
        )
        request = {"protocolVersion": 1, "provider": "infisical",
                   "ids": ["weather_token", "kalshi_api_key"]}
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(request),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        assert code is None
        assert _parse(out)["values"] == {
            "weather_token": "tok-123",
            "kalshi_api_key": "key-abc",
        }
        recorded = [
            (call["secret_name"], call["project_id"])
            for call in factory.clients[0].secrets.calls
        ]
        assert recorded == [
            ("weather_token", CREDENTIALS["agentTokensProjectId"]),
            ("kalshi_api_key", CREDENTIALS["projectId"]),
        ]

    def test_environment_slug_and_secret_path_are_prod_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        call = factory.clients[0].secrets.calls[0]
        assert call["environment_slug"] == "prod"
        assert call["secret_path"] == "/"
        assert call["view_secret_value"] is True


class TestSdkConstruction:
    def test_client_built_with_cache_ttl_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        _run(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "secret-token", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        args = factory.construct_args[0]
        assert args == {
            "host": "https://x",
            "token": "secret-token",
            "cache_ttl": None,
        }


class TestPartialFailure:
    def test_partial_failure_some_values_some_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        request = {"protocolVersion": 1, "provider": "infisical",
                   "ids": ["weather_token", "missing_secret"]}
        out, code = _run(
            monkeypatch,
            tmp_path,
            json.dumps(request),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )
        assert code is None
        assert _parse(out) == {
            "protocolVersion": 1,
            "values": {"weather_token": "tok-123"},
            "errors": {"missing_secret": "Not found"},
        }

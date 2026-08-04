"""Integration tests for the full secrets store stack (DD-037, Phase 1.5).

Drives the complete chain — SecretsResolver → TokenStoreAdapter →
SecretsStore → (Infisical | local encrypted) — plus rotation, the OpenClaw
exec-provider wrapper protocol, local→Infisical migration, suspended-profile
enforcement, and the with-plugin.json config contract. Every Infisical SDK
call is mocked/faked; no real Infisical connection is required.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tests.test_infisical_resolver_script import FakeClientFactory
from tests.test_secrets_resolver import _FakeAuth
from tests.test_secrets_store import FakeInfisicalClient, FakeSecretsClient
from tests.test_with_plugin_config import load_with_plugin_config
from traderbot.mcp.resolver import _SUSPENDED_PROFILES, resolve_token_adapter
from traderbot.profiles.tokens import LocalTokenStore, get_store, set_store
from traderbot.secrets.adapter import TokenStoreAdapter
from traderbot.secrets.migrate import migrate_local_to_infisical
from traderbot.secrets.resolver import SecretsResolver
from traderbot.secrets.rotation import TokenRotationManager
from traderbot.secrets.store import SecretsStore

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "openclaw-infisical-resolver"

_loader = SourceFileLoader("openclaw_infisical_resolver_integration", str(SCRIPT_PATH))
assert _loader is not None
_spec = importlib.util.spec_from_loader("openclaw_infisical_resolver_integration", _loader)
assert _spec is not None
wrapper = importlib.util.module_from_spec(_spec)
_loader.exec_module(wrapper)

CREDENTIALS = {
    "host": "https://infisical.example.com",
    "projectId": "traderbot-project-id",
    "agentTokensProjectId": "agent-tokens-project-id",
}
REQUEST = {"protocolVersion": 1, "provider": "infisical", "ids": ["weather_token"]}


class _FakeSdkClient:
    """Fake InfisicalSDKClient exposing both ``auth`` and ``secrets`` resources."""

    def __init__(self) -> None:
        self.auth: _FakeAuth = _FakeAuth()
        self.secrets: FakeSecretsClient = FakeSecretsClient()


def _credentials_at(home: Path) -> Path:
    """Write an infisical-credentials.json under ``home`` and return its path."""
    creds_dir = home / ".traderbot"
    creds_dir.mkdir(parents=True)
    creds_path = creds_dir / "infisical-credentials.json"
    _ = creds_path.write_text(
        '{"host": "http://localhost:8080", '
        + '"machineIdentity": {"clientId": "cid-1", "clientSecret": "cs-1"}}'
    )
    return creds_path


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch, created: list[_FakeSdkClient]) -> None:
    """Replace ``InfisicalSDKClient.__init__`` with a fake that records instances."""
    from infisical_sdk import InfisicalSDKClient

    def fake_init(
        self: object, host: str, token: str | None = None, cache_ttl: int = 60
    ) -> None:
        del token, cache_ttl
        fake = _FakeSdkClient()
        created.append(fake)
        setattr(self, "auth", fake.auth)
        setattr(self, "secrets", fake.secrets)

    monkeypatch.setattr(InfisicalSDKClient, "__init__", fake_init)


def _run_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request_json: str,
    *,
    credentials: dict[str, str] | None = CREDENTIALS,
    env: dict[str, str] | None = None,
    factory: Any | None = None,
) -> tuple[str, int | None]:
    """Drive the wrapper script with fake stdin/stdout; return (stdout, exit_code)."""
    creds_path = tmp_path / "infisical-credentials.json"
    if credentials is not None:
        _ = creds_path.write_text(json.dumps(credentials), encoding="utf-8")
    monkeypatch.setattr(wrapper, "CREDENTIALS_PATH", creds_path)
    for var in ("INFISICAL_TOKEN", "INFISICAL_DOMAIN"):
        monkeypatch.delenv(var, raising=False)
    if env:
        for var, value in env.items():
            monkeypatch.setenv(var, value)
    if factory is not None:
        monkeypatch.setattr(wrapper, "InfisicalSDKClient", factory)
    monkeypatch.setattr(sys, "stdin", io.StringIO(request_json))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    try:
        wrapper.main()
    except SystemExit as exc:
        assert isinstance(exc.code, int)
        return stdout.getvalue(), exc.code
    return stdout.getvalue(), None


class TestResolverWithInfisical:
    def test_tokens_resolve_through_adapter_to_infisical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _ = _credentials_at(tmp_path)
        created: list[_FakeSdkClient] = []
        _install_fake_sdk(monkeypatch, created)
        try:
            _ = SecretsResolver()
            adapter = get_store()
            assert isinstance(adapter, TokenStoreAdapter)

            adapter.store_token("weather", "weather-agent", "tok-1")

            assert adapter.resolve_token("tok-1") == ("weather", "weather-agent")
            create_calls = [c for c in created[0].secrets.calls if c[0] == "create"]
            assert create_calls[0][1]["secret_name"] == "weather-agent_token"
            assert create_calls[0][1]["project_slug"] == "traderbot-agent-tokens"
            assert create_calls[0][1]["environment_slug"] == "prod"
        finally:
            set_store(None)


class TestResolverLocalFallback:
    def test_no_credentials_stores_and_resolves_locally(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        try:
            _ = SecretsResolver()
            adapter = get_store()
            assert isinstance(adapter, TokenStoreAdapter)

            adapter.store_token("weather", "weather-agent", "local-tok")

            assert adapter.resolve_token("local-tok") == ("weather", "weather-agent")
            secrets_file = tmp_path / ".traderbot" / "secrets" / "secrets.json"
            assert secrets_file.exists()
        finally:
            set_store(None)


class TestRotationE2E:
    def test_rotate_all_old_tokens_fail_new_tokens_work(self) -> None:
        client = FakeInfisicalClient()
        store = SecretsStore(infisical_client=client)
        store.store_profile_token(
            agent_id="weather",
            token="old-weather",
            profile="weather",
            categories=["weather"],
            permissions=["market_edge"],
        )
        store.store_profile_token(
            agent_id="sysadmin",
            token="old-sys",
            profile="sysadmin",
            categories=[],
            permissions=[],
        )
        manager = TokenRotationManager(store)

        with patch("traderbot.secrets.rotation.time.time", return_value=1_000_000.0):
            rotated = manager.rotate_all()

        assert set(rotated) == {"weather", "sysadmin"}
        assert store.resolve_profile_token("old-weather") is None
        assert store.resolve_profile_token("old-sys") is None
        assert store.resolve_profile_token(rotated["weather"]) == ("weather", "weather")
        assert store.resolve_profile_token(rotated["sysadmin"]) == ("sysadmin", "sysadmin")

    def test_mock_time_advances_staleness(self) -> None:
        client = FakeInfisicalClient()
        store = SecretsStore(infisical_client=client)
        store.store_profile_token(
            agent_id="weather",
            token="old-weather",
            profile="weather",
            categories=["weather"],
            permissions=["market_edge"],
        )
        manager = TokenRotationManager(store)
        base = 1_000_000.0

        with patch("traderbot.secrets.rotation.time.time", return_value=base):
            _ = manager.rotate_all()
        with patch("traderbot.secrets.rotation.time.time", return_value=base + 2 * 3600.0):
            staleness = manager.get_staleness()

        assert staleness["weather"] == pytest.approx(2.0, abs=0.01)


class TestPluginExecProtocol:
    def test_send_ids_get_values_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({"weather_token": "tok-123"})
        out, code = _run_wrapper(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )

        assert code is None
        assert json.loads(out) == {
            "protocolVersion": 1,
            "values": {"weather_token": "tok-123"},
        }

    def test_missing_secret_returns_errors_map(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        factory = FakeClientFactory({})
        out, code = _run_wrapper(
            monkeypatch,
            tmp_path,
            json.dumps(REQUEST),
            env={"INFISICAL_TOKEN": "t", "INFISICAL_DOMAIN": "https://x"},
            factory=factory,
        )

        assert code is None
        assert json.loads(out) == {
            "protocolVersion": 1,
            "errors": {"weather_token": "Not found"},
        }


class TestMigrationE2E:
    def test_tokens_appear_in_store(self, tmp_path: Path) -> None:
        client = FakeInfisicalClient()
        store = SecretsStore(infisical_client=client)
        tokens_path = tmp_path / "tokens.json"
        _ = tokens_path.write_text(
            json.dumps(
                {"tokens": {"tok-weather": {"profile": "weather", "agent_id": "weather"}}}
            ),
            encoding="utf-8",
        )

        count = migrate_local_to_infisical(store=store, tokens_path=tokens_path)

        assert count == 1
        entry = store.get_profile_token("weather")
        assert entry is not None
        assert entry["token"] == "tok-weather"
        assert entry["profile"] == "weather"
        assert entry["agent_id"] == "weather"

    def test_original_file_preserved(self, tmp_path: Path) -> None:
        client = FakeInfisicalClient()
        store = SecretsStore(infisical_client=client)
        tokens_path = tmp_path / "tokens.json"
        _ = tokens_path.write_text(
            json.dumps(
                {"tokens": {"tok-weather": {"profile": "weather", "agent_id": "weather"}}}
            ),
            encoding="utf-8",
        )
        original = tokens_path.read_bytes()

        _ = migrate_local_to_infisical(store=store, tokens_path=tokens_path)

        assert tokens_path.exists()
        assert tokens_path.read_bytes() == original


class TestSuspendedProfiles:
    @pytest.fixture(autouse=True)
    def _env_real_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")

    def test_suspended_profile_returns_none_none(
        self, secrets_resolver_reset: None, real_auth: LocalTokenStore
    ) -> None:
        real_auth.store_token("weather", "weather-agent", "suspend-me")
        _SUSPENDED_PROFILES.add("weather")

        assert resolve_token_adapter("suspend-me") == (None, None)


class TestWithPluginConfig:
    def test_infisical_provider_present(self) -> None:
        providers = load_with_plugin_config().secrets.providers

        assert providers.model_fields_set == {"infisical"}
        provider = providers.infisical
        assert provider.type == "exec"
        assert provider.command == "/usr/local/bin/openclaw-infisical-resolver"
        assert provider.jsonOnly is True
        assert set(provider.passEnv) == {"INFISICAL_TOKEN", "INFISICAL_DOMAIN"}

    def test_agent_token_map_uses_exec_infisical_ids(self) -> None:
        token_map = (
            load_with_plugin_config()
            .plugins.entries.traderbot_token_injector.config.agentTokenMap
        )

        assert set(token_map) == {"weather", "sysadmin", "dev-liaison"}
        for agent_id, secret_ref in token_map.items():
            assert secret_ref.source == "exec"
            assert secret_ref.provider == "infisical"
            assert secret_ref.id == f"{agent_id}_token"

    def test_mcp_server_env_enables_real_auth(self) -> None:
        server = load_with_plugin_config().mcp.servers.traderbot

        assert server.env == {"TRADERBOT_USE_HARDCODED_AUTH": "0"}

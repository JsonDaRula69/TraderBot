from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, final, override

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

import traderbot.deploy.backfill_command as backfill_command
import traderbot.deploy.verify_command as verify_command
import traderbot.deploy.verify_ports as verify_ports
from tests.test_deploy_provider_security import build_and_install_wheel
from traderbot.cli import main
from traderbot.deploy.backfill import BackfillRequest
from traderbot.deploy.backfill_command import (
    BackfillCommandOptions,
    BackfillRuntimeFactories,
    execute_backfill,
)
from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.backfill_ports import BackfillDependencies, BackfillRuntime
from traderbot.deploy.secret_step import KalshiSecretPair, SecretPairValidationError
from traderbot.deploy.verify import VerificationPorts
from traderbot.deploy.verify_command import VerificationCommandOptions, execute_verification
from traderbot.deploy.verify_models import (
    CheckId,
    CheckResult,
    CheckStatus,
    OverallStatus,
    ProbeResult,
    TokenProbe,
    VerificationRequest,
    VerificationResult,
)
from traderbot.deploy.verify_ports import ProductionVerificationPorts
from traderbot.kalshi.client import Environment, KalshiClient
from traderbot.kalshi.order_models import MarketCategory
from traderbot.secrets.resolver import build_secrets_store
from traderbot.secrets.store import SecretsStore


@final
class UnusedBackfillDependencies:
    default_collector_path: Path = Path("/missing")

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 8, 19, tzinfo=UTC)

    def open_runtime(self, environment: str) -> AbstractAsyncContextManager[BackfillRuntime]:
        raise AssertionError(f"runtime must not open during request capture: {environment}")


class UnusedVerificationPorts(VerificationPorts):
    @override
    async def tokens(self) -> TokenProbe:
        raise AssertionError("tokens must not run during request capture")

    @override
    async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult:
        raise AssertionError(f"probe must not run during request capture: {check_id}, {token}")


def _verification_options(
    environment: Environment = "production",
) -> VerificationCommandOptions:
    return VerificationCommandOptions.model_validate(
        {
            "categories": (MarketCategory.WEATHER,),
            "mode": "backtest",
            "environment": environment,
            "infisical_origin": "http://localhost:8080",
            "daemon_mcp_url": "http://127.0.0.1:8765/mcp",
            "timeout_seconds": 0.5,
            "json_output": True,
        }
    )


def _passing_verification() -> VerificationResult:
    return VerificationResult(
        overall=OverallStatus.OK,
        checks=tuple(
            CheckResult(
                id=check_id,
                status=CheckStatus.PASS,
                required=True,
                action="captured",
                message="Captured",
                elapsed_ms=0,
            )
            for check_id in CheckId
        ),
    )


def test_backfill_omitted_environment_builds_production_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[str] = []

    async def capture(
        request: BackfillRequest, dependencies: BackfillDependencies
    ) -> BackfillResult:
        del dependencies
        observed.append(request.kalshi_environment)
        return BackfillResult(status="complete")

    monkeypatch.setattr(backfill_command, "run_backfill", capture)

    code = execute_backfill(
        BackfillCommandOptions(months=6, json_output=True, target_db=tmp_path / "unused.db"),
        cast(BackfillDependencies, UnusedBackfillDependencies()),
    )

    assert code == 0
    assert observed == ["production"]
    assert not (tmp_path / "unused.db").exists()


def test_verify_omitted_environment_builds_production_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    async def capture(request: VerificationRequest, ports: VerificationPorts) -> VerificationResult:
        del ports
        observed.append(request.kalshi_environment)
        return _passing_verification()

    monkeypatch.setattr(verify_command, "run_verification", capture)

    code = execute_verification(_verification_options(), UnusedVerificationPorts())

    assert code == 0
    assert observed == ["production"]


@pytest.mark.parametrize("environment", ["production", "demo"])
def test_backfill_explicit_environment_builds_typed_request(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[Environment] = []

    async def capture(
        request: BackfillRequest, dependencies: BackfillDependencies
    ) -> BackfillResult:
        del dependencies
        observed.append(request.kalshi_environment)
        return BackfillResult(status="complete")

    monkeypatch.setattr(backfill_command, "run_backfill", capture)

    code = execute_backfill(
        BackfillCommandOptions(
            months=6,
            environment=environment,
            json_output=True,
            target_db=tmp_path / "unused.db",
        ),
        cast(BackfillDependencies, UnusedBackfillDependencies()),
    )

    assert code == 0
    assert observed == [environment]
    assert not (tmp_path / "unused.db").exists()


@pytest.mark.parametrize("environment", ["production", "demo"])
def test_verify_explicit_environment_builds_typed_request(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Environment] = []

    async def capture(request: VerificationRequest, ports: VerificationPorts) -> VerificationResult:
        del ports
        observed.append(request.kalshi_environment)
        return _passing_verification()

    monkeypatch.setattr(verify_command, "run_verification", capture)

    code = execute_verification(_verification_options(environment), UnusedVerificationPorts())

    assert code == 0
    assert observed == [environment]


@pytest.mark.parametrize("command", ["backfill", "verify"])
@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ([], "production"),
        (["--environment", "production"], "production"),
        (["--environment", "demo"], "demo"),
    ],
)
def test_standalone_cli_selects_environment(
    command: str,
    option: list[str],
    expected: Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Environment] = []

    def capture(arguments: argparse.Namespace) -> int:
        observed.append(cast(Environment, arguments.environment))
        return 0

    monkeypatch.setattr(f"traderbot.cli._cmd_{command}", capture)
    arguments = [command, *option]
    if command == "verify":
        arguments.extend(("--categories", "weather"))

    code = main(arguments)

    assert code == 0
    assert observed == [expected]


@pytest.mark.parametrize("command", ["backfill", "verify"])
def test_invalid_environment_exits_two_before_handler_or_file_write(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "must-not-exist"
    called = False

    def capture(_arguments: argparse.Namespace) -> int:
        nonlocal called
        called = True
        _ = marker.write_text("mutated", encoding="utf-8")
        return 0

    monkeypatch.setattr(f"traderbot.cli._cmd_{command}", capture)
    arguments = [command, "--environment", "invalid", "--json"]
    if command == "verify":
        arguments.extend(("--categories", "weather"))

    code = main(arguments)

    assert code == 2
    assert not called
    assert not marker.exists()


@pytest.mark.parametrize("command", ["backfill", "verify"])
def test_standalone_help_documents_environment(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        _ = main([command, "--help"])

    output = capsys.readouterr().out
    assert error.value.code == 0
    assert "--environment {production,demo}" in output
    assert "default: production" in output


def _secret_pair() -> KalshiSecretPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return KalshiSecretPair.from_plain("test-api-key", pem)


class CredentialBackend:
    def __init__(self, values: dict[tuple[str, str], str]) -> None:
        self.values: dict[tuple[str, str], str] = values
        self.get_calls: list[tuple[str, str]] = []

    def get(self, *, service: str, key: str, namespace: str) -> str | None:
        del namespace
        self.get_calls.append((service, key))
        return self.values.get((service, key))

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None:
        del namespace
        self.values[(service, key)] = value

    def delete(self, *, service: str, key: str, namespace: str) -> None:
        del namespace
        del self.values[(service, key)]

    def get_namespace(self, namespace: str) -> dict[str, str]:
        del namespace
        return {}


@pytest.mark.asyncio
async def test_backfill_demo_reads_only_demo_pair_when_both_pairs_exist() -> None:
    production = _secret_pair()
    demo = _secret_pair()
    backend = CredentialBackend(
        {
            ("kalshi", "api_key"): production.api_key.get_secret_value(),
            ("kalshi", "private_key_pem"): production.private_key_pem.get_secret_value(),
            ("kalshi_demo", "api_key"): demo.api_key.get_secret_value(),
            ("kalshi_demo", "private_key_pem"): demo.private_key_pem.get_secret_value(),
        }
    )
    observed: list[tuple[str, Environment]] = []

    class Client:
        async def close(self) -> None:
            return None

    dependencies = backfill_command.OwnedBackfillDependencies(
        default_collector_path=Path("/missing"),
        factories=BackfillRuntimeFactories(
            store=lambda: SecretsStore(local_store=backend),
            client=lambda pair, environment: (
                observed.append((pair.api_key.get_secret_value(), environment))
                or cast(
                    backfill_command.ManagedKalshiHistoryPort,
                    cast(object, Client()),
                )
            ),
        ),
    )

    async with dependencies.open_runtime("demo"):
        pass

    assert backend.get_calls == [
        ("kalshi_demo", "api_key"),
        ("kalshi_demo", "private_key_pem"),
    ]
    assert observed == [(demo.api_key.get_secret_value(), "demo")]


@pytest.mark.asyncio
async def test_backfill_demo_missing_pair_never_falls_back_or_opens_client() -> None:
    production = _secret_pair()
    backend = CredentialBackend(
        {
            ("kalshi", "api_key"): production.api_key.get_secret_value(),
            ("kalshi", "private_key_pem"): production.private_key_pem.get_secret_value(),
        }
    )
    client_calls = 0

    def client(pair: KalshiSecretPair, environment: Environment) -> object:
        nonlocal client_calls
        client_calls += 1
        return pair, environment

    dependencies = backfill_command.OwnedBackfillDependencies(
        default_collector_path=Path("/missing"),
        factories=BackfillRuntimeFactories(
            store=lambda: SecretsStore(local_store=backend),
            client=cast(
                Callable[
                    [KalshiSecretPair, Environment],
                    backfill_command.ManagedKalshiHistoryPort,
                ],
                client,
            ),
        ),
    )

    with pytest.raises(SecretPairValidationError):
        async with dependencies.open_runtime("demo"):
            pass

    assert backend.get_calls == [
        ("kalshi_demo", "api_key"),
        ("kalshi_demo", "private_key_pem"),
    ]
    assert client_calls == 0


@pytest.mark.asyncio
async def test_standalone_demo_factories_never_construct_production_base_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair = _secret_pair()
    history_client = cast(KalshiClient, BackfillRuntimeFactories().client(pair, "demo"))
    history_base = cast(str, vars(history_client)["_base_url"]) + "/"
    await history_client.close()
    observed: list[tuple[Environment, str]] = []

    backend = CredentialBackend(
        {
            ("kalshi_demo", "api_key"): pair.api_key.get_secret_value(),
            ("kalshi_demo", "private_key_pem"): pair.private_key_pem.get_secret_value(),
        }
    )
    store = SecretsStore(local_store=backend)

    class Client:
        def __init__(self, **values: object) -> None:
            environment = cast(Environment, values["environment"])
            base = {
                "production": "https://external-api.kalshi.com/trade-api/v2/",
                "demo": "https://external-api.demo.kalshi.co/trade-api/v2/",
            }[environment]
            observed.append((environment, base))

        async def get_balance(self, timeout: float) -> None:
            del timeout

        async def close(self) -> None:
            return None

    request = VerificationRequest(
        categories=(MarketCategory.WEATHER,),
        kalshi_environment="demo",
    )
    ports = ProductionVerificationPorts(request)
    monkeypatch.setattr(ports, "_selection", lambda: (store, "local-encrypted"))
    monkeypatch.setattr(verify_ports, "KalshiClient", Client)

    result = await ports.probe(CheckId.KALSHI)

    demo_base = "https://external-api.demo.kalshi.co/trade-api/v2/"
    production_base = "https://external-api.kalshi.com/trade-api/v2/"
    assert result.action == "kalshi_auth_valid"
    assert history_base == demo_base
    assert backend.get_calls == [
        ("kalshi_demo", "api_key"),
        ("kalshi_demo", "private_key_pem"),
    ]
    assert observed == [("demo", demo_base)]
    assert production_base not in [history_base, *(base for _, base in observed)]


@pytest.mark.asyncio
async def test_verify_demo_missing_pair_never_falls_back_or_opens_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = _secret_pair()
    backend = CredentialBackend(
        {
            ("kalshi", "api_key"): production.api_key.get_secret_value(),
            ("kalshi", "private_key_pem"): production.private_key_pem.get_secret_value(),
        }
    )
    client_calls = 0

    class Client:
        def __init__(self, **values: object) -> None:
            nonlocal client_calls
            client_calls += 1
            del values

    ports = ProductionVerificationPorts(
        VerificationRequest(
            categories=(MarketCategory.WEATHER,),
            kalshi_environment="demo",
        )
    )
    monkeypatch.setattr(
        ports,
        "_selection",
        lambda: (SecretsStore(local_store=backend), "local-encrypted"),
    )
    monkeypatch.setattr(verify_ports, "KalshiClient", Client)

    result = await ports.probe(CheckId.KALSHI)

    assert result.action == "kalshi_credentials_missing"
    assert backend.get_calls == [
        ("kalshi_demo", "api_key"),
        ("kalshi_demo", "private_key_pem"),
    ]
    assert client_calls == 0


def test_installed_wheel_cli_fails_closed_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_root, _, _ = build_and_install_wheel(tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    data_root = runtime_root / "data"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_root)
    environment["TRADERBOT_DATA_DIR"] = str(data_root)
    _ = environment.pop("TRADERBOT_USE_HARDCODED_AUTH", None)

    def run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "traderbot.cli", *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=60.0,
            env=environment,
            cwd=runtime_root,
        )

    # 1. Production with no credentials fails closed before any network call.
    production = run_cli(["backfill", "--environment", "production", "--json"])
    assert production.returncode == 2
    assert "invalid_credentials_or_request" in production.stdout

    # 2. Demo with no credentials fails closed before any network call.
    demo = run_cli(["backfill", "--environment", "demo", "--json"])
    assert demo.returncode == 2
    assert "invalid_credentials_or_request" in demo.stdout

    # 3. Demo with only a production pair present fails closed without fallback.
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_root))
    store = build_secrets_store()
    _ = store.set("kalshi", "api_key", "production-key")
    _ = store.set("kalshi", "private_key_pem", "production-pem")
    missing_demo = run_cli(["backfill", "--environment", "demo", "--json"])
    assert missing_demo.returncode == 2
    assert "invalid_credentials_or_request" in missing_demo.stdout

    # 4. Invalid environment exits before the handler or any file write.
    invalid = run_cli(["verify", "--environment", "invalid", "--categories", "weather", "--json"])
    assert invalid.returncode == 2
    assert "invalid_request" in invalid.stdout

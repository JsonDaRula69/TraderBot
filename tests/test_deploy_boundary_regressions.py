from __future__ import annotations

import ast
import os
import secrets
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from rich.console import Console

from tests.deploy_wizard_fakes import FakeEnvironment, FakePhase45, FakePhase678
from traderbot.deploy import phase45_runtime, verify_ports, wizard_command
from traderbot.deploy.backfill_command import _build_client
from traderbot.deploy.database_step import DatabaseProvisionReport
from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.phase678_runtime import Phase678Adapter
from traderbot.deploy.secret_step import KalshiSecretPair
from traderbot.deploy.verify_models import VerificationRequest
from traderbot.deploy.verify_ports import ProductionVerificationPorts
from traderbot.deploy.wizard_contracts import DeployState, WizardPorts
from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.order_models import MarketCategory
from traderbot.kalshi.websocket import KalshiWebSocket


def _pure_lines(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstring_lines = {
        line
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1)
    }
    return sum(
        line_number not in docstring_lines
        and bool(line.strip())
        and not line.lstrip().startswith("#")
        for line_number, line in enumerate(source.splitlines(), start=1)
    )


def test_configured_data_root_is_shared_by_all_runtime_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "configured"
    environment_default = tmp_path / "environment-default"
    config_path = tmp_path / "deploy.json"
    configured.mkdir(mode=0o700)
    os.chmod(configured, 0o700)
    _ = config_path.write_text(
        '{"categories":["weather"],"mode":"backtest",'
        + f'"data_root":"{configured}",'
        + '"approvals":{"install_openclaw":false,"setup_openclaw":false,'
        + '"create_agents":true,"heartbeat_change":false,"sandbox_apply":false},'
        + '"heartbeat_every":"preserve"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(environment_default))
    observed: dict[str, Path] = {}
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    class Selection:
        store: None = None
        backend = "local-encrypted"
        fallback_store: None = None

        @staticmethod
        def close() -> None:
            return None

    def ports_factory(_store: None, phase45: Phase45Adapter) -> WizardPorts:
        observed["phase45"] = phase45._data_root
        ports = environment.ports()
        return WizardPorts(
            openclaw=ports.openclaw,
            tokens=ports.tokens,
            injector=ports.injector,
            phase45=phase45,
        )

    monkeypatch.setattr(wizard_command, "select_deploy_secrets", lambda _url: Selection())
    monkeypatch.setattr(wizard_command, "build_wizard_ports", ports_factory)

    prepared = wizard_command._prepare_deploy(config_path, None, Console())
    with prepared.resources:
        phase678 = prepared.ports.phase678
        assert isinstance(phase678, Phase678Adapter)
        backfill = phase678._backfill_request(prepared.request)
        verification = phase678._verification_request(prepared.request)
        phase45 = prepared.ports.phase45
        assert isinstance(phase45, Phase45Adapter)
        monkeypatch.setattr(
            phase45_runtime,
            "provision_deploy_databases",
            lambda _categories, _mode, root: (
                observed.update(database=root)
                or DatabaseProvisionReport(root / "traderbot.db", (), 0, (), ())
            ),
        )
        assert phase45.provision_databases(prepared.request).status.value == "completed"
        phase678.save_state(
            prepared.request,
            DeployState(
                step6_fingerprint="six",
                step7_fingerprint="seven",
                step8_fingerprint="eight",
                steps=(),
            ),
        )

    assert observed == {"phase45": configured, "database": configured}
    assert backfill.target_db == configured / "traderbot.db"
    assert verification.data_root == configured
    assert (configured / "deploy-state.json").is_file()
    assert not environment_default.exists()


def test_deploy_runtime_import_graph_has_no_late_step_cycle() -> None:
    deploy = Path(__file__).parents[1] / "src" / "traderbot" / "deploy"
    wizard_runtime = (deploy / "wizard_runtime.py").read_text(encoding="utf-8")
    verify_openclaw = (deploy / "verify_openclaw.py").read_text(encoding="utf-8")

    assert "traderbot.deploy.phase678_runtime" not in wizard_runtime
    assert "traderbot.deploy.wizard_runtime" not in verify_openclaw


def test_split_wizard_modules_stay_within_pure_line_limit() -> None:
    deploy = Path(__file__).parents[1] / "src" / "traderbot" / "deploy"

    assert _pure_lines(deploy / "wizard_command.py") <= 250
    assert _pure_lines(deploy / "wizard_request.py") <= 250


@pytest.mark.asyncio
async def test_standalone_kalshi_paths_are_production_canonical_without_live_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    pair = KalshiSecretPair.from_plain(secrets.token_urlsafe(), pem)
    backfill_client = cast(KalshiClient, _build_client(pair, "production"))
    backfill_base_url = str(backfill_client._client.base_url)
    await backfill_client.close()
    services: list[str] = []
    environments: list[object] = []

    class Store:
        @staticmethod
        def get(service: str, key: str, namespace: str = "global") -> str:
            del namespace
            services.append(service)
            return pair.api_key.get_secret_value() if key == "api_key" else pem

    class Client:
        def __init__(self, **values: object) -> None:
            environments.append(values.get("environment", "production-default"))

        async def get_balance(self, timeout: float) -> None:
            del timeout

        async def close(self) -> None:
            return None

    request = VerificationRequest(
        categories=(MarketCategory.WEATHER,),
    )
    ports = ProductionVerificationPorts(request)
    monkeypatch.setattr(ports, "_selection", lambda: (Store(), "local-encrypted"))
    monkeypatch.setattr(verify_ports, "KalshiClient", Client)
    result = await ports._kalshi()
    websocket = KalshiWebSocket(pair.api_key.get_secret_value(), pem, environment="production")

    assert result.action == "kalshi_auth_valid"
    assert backfill_base_url == "https://external-api.kalshi.com/trade-api/v2/"
    assert services == ["kalshi", "kalshi"]
    assert environments == ["production-default"]
    assert websocket._ws_url == "wss://external-api-ws.kalshi.com/trade-api/ws/v2"

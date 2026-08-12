from __future__ import annotations

from pathlib import Path
from typing import ClassVar, override

import pytest
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from traderbot.deploy.verify import VerificationPorts, run_verification
from traderbot.deploy.verify_models import (
    CheckId,
    CheckStatus,
    ProbeResult,
    TokenProbe,
    VerificationRequest,
)
from traderbot.deploy.verify_runtime import HealthComponents, evaluate_health
from traderbot.deploy.verify_storage import decisions_databases, global_database
from traderbot.kalshi.order_models import MarketCategory


class Evidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True, strict=True)

    version: str
    base: str
    commit: str
    commands: tuple[str, ...]
    receipts: dict[str, str]
    cleanup: tuple[str, ...]
    preserved_full_suite: str


class ProbeCanaryError(Exception):
    pass


class RaisingPorts(VerificationPorts):
    __slots__: ClassVar[tuple[str, ...]] = ("calls", "raised")

    def __init__(self, raised: CheckId) -> None:
        self.raised: CheckId = raised
        self.calls: list[CheckId] = []

    @override
    async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult:
        _ = token
        self.calls.append(check_id)
        if check_id is self.raised:
            raise ProbeCanaryError("SECRET-CANARY")
        return ProbeResult.passed("healthy")

    @override
    async def tokens(self) -> TokenProbe:
        self.calls.append(CheckId.TOKENS)
        if self.raised is CheckId.TOKENS:
            raise ProbeCanaryError("SECRET-CANARY")
        return TokenProbe(result=ProbeResult.passed("valid"), token=SecretStr("opaque"))


def _request(root: Path) -> VerificationRequest:
    return VerificationRequest(categories=(MarketCategory.WEATHER,), data_root=root)


@pytest.mark.asyncio
@pytest.mark.parametrize("raised", tuple(CheckId))
async def test_check_exception_is_local_sanitized_and_graph_continues(
    tmp_path: Path,
    raised: CheckId,
) -> None:
    # Given
    ports = RaisingPorts(raised)

    # When
    result = await run_verification(_request(tmp_path), ports)

    # Then
    indexed = {check.id: check for check in result.checks}
    failed = indexed[raised]
    assert failed.status is CheckStatus.FAIL
    assert failed.action == "check_exception"
    assert "CANARY" not in result.model_dump_json()
    assert CheckId.INFISICAL in ports.calls
    if raised is CheckId.GATEWAY:
        assert indexed[CheckId.AGENTS_WORKSPACES].dependency is CheckId.GATEWAY
    if raised is CheckId.TOKENS:
        assert indexed[CheckId.KALSHI].dependency is CheckId.TOKENS


@pytest.mark.asyncio
async def test_base_exception_propagates(tmp_path: Path) -> None:
    # Given
    class InterruptPorts(RaisingPorts):
        @override
        async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult:
            _ = check_id, token
            raise KeyboardInterrupt

    # When / Then
    with pytest.raises(KeyboardInterrupt):
        _ = await run_verification(_request(tmp_path), InterruptPorts(CheckId.GATEWAY))


@pytest.mark.asyncio
async def test_chroma_uses_online_health_or_offline_probe(tmp_path: Path) -> None:
    # Given
    online = RaisingPorts(CheckId.CRON)
    offline = RaisingPorts(CheckId.DAEMON_RUNTIME)

    # When
    online_result = await run_verification(_request(tmp_path), online)
    offline_result = await run_verification(_request(tmp_path), offline)

    # Then
    online_index = {check.id: check for check in online_result.checks}
    offline_index = {check.id: check for check in offline_result.checks}
    assert online_index[CheckId.CHROMA].status is CheckStatus.PASS
    assert CheckId.CHROMA in online.calls
    assert offline_index[CheckId.CHROMA].status is not CheckStatus.SKIP
    assert CheckId.CHROMA in offline.calls


@pytest.mark.parametrize(
    ("websocket", "pipeline", "expected"),
    [
        ("connected", "running", CheckStatus.PASS),
        ("disconnected", "running", CheckStatus.FAIL),
        ("fail_open", "running", CheckStatus.FAIL),
        ("not_started", "running", CheckStatus.FAIL),
        ("connected", "stopped", CheckStatus.FAIL),
    ],
)
def test_daemon_health_policy_is_explicit(
    websocket: str,
    pipeline: str,
    expected: CheckStatus,
) -> None:
    # Given
    components = HealthComponents.model_validate(
        {
            "mcp_server": "running",
            "auth": "resolved",
            "data_pipeline": pipeline,
            "websocket": websocket,
            "database": "initialized",
            "chromadb": "initialized",
            "chromadb_lock": "held",
        }
    )

    # When
    result = evaluate_health(components)

    # Then
    assert result.status is expected


@pytest.mark.parametrize(
    "url",
    [
        "http://user@127.0.0.1:8765/mcp",
        "http://:password@127.0.0.1:8765/mcp",
        "http://user:password@127.0.0.1:8765/mcp",
        "http://127.0.0.1:8765/mcp?x=1",
        "http://127.0.0.1:8765/mcp#x",
        "http://127.0.0.1:8765/%6dcp",
        "http://127.0.0.1:8765/mcp%0a",
    ],
)
def test_mcp_url_rejects_ambiguous_or_secret_authority(url: str) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        _ = VerificationRequest(categories=(MarketCategory.WEATHER,), daemon_mcp_url=url)


@pytest.mark.parametrize("mode", ("backtest", "paper", "live"))
def test_all_sysadmin_mode_databases_are_forbidden(tmp_path: Path, mode: str) -> None:
    # Given
    forbidden = tmp_path / f"{mode}-sysadmin" / "db" / "decisions.db"
    forbidden.parent.mkdir(parents=True)
    forbidden.touch()

    # When
    result = decisions_databases(_request(tmp_path))

    # Then
    assert result.action == "sysadmin_db_forbidden"


def test_schema_authority_ignores_mutated_runtime_registries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    from traderbot.db.decisions import init_decisions_db
    from traderbot.db.migrations import init_schema

    global_path = tmp_path / "traderbot.db"
    decision_path = tmp_path / "backtest-weather" / "db" / "decisions.db"
    init_schema(global_path)
    decision_path.parent.mkdir(parents=True)
    init_decisions_db(decision_path)
    monkeypatch.setattr("traderbot.db.migrations.GLOBAL_MIGRATIONS", ())
    monkeypatch.setattr("traderbot.db.decisions.DECISIONS_MIGRATIONS", ())

    # When / Then
    assert global_database(_request(tmp_path)).status is CheckStatus.PASS
    assert decisions_databases(_request(tmp_path)).status is CheckStatus.PASS


def test_evidence_records_substantive_repair_contract() -> None:
    # Given
    path = Path(__file__).parents[2] / ".omo" / "evidence" / "task-10-phase4-deploy-wizard.json"

    # When
    evidence = Evidence.model_validate_json(path.read_text(encoding="utf-8"))

    # Then
    required = {"base", "commit", "commands", "receipts", "cleanup", "preserved_full_suite"}
    assert required <= set(evidence.model_fields_set)
    assert evidence.version == "2.0.0a94"

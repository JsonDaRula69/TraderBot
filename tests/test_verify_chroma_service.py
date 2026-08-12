from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import SecretStr

from traderbot.db.chroma_ownership import ChromaOwnershipLock
from traderbot.db.chroma_store import ChromaStore
from traderbot.db.security import create_chroma_root
from traderbot.deploy import verify_ports, verify_runtime
from traderbot.deploy.verify_models import CheckId, CheckStatus, ProbeResult, VerificationRequest
from traderbot.deploy.verify_storage import chroma_offline
from traderbot.kalshi.order_models import MarketCategory
from traderbot.services.paths import BinPaths


def _request(root: Path) -> VerificationRequest:
    return VerificationRequest(categories=(MarketCategory.WEATHER,), data_root=root)


def _tree_receipt(root: Path) -> tuple[tuple[Path, int, bytes], ...]:
    return tuple(
        (path.relative_to(root), path.lstat().st_mode, path.read_bytes() if path.is_file() else b"")
        for path in sorted(root.rglob("*"))
    )


def _fail_lock(_lock: ChromaOwnershipLock) -> None:
    pytest.fail("lock acquired")


def _fail_client(_client: ChromaStore, _root: Path) -> None:
    pytest.fail("client opened")


def _running_process(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    _ = timeout
    return subprocess.CompletedProcess(argv, returncode=0, stdout="RUNNING", stderr="")


def test_chroma_offline_uses_exact_root_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    root = tmp_path / "chromadb"
    monkeypatch.setattr("traderbot.db.security.get_data_dir", lambda: tmp_path)
    create_chroma_root(root)
    before = _tree_receipt(tmp_path)
    monkeypatch.setattr("traderbot.db.chroma_ownership.ChromaOwnershipLock.acquire", _fail_lock)
    monkeypatch.setattr("traderbot.db.chroma_store.ChromaStore.__init__", _fail_client)

    # When
    result = chroma_offline(_request(tmp_path))

    # Then
    assert result.status is CheckStatus.DEGRADED
    assert before == _tree_receipt(tmp_path)


@pytest.mark.asyncio
async def test_production_chroma_branch_uses_runtime_or_offline_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    ports = verify_ports.ProductionVerificationPorts(_request(tmp_path))
    offline_calls: list[Path] = []

    async def healthy_runtime(
        _request_value: VerificationRequest, _token: SecretStr
    ) -> ProbeResult:
        return ProbeResult.passed("daemon_health_exact")

    def offline(request_value: VerificationRequest) -> ProbeResult:
        offline_calls.append(request_value.data_root)
        return ProbeResult.degraded("chroma_runtime_unverified", "offline")

    monkeypatch.setattr(verify_ports, "daemon_runtime", healthy_runtime)
    monkeypatch.setattr(verify_ports, "chroma_offline", offline)

    # When
    runtime_result = await ports.probe(CheckId.DAEMON_RUNTIME, SecretStr("opaque"))
    online_result = await ports.probe(CheckId.CHROMA, SecretStr("opaque"))
    ports.set_runtime_result(ProbeResult.failed("daemon_unreachable", "unavailable"))
    offline_result = await ports.probe(CheckId.CHROMA, SecretStr("opaque"))

    # Then
    assert runtime_result.status is CheckStatus.PASS
    assert online_result.action == "chroma_daemon_owned"
    assert offline_result.status is CheckStatus.DEGRADED
    assert offline_calls == [tmp_path]
    ports.close()


def test_windows_service_path_uses_authoritative_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    paths = BinPaths(
        traderbot_bin=tmp_path / "bin" / "traderbot",
        python_bin=tmp_path / "bin" / "python",
        home=tmp_path / "alternate-home",
        user="tester",
    )
    expected = paths.home / ".traderbot" / "traderbot-daemon.xml"
    expected.parent.mkdir(parents=True)
    expected.touch()
    monkeypatch.setattr(verify_runtime, "detect_service_manager", lambda: "windows")
    monkeypatch.setattr(verify_runtime, "resolve_bin_paths", lambda: paths)
    monkeypatch.setattr(verify_runtime, "run_bounded", _running_process)

    # When
    result = verify_runtime.service_status()

    # Then
    assert result.status is CheckStatus.PASS

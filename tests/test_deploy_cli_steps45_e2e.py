"""Real CLI failure scenarios for deploy steps 4-5."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.deploy_cli_support import build_fake_environment, run_fake_cli
from tests.test_deploy_cli_fake_e2e import write_config, write_happy_state
from traderbot.db.chroma_store import ChromaStore
from traderbot.db.security import create_chroma_root
from traderbot.deploy.wizard import DeployResult, StepStatus
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.store import SecretsStore


def test_real_cli_invalid_pem_stops_before_kalshi_or_database_mutation(tmp_path: Path) -> None:
    # Given: a complete config whose referenced PEM is malformed.
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, tmp_path)
    env["TRADERBOT_TEST_KALSHI_PEM"] = "malformed-non-secret-test-input"
    config = tmp_path / "deploy.json"
    write_config(config, tmp_path / "approved" / "crypto")

    # When: the real CLI reaches local RSA validation.
    result = run_fake_cli(config, env)

    # Then: step 4 fails without canonical Kalshi writes or step-5 resources.
    parsed = DeployResult.model_validate_json(result.stdout)
    store = SecretsStore(
        local_store=LocalEncryptedStore(Path(env["TRADERBOT_DATA_DIR"]) / "secrets")
    )
    assert result.returncode == 1
    assert parsed.steps[3].status is StepStatus.FAILED
    assert parsed.steps[4].status is StepStatus.SKIPPED
    assert store.get("kalshi", "api_key") is None
    assert store.get("kalshi", "private_key_pem") is None
    assert not (Path(env["TRADERBOT_DATA_DIR"]) / "chromadb").exists()
    assert not tuple(Path(env["TRADERBOT_DATA_DIR"]).glob("backtest-*/db/decisions.db"))


def test_real_cli_missing_environment_references_name_only_missing_variables(
    tmp_path: Path,
) -> None:
    # Given: a complete reference pair whose environment values are absent.
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, tmp_path)
    del env["TRADERBOT_TEST_KALSHI_KEY"]
    del env["TRADERBOT_TEST_KALSHI_PEM"]
    config = tmp_path / "deploy.json"
    write_config(config, tmp_path / "approved" / "crypto")

    # When: the real CLI resolves noninteractive secret references.
    result = run_fake_cli(config, env)

    # Then: output reports only the two names and database creation stays blocked.
    parsed = DeployResult.model_validate_json(result.stdout)
    assert result.returncode == 1
    assert parsed.steps[3].status is StepStatus.FAILED
    assert "TRADERBOT_TEST_KALSHI_KEY" in parsed.steps[3].message
    assert "TRADERBOT_TEST_KALSHI_PEM" in parsed.steps[3].message
    assert not (Path(env["TRADERBOT_DATA_DIR"]) / "chromadb").exists()


def test_real_cli_chroma_lock_blocks_then_rerun_reopens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: valid secret references and an externally held embedded Chroma lock.
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, tmp_path)
    config = tmp_path / "deploy.json"
    write_config(config, tmp_path / "approved" / "crypto")
    data_root = Path(env["TRADERBOT_DATA_DIR"])
    data_root.mkdir(mode=0o700)
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(data_root))
    chroma_root = data_root / "chromadb"
    create_chroma_root(chroma_root)
    owner = ChromaStore(chroma_root)

    # When: one run contends, then the owner closes and deploy reruns.
    try:
        blocked = run_fake_cli(config, env)
    finally:
        owner.close()
    healed = run_fake_cli(config, env)

    # Then: contention is non-destructive and the rerun converges without lock removal.
    blocked_result = DeployResult.model_validate_json(blocked.stdout)
    healed_result = DeployResult.model_validate_json(healed.stdout)
    assert blocked.returncode == 1
    assert blocked_result.steps[4].status is StepStatus.FAILED
    assert chroma_root.is_dir()
    assert healed.returncode == 0
    assert healed_result.completed_steps == tuple(range(1, 9))
    with ChromaStore(chroma_root) as reopened:
        assert reopened.list_collections() == []


def test_real_cli_proxy_environment_uses_honest_encrypted_fallback(tmp_path: Path) -> None:
    # Given: a complete deploy and an unsafe SDK proxy environment.
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, tmp_path)
    env["HTTPS_PROXY"] = "http://proxy.invalid:3128"
    config = tmp_path / "deploy.json"
    write_config(config, tmp_path / "approved" / "crypto")

    # When: the real CLI reaches backend selection.
    result = run_fake_cli(config, env)

    # Then: deploy succeeds through the honestly reported encrypted fallback.
    parsed = DeployResult.model_validate_json(result.stdout)
    assert result.returncode == 0
    assert parsed.steps[3].status is StepStatus.COMPLETED
    assert "backend=local-encrypted" in parsed.steps[3].message


def test_real_cli_partial_pair_requires_approval_then_reruns_without_rewrite(
    tmp_path: Path,
) -> None:
    # Given: only the matching API field is durable and reconciliation is explicit.
    state_path, env = build_fake_environment(tmp_path)
    write_happy_state(state_path, tmp_path)
    data_root = Path(env["TRADERBOT_DATA_DIR"])
    local = LocalEncryptedStore(data_root / "secrets")
    local.set(
        service="kalshi",
        key="api_key",
        value=env["TRADERBOT_TEST_KALSHI_KEY"],
        namespace="global",
    )
    config = tmp_path / "deploy.json"
    write_config(
        config,
        tmp_path / "approved" / "crypto",
        {"reconcile_incomplete": True},
    )

    # When: deploy reconciles once and reruns against the complete durable pair.
    first = run_fake_cli(config, env)
    encrypted_path = data_root / "secrets" / "secrets.json"
    encrypted_after_first = encrypted_path.read_bytes()
    second = run_fake_cli(config, env)

    # Then: both runs succeed and the second performs no secret rewrite.
    first_result = DeployResult.model_validate_json(first.stdout)
    second_result = DeployResult.model_validate_json(second.stdout)
    assert first.returncode == 0
    assert second.returncode == 0
    assert first_result.steps[3].status is StepStatus.COMPLETED
    assert second_result.steps[3].status is StepStatus.COMPLETED
    assert encrypted_path.read_bytes() == encrypted_after_first

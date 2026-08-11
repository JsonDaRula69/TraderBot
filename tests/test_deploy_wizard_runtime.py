from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from traderbot.deploy import openclaw
from traderbot.deploy.openclaw_models import CronJob, JsonValue
from traderbot.deploy.wizard import ProvisionStatus
from traderbot.deploy.wizard_runtime import OpenClawAdapter, SecretsTokenProvisioner
from traderbot.kalshi.models import MarketCategory
from traderbot.mcp.resolver import resolve_token_adapter
from traderbot.profiles.generic import create_category_profile
from traderbot.profiles.tokens import set_store
from traderbot.secrets.adapter import TokenStoreAdapter
from traderbot.secrets.local_encrypted import LocalEncryptedStore
from traderbot.secrets.store import SecretsStore

_EXPECTED_BOOTSTRAP_PROMPT = (
    "Begin the SysAdmin activation protocol: remove this bootstrap job, verify the "
    "TraderBot service and data freshness, register essential jobs, enable the SysAdmin "
    "heartbeat, then activate selected categories one at a time."
)


class FailingLocalStore:
    def get(self, *, service: str, key: str, namespace: str) -> str | None:
        _ = service, key, namespace
        return None

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None:
        _ = service, key, value, namespace
        raise OSError("opaque-test-value")

    def delete(self, *, service: str, key: str, namespace: str) -> None:
        _ = service, key, namespace
        raise AssertionError

    def get_namespace(self, namespace: str) -> dict[str, str]:
        _ = namespace
        return {}


def _managed_bootstrap_cron() -> CronJob:
    return {
        "id": "bootstrap-id",
        "name": "traderbot-main-at-5m",
        "agentId": "main",
        "enabled": True,
        "createdAtMs": 1_700_000_000_000,
        "updatedAtMs": 1_700_000_000_000,
        "schedule": {"kind": "at", "at": "2023-11-14T22:18:20Z"},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": _EXPECTED_BOOTSTRAP_PROMPT},
        "deleteAfterRun": True,
        "state": {},
    }


def test_encrypted_identity_is_reused_and_restart_resolvable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an encrypted test store and one category profile
    first_store = SecretsStore(local_store=LocalEncryptedStore(tmp_path))
    provisioner = SecretsTokenProvisioner(first_store, lambda: "opaque-test-value")
    profile = create_category_profile("crypto", "backtest", (MarketCategory.CRYPTO,))

    # When: identity provisioning runs twice and the store is reconstructed
    first = provisioner.ensure(profile, "crypto")
    second = provisioner.ensure(profile, "crypto")
    restarted = SecretsStore(local_store=LocalEncryptedStore(tmp_path))
    set_store(TokenStoreAdapter(restarted))
    monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "0")
    try:
        resolved_profile, resolved_agent = resolve_token_adapter("opaque-test-value")
    finally:
        set_store(None)

    # Then: one opaque identity persists and resolves after process-local state is gone
    assert first.status is ProvisionStatus.CREATED
    assert second.status is ProvisionStatus.EXISTING
    assert restarted.resolve_profile_token("opaque-test-value") == ("crypto", "crypto")
    assert resolved_profile is not None
    assert resolved_profile.name == "crypto"
    assert resolved_profile.mode == "backtest"
    assert resolved_agent == "crypto"
    assert b"opaque-test-value" not in (tmp_path / "secrets.json").read_bytes()


def test_storage_failure_does_not_echo_backend_secret() -> None:
    # Given: a backend error message containing the opaque value
    store = SecretsStore(local_store=FailingLocalStore())
    provisioner = SecretsTokenProvisioner(store, lambda: "opaque-test-value")
    profile = create_category_profile("crypto", "backtest", (MarketCategory.CRYPTO,))

    # When: encrypted persistence fails
    result = provisioner.ensure(profile, "crypto")

    # Then: the typed failure is actionable without echoing backend details
    assert result.status is ProvisionStatus.FAILED
    assert result.message == "encrypted identity storage failed"
    assert "opaque-test-value" not in result.message


def test_bootstrap_cron_reuses_exact_main_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the complete managed activation contract already belongs to main
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(
        openclaw,
        "inspect_crons",
        mock.Mock(return_value=[_managed_bootstrap_cron()]),
    )
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the adapter reconciles the bootstrap job
    result = OpenClawAdapter().ensure_bootstrap_cron()

    # Then: the existing stable identity is accepted without duplicate creation
    assert result is True
    assert register.call_count == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schedule", {"kind": "every", "everyMs": 86_400_000}),
        ("sessionTarget", "main"),
        ("payload", {"kind": "systemEvent", "text": "wrong activation"}),
        ("enabled", False),
        ("deleteAfterRun", False),
    ],
)
def test_bootstrap_cron_mismatch_fails_without_add(
    field: str,
    value: JsonValue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a same-name/main job with one invalid managed field
    job = _managed_bootstrap_cron()
    job[field] = value
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "inspect_crons", mock.Mock(return_value=[job]))
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the adapter reconciles the managed identity
    result = OpenClawAdapter().ensure_bootstrap_cron()

    # Then: the conflict fails closed without adding, editing, or deleting
    assert result is False
    assert register.call_count == 0


def test_bootstrap_cron_add_is_verified_from_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: no existing job and a misleading successful add followed by a wrong inventory
    wrong = _managed_bootstrap_cron()
    wrong["deleteAfterRun"] = False
    inspect = mock.Mock(side_effect=[[], [wrong]])
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "inspect_crons", inspect)
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the missing bootstrap cron is reconciled
    result = OpenClawAdapter().ensure_bootstrap_cron()

    # Then: post-add verification rejects the wrong stored contract
    assert result is False
    assert register.call_count == 1
    assert inspect.call_count == 2


def test_bootstrap_cron_add_succeeds_after_exact_inventory_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: no existing job and an exact managed contract after add
    inspect = mock.Mock(side_effect=[[], [_managed_bootstrap_cron()]])
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "inspect_crons", inspect)
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the missing bootstrap cron is reconciled
    result = OpenClawAdapter().ensure_bootstrap_cron()

    # Then: one add and one confirmation inventory complete reconciliation
    assert result is True
    assert register.call_count == 1
    assert inspect.call_count == 2


def test_bootstrap_cron_collision_fails_without_add(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the stable name is owned by another agent
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(
        openclaw,
        "inspect_crons",
        mock.Mock(return_value=[{"name": "traderbot-main-at-5m", "agentId": "weather"}]),
    )
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: reconciliation inspects the collision
    result = OpenClawAdapter().ensure_bootstrap_cron()

    # Then: it fails closed rather than creating a duplicate
    assert result is False
    assert register.call_count == 0


def test_secret_ref_updates_only_selected_agent_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a recording safe-config boundary
    writes: list[tuple[str, str]] = []

    def record_write(key: str, value: str) -> bool:
        writes.append((key, value))
        return True

    monkeypatch.setattr(openclaw, "set_config", record_write)

    # When: one selected category mapping is configured
    result = OpenClawAdapter().configure_secret_ref("crypto", "crypto_token")

    # Then: only the selected mapping's three SecretRef fields are touched
    assert result is True
    assert writes == [
        (
            "plugins.entries.traderbot-token-injector.config.agentTokenMap.crypto.source",
            "exec",
        ),
        (
            "plugins.entries.traderbot-token-injector.config.agentTokenMap.crypto.provider",
            "infisical",
        ),
        (
            "plugins.entries.traderbot-token-injector.config.agentTokenMap.crypto.id",
            "crypto_token",
        ),
    ]


def test_agent_workspace_mismatch_fails_before_openclaw_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a hostile explicit path that differs from the Todo-3 workspace convention
    create = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "create_agent", create)

    # When: the runtime adapter validates it
    result = OpenClawAdapter().create_agent("weather", tmp_path / "$(touch-pwned)")

    # Then: the path remains inert data and no OpenClaw mutation is attempted
    assert result is False
    assert create.call_count == 0

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from traderbot.deploy import openclaw, openclaw_config
from traderbot.deploy.openclaw_models import AgentInventory, AgentSummary, CronJob, JsonValue
from traderbot.deploy.wizard import ProvisionStatus
from traderbot.deploy.wizard_runtime import (
    OpenClawAdapter,
    SecretsTokenProvisioner,
    resolve_agent_config_path,
)
from traderbot.deploy.wizard_state import BootstrapCronState, SecretRefConfig
from traderbot.kalshi.order_models import MarketCategory
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


def test_characterization_encrypted_identity_is_reused_and_restart_resolvable(
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


def test_characterization_bootstrap_cron_reuses_exact_main_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the complete managed activation contract already belongs to main
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(
        openclaw,
        "inspect_crons",
        mock.Mock(return_value=[_managed_bootstrap_cron()]),
    )
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the adapter reconciles the bootstrap job
    result = OpenClawAdapter().ensure_bootstrap_cron(BootstrapCronState.EXACT)

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
    result = OpenClawAdapter().ensure_bootstrap_cron(BootstrapCronState.CONFLICT)

    # Then: the conflict fails closed without adding, editing, or deleting
    assert result is False
    assert register.call_count == 0


def test_bootstrap_cron_add_is_verified_from_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: no existing job and a misleading successful add followed by a wrong inventory
    wrong = _managed_bootstrap_cron()
    wrong["deleteAfterRun"] = False
    inspect = mock.Mock(return_value=[wrong])
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "inspect_crons", inspect)
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the missing bootstrap cron is reconciled
    result = OpenClawAdapter().ensure_bootstrap_cron(BootstrapCronState.MISSING)

    # Then: post-add verification rejects the wrong stored contract
    assert result is False
    assert register.call_count == 1
    assert inspect.call_count == 1


def test_bootstrap_cron_add_succeeds_after_exact_inventory_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: no existing job and an exact managed contract after add
    inspect = mock.Mock(return_value=[_managed_bootstrap_cron()])
    register = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "inspect_crons", inspect)
    monkeypatch.setattr(openclaw, "register_cron", register)

    # When: the missing bootstrap cron is reconciled
    result = OpenClawAdapter().ensure_bootstrap_cron(BootstrapCronState.MISSING)

    # Then: one add and one confirmation inventory complete reconciliation
    assert result is True
    assert register.call_count == 1
    assert inspect.call_count == 1


def test_completed_bootstrap_job_is_not_an_exact_pending_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Gateway retains the canonical job with completed runtime state.
    completed = _managed_bootstrap_cron()
    completed["state"] = {"lastStatus": "ok", "lastRunAtMs": 1_700_000_300_000}
    monkeypatch.setattr(openclaw, "inspect_crons", lambda: [completed])

    # When: TraderBot inspects the pending one-shot contract.
    state = OpenClawAdapter().inspect_bootstrap_cron()

    # Then: completed state is distinct from the exact active matcher.
    assert state is BootstrapCronState.COMPLETED_RETAINED


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
    result = OpenClawAdapter().ensure_bootstrap_cron(BootstrapCronState.CONFLICT)

    # Then: it fails closed rather than creating a duplicate
    assert result is False
    assert register.call_count == 0


def test_secret_ref_updates_only_selected_agent_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a recording atomic SecretRef boundary
    write = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "set_secret_ref", write)

    # When: one selected category mapping is configured
    secret_ref = SecretRefConfig(id="crypto_token")
    result = OpenClawAdapter().set_secret_ref("crypto", secret_ref)

    # Then: the complete selected mapping is written once
    assert result is True
    write.assert_called_once_with("crypto", secret_ref)


def test_agent_workspace_is_forwarded_as_explicit_inert_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an arbitrary approved absolute path with shell-like text
    create = mock.Mock(return_value=True)
    monkeypatch.setattr(openclaw, "create_agent", create)

    workspace = tmp_path / "$(touch-pwned)"
    result = OpenClawAdapter().create_agent("weather", workspace)

    # Then: the path remains one typed argument without local convention rewriting
    assert result is True
    create.assert_called_once_with("weather", workspace)


def _weather_inventory() -> AgentInventory:
    workspace = str(Path(Path.cwd().anchor) / "srv" / "weather")
    return AgentInventory(
        [
            AgentSummary(
                id="weather",
                workspace=workspace,
                agentDir="/state/weather",
                bindings=0,
                isDefault=False,
            )
        ]
    )


def test_resolve_agent_config_path_uses_entries_first_then_list_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the REAL read logic with only the CLI boundary mocked — entries is
    # absent and the deployed 2026.7.1-2 shape serves the agent at list index 0
    monkeypatch.setattr(openclaw, "inspect_agents", mock.Mock(return_value=_weather_inventory()))
    run = mock.Mock(
        side_effect=[
            subprocess.CompletedProcess(
                ["openclaw"], 1, "", "Config path not found: agents.entries.weather\n"
            ),
            subprocess.CompletedProcess(
                ["openclaw"], 0, '{"id":"weather","sandbox":{"mode":"all"}}', ""
            ),
        ]
    )
    monkeypatch.setattr(openclaw_config, "_run", run)

    # When: the wizard resolves the write target from observed current state
    prefix = resolve_agent_config_path("weather")

    # Then: the fallback lands on the deployed-shape bracket path, twice-read
    assert prefix == "agents.list[0]"
    assert run.call_count == 2


def test_resolve_agent_config_path_fails_closed_without_observed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an unreadable inventory — no prefix may be guessed from stale state
    monkeypatch.setattr(openclaw, "inspect_agents", mock.Mock(return_value=None))
    assert resolve_agent_config_path("weather") is None

    # And: an agent absent from the inventory resolves to None without any read
    monkeypatch.setattr(openclaw, "inspect_agents", mock.Mock(return_value=_weather_inventory()))
    assert resolve_agent_config_path("crypto") is None

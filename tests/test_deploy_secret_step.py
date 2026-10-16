"""Behavioral tests for deploy step 4 secret collection and persistence."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr, ValidationError

from traderbot.deploy.config import DeployConfig
from traderbot.deploy.secret_step import (
    EnvironmentSecretInput,
    HiddenSecretInput,
    KalshiSecretPair,
    MissingSecretEnvironmentError,
    SecretPairValidationError,
    SecretReconciliationError,
    provision_kalshi_secrets,
    select_deploy_secrets,
)


class _MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.set_calls: list[tuple[str, str]] = []

    def get(self, service: str, key: str, namespace: str = "global") -> str | None:
        del namespace
        return self.values.get((service, key))

    def set(
        self,
        service: str,
        key: str,
        value: str,
        namespace: str = "global",
    ) -> None:
        del namespace
        self.values[(service, key)] = value
        self.set_calls.append((service, key))


class _InjectedBackendWriteFault(RuntimeError):
    pass


class _SecondWriteFails(_MemorySecrets):
    def set(
        self,
        service: str,
        key: str,
        value: str,
        namespace: str = "global",
    ) -> None:
        if key == "private_key_pem":
            raise _InjectedBackendWriteFault("injected backend write failure")
        super().set(service, key, value, namespace)


def _secret_pair() -> KalshiSecretPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return KalshiSecretPair.from_plain(secrets.token_urlsafe(), pem)


def _plain(value: SecretStr) -> str:
    return value.get_secret_value()


def test_deploy_config_accepts_only_environment_secret_references(tmp_path: Path) -> None:
    # Given: a complete config containing environment variable names.
    payload = {
        "categories": ["weather"],
        "mode": "backtest",
        "tokens": {
            "kalshi_api_key_env": "TEST_KALSHI_KEY",
            "kalshi_private_key_pem_env": "TEST_KALSHI_PEM",
        },
        "category_workspaces": {"weather": str(tmp_path / "weather")},
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": True,
            "heartbeat_change": False,
            "sandbox_apply": False,
        },
        "heartbeat_every": "preserve",
    }

    # When: the document crosses the noninteractive boundary.
    config = DeployConfig.model_validate(payload)

    # Then: only typed non-secret references survive parsing.
    assert config.tokens.kalshi_api_key_env == "TEST_KALSHI_KEY"
    with pytest.raises(ValidationError):
        _ = DeployConfig.model_validate(
            {**payload, "tokens": {"kalshi_api_key": secrets.token_urlsafe()}}
        )


def test_environment_input_reports_only_missing_variable_names() -> None:
    # Given: both references are valid names but neither variable exists.
    source = EnvironmentSecretInput("TEST_KALSHI_KEY", "TEST_KALSHI_PEM", environment={})

    # When: the source resolves the pair.
    with pytest.raises(MissingSecretEnvironmentError) as raised:
        _ = source.read()

    # Then: the error identifies names only and carries no secret values.
    assert raised.value.names == ("TEST_KALSHI_KEY", "TEST_KALSHI_PEM")


def test_hidden_input_uses_fakeable_password_prompt() -> None:
    # Given: a fake hidden prompt returns a runtime-generated pair.
    pair = _secret_pair()
    prompts: list[str] = []

    def ask(label: str) -> str:
        prompts.append(label)
        return _plain(pair.api_key) if len(prompts) == 1 else _plain(pair.private_key_pem)

    # When: interactive secret input collects the pair.
    collected = HiddenSecretInput(ask).read()

    # Then: the abstraction requested exactly two hidden values without embedding either value.
    assert collected == pair
    assert len(prompts) == 2
    assert all(
        _plain(pair.api_key) not in prompt and _plain(pair.private_key_pem) not in prompt
        for prompt in prompts
    )


def test_unreachable_infisical_selects_encrypted_local_backend(tmp_path: Path) -> None:
    # Given: the explicit status seam reports the configured local vault unavailable.
    status_calls: list[str] = []

    def unavailable(url: str) -> bool:
        status_calls.append(url)
        return False

    # When: deploy selects its secret facade.
    selection = select_deploy_secrets(
        "http://127.0.0.1:9080",
        local_path=tmp_path / "secrets",
        status_probe=unavailable,
    )

    # Then: fallback is encrypted, explicit, and no further Infisical work is attempted.
    assert selection.backend == "local-encrypted"
    assert status_calls == ["http://127.0.0.1:9080"]
    selection.store.set("kalshi", "api_key", secrets.token_urlsafe())
    assert (tmp_path / "secrets" / "secrets.json").is_file()


def test_healthy_status_without_usable_credentials_still_falls_back_encrypted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: status is misleadingly healthy but the isolated root has no credentials.
    monkeypatch.setenv("TRADERBOT_DATA_DIR", str(tmp_path / "data"))

    # When: deploy attempts backend selection.
    selection = select_deploy_secrets(
        "http://127.0.0.1:9080",
        local_path=tmp_path / "secrets",
        status_probe=lambda _url: True,
    )

    # Then: unusable Infisical still resolves to the encrypted facade without mutation.
    assert selection.backend == "local-encrypted"
    assert not (tmp_path / "secrets").exists()


def test_invalid_pem_fails_before_first_secret_write() -> None:
    # Given: an absent backend pair and a non-RSA replacement.
    store = _MemorySecrets()
    pair = KalshiSecretPair.from_plain(secrets.token_urlsafe(), "not-a-pem")

    # When/Then: local validation fails before mutating the store.
    with pytest.raises(SecretPairValidationError):
        _ = provision_kalshi_secrets(store, lambda: pair, backend="local-encrypted")
    assert store.set_calls == []


def test_valid_pair_is_stored_once_without_values_in_report() -> None:
    # Given: an empty backend and a runtime-generated valid pair.
    store = _MemorySecrets()
    pair = _secret_pair()

    # When: step 4 provisions the canonical pair twice.
    first = provision_kalshi_secrets(store, lambda: pair, backend="local-encrypted")
    second = provision_kalshi_secrets(
        store,
        lambda: pytest.fail("valid stored secrets must be reused"),
        backend="local-encrypted",
    )

    # Then: both canonical keys were written only on the first run and reports are secret-free.
    assert store.set_calls == [("kalshi", "api_key"), ("kalshi", "private_key_pem")]
    assert first.status == "created"
    assert second.status == "existing"
    report_text = f"{first!r}{second!r}"
    assert _plain(pair.api_key) not in report_text
    assert _plain(pair.private_key_pem) not in report_text


def test_partial_backend_write_reports_forward_reconciliation_boundary() -> None:
    # Given: a valid pair and a backend that fails only on the second canonical write.
    store = _SecondWriteFails()
    pair = _secret_pair()

    # When: the unexpected partial write occurs.
    with pytest.raises(SecretReconciliationError) as raised:
        _ = provision_kalshi_secrets(store, lambda: pair, backend="local-encrypted")

    # Then: the boundary names written and pending keys without deleting or exposing values.
    assert raised.value.written_secret_names == ("kalshi_api_key",)
    assert raised.value.pending_secret_names == ("kalshi_private_key_pem",)
    assert store.set_calls == [("kalshi", "api_key")]
    assert _plain(pair.api_key) not in str(raised.value)
    assert _plain(pair.private_key_pem) not in str(raised.value)
